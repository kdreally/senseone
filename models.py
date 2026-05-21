from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# Statuses where versioning kicks in
VERSIONED_STATUSES = {"final", "published"}

TASK_STATUSES = [
    ("draft", "Draft"),
    ("in_progress", "In Progress"),
    ("review", "Review"),
    ("final", "Final Save"),
    ("published", "Published"),
]


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tasks_created = db.relationship(
        "Task", foreign_keys="Task.created_by_id", back_populates="creator"
    )
    tasks_assigned = db.relationship(
        "Task", foreign_keys="Task.assigned_to_id", back_populates="assignee"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    status = db.Column(db.String(20), default="draft", nullable=False)
    priority = db.Column(db.String(10), default="medium", nullable=False)
    due_date = db.Column(db.Date, nullable=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    creator = db.relationship(
        "User", foreign_keys=[created_by_id], back_populates="tasks_created"
    )
    assignee = db.relationship(
        "User", foreign_keys=[assigned_to_id], back_populates="tasks_assigned"
    )
    versions = db.relationship(
        "TaskVersion", back_populates="task", order_by="TaskVersion.version_number"
    )

    @property
    def is_versioned(self):
        """True when the task is in a status that requires change tracking."""
        return self.status in VERSIONED_STATUSES

    @property
    def latest_version(self):
        return self.versions[-1] if self.versions else None

    def __repr__(self):
        return f"<Task {self.id}: {self.title}>"


class TaskVersion(db.Model):
    """Immutable snapshot of a Task recorded after each edit once the task
    has reached 'final' or 'published' status."""

    __tablename__ = "task_versions"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    status = db.Column(db.String(20), nullable=False)
    priority = db.Column(db.String(10), nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    changed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    changed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    change_note = db.Column(db.String(500), default="")

    task = db.relationship("Task", back_populates="versions")
    changed_by = db.relationship("User", foreign_keys=[changed_by_id])
    assignee_snapshot = db.relationship("User", foreign_keys=[assigned_to_id])

    def __repr__(self):
        return f"<TaskVersion task={self.task_id} v{self.version_number}>"
