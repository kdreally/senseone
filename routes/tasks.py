from datetime import datetime, date, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from models import db, Task, TaskVersion, User, TASK_STATUSES, VERSIONED_STATUSES

tasks_bp = Blueprint("tasks", __name__, url_prefix="/tasks")

PRIORITY_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High")]


def _snapshot_task(task, changed_by, change_note=""):
    """Record an immutable version snapshot of the task."""
    next_version = (task.latest_version.version_number + 1) if task.latest_version else 1
    version = TaskVersion(
        task_id=task.id,
        version_number=next_version,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        due_date=task.due_date,
        assigned_to_id=task.assigned_to_id,
        changed_by_id=changed_by.id,
        changed_at=datetime.now(timezone.utc),
        change_note=change_note,
    )
    db.session.add(version)


def _parse_due_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# List / Dashboard
# ---------------------------------------------------------------------------

@tasks_bp.route("/")
@login_required
def list_tasks():
    status_filter = request.args.get("status", "")
    assigned_filter = request.args.get("assigned", "")
    priority_filter = request.args.get("priority", "")

    query = Task.query

    if status_filter:
        query = query.filter(Task.status == status_filter)
    if assigned_filter == "me":
        query = query.filter(Task.assigned_to_id == current_user.id)
    elif assigned_filter == "created":
        query = query.filter(Task.created_by_id == current_user.id)
    if priority_filter:
        query = query.filter(Task.priority == priority_filter)

    tasks = query.order_by(Task.updated_at.desc()).all()
    users = User.query.order_by(User.username).all()

    return render_template(
        "tasks/list.html",
        tasks=tasks,
        users=users,
        status_filter=status_filter,
        assigned_filter=assigned_filter,
        priority_filter=priority_filter,
        PRIORITY_CHOICES=PRIORITY_CHOICES,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@tasks_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_task():
    users = User.query.order_by(User.username).all()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", "medium")
        due_date_str = request.form.get("due_date", "")
        assigned_to_id = request.form.get("assigned_to_id") or None

        if not title:
            flash("Title is required.", "danger")
        else:
            task = Task(
                title=title,
                description=description,
                status="draft",
                priority=priority,
                due_date=_parse_due_date(due_date_str),
                created_by_id=current_user.id,
                assigned_to_id=int(assigned_to_id) if assigned_to_id else None,
            )
            db.session.add(task)
            db.session.commit()
            flash("Task created.", "success")
            return redirect(url_for("tasks.task_detail", task_id=task.id))

    return render_template(
        "tasks/create.html",
        users=users,
        PRIORITY_CHOICES=PRIORITY_CHOICES,
    )


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@tasks_bp.route("/<int:task_id>")
@login_required
def task_detail(task_id):
    task = Task.query.get_or_404(task_id)
    return render_template("tasks/detail.html", task=task)


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------

@tasks_bp.route("/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    users = User.query.order_by(User.username).all()

    if request.method == "POST":
        old_status = task.status

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", task.priority)
        due_date_str = request.form.get("due_date", "")
        assigned_to_id = request.form.get("assigned_to_id") or None
        new_status = request.form.get("status", task.status)
        change_note = request.form.get("change_note", "").strip()

        if not title:
            flash("Title is required.", "danger")
            return render_template(
                "tasks/edit.html",
                task=task,
                users=users,
                PRIORITY_CHOICES=PRIORITY_CHOICES,
            )

        # If the task is already in a versioned status, record the current
        # state BEFORE applying changes so we preserve a clean before-snapshot.
        was_versioned = task.status in VERSIONED_STATUSES

        task.title = title
        task.description = description
        task.priority = priority
        task.due_date = _parse_due_date(due_date_str)
        task.assigned_to_id = int(assigned_to_id) if assigned_to_id else None
        task.status = new_status
        task.updated_at = datetime.now(timezone.utc)

        # Versioning logic:
        # - If the task transitions INTO a versioned status, record v1.
        # - If it was already versioned, record the updated state.
        entering_versioned = new_status in VERSIONED_STATUSES and not was_versioned
        already_versioned = new_status in VERSIONED_STATUSES and was_versioned

        if entering_versioned or already_versioned:
            _snapshot_task(task, current_user, change_note)

        db.session.commit()

        if entering_versioned:
            flash(
                f"Task saved as '{dict(TASK_STATUSES)[new_status]}'. "
                "Edit history will now be tracked.",
                "success",
            )
        else:
            flash("Task updated.", "success")

        return redirect(url_for("tasks.task_detail", task_id=task.id))

    return render_template(
        "tasks/edit.html",
        task=task,
        users=users,
        PRIORITY_CHOICES=PRIORITY_CHOICES,
    )


# ---------------------------------------------------------------------------
# Version history
# ---------------------------------------------------------------------------

@tasks_bp.route("/<int:task_id>/history")
@login_required
def task_history(task_id):
    task = Task.query.get_or_404(task_id)
    versions = (
        TaskVersion.query.filter_by(task_id=task_id)
        .order_by(TaskVersion.version_number.desc())
        .all()
    )
    return render_template("tasks/history.html", task=task, versions=versions)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@tasks_bp.route("/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.created_by_id != current_user.id:
        abort(403)
    db.session.delete(task)
    db.session.commit()
    flash("Task deleted.", "info")
    return redirect(url_for("tasks.list_tasks"))
