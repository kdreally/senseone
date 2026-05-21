"""Tests for the SenseOne task manager — versioning logic and routes."""
import pytest
from app import create_app
from models import db as _db, User, Task, TaskVersion, VERSIONED_STATUSES
from routes.tasks import _snapshot_task


@pytest.fixture()
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-secret",
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def two_users(app):
    with app.app_context():
        u1 = User(username="alice", email="alice@example.com")
        u1.set_password("pass")
        u2 = User(username="bob", email="bob@example.com")
        u2.set_password("pass")
        _db.session.add_all([u1, u2])
        _db.session.commit()
        yield u1.id, u2.id


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestVersioningLogic:
    def test_draft_task_not_versioned(self, app, two_users):
        uid1, uid2 = two_users
        with app.app_context():
            task = Task(
                title="Draft task",
                status="draft",
                priority="medium",
                created_by_id=uid1,
                assigned_to_id=uid2,
            )
            _db.session.add(task)
            _db.session.commit()
            assert task.is_versioned is False
            assert len(task.versions) == 0

    def test_in_progress_task_not_versioned(self, app, two_users):
        uid1, _ = two_users
        with app.app_context():
            task = Task(title="WIP", status="in_progress", priority="low", created_by_id=uid1)
            _db.session.add(task)
            _db.session.commit()
            assert task.is_versioned is False

    def test_final_task_is_versioned(self, app, two_users):
        uid1, _ = two_users
        with app.app_context():
            task = Task(title="Done", status="final", priority="high", created_by_id=uid1)
            _db.session.add(task)
            _db.session.commit()
            assert task.is_versioned is True

    def test_published_task_is_versioned(self, app, two_users):
        uid1, _ = two_users
        with app.app_context():
            task = Task(title="Live", status="published", priority="high", created_by_id=uid1)
            _db.session.add(task)
            _db.session.commit()
            assert task.is_versioned is True

    def test_snapshot_creates_version_record(self, app, two_users):
        uid1, _ = two_users
        with app.app_context():
            user = _db.session.get(User, uid1)
            task = Task(title="Snap me", status="final", priority="medium", created_by_id=uid1)
            _db.session.add(task)
            _db.session.commit()

            _snapshot_task(task, user, "initial final save")
            _db.session.commit()

            assert len(task.versions) == 1
            v = task.versions[0]
            assert v.version_number == 1
            assert v.change_note == "initial final save"
            assert v.title == "Snap me"

    def test_multiple_snapshots_increment_version(self, app, two_users):
        uid1, uid2 = two_users
        with app.app_context():
            u1 = _db.session.get(User, uid1)
            u2 = _db.session.get(User, uid2)
            task = Task(title="Evolving", status="published", priority="high", created_by_id=uid1)
            _db.session.add(task)
            _db.session.commit()

            _snapshot_task(task, u1, "v1 note")
            _db.session.commit()
            task.title = "Evolving (updated)"
            _snapshot_task(task, u2, "v2 note")
            _db.session.commit()

            assert len(task.versions) == 2
            assert task.versions[0].version_number == 1
            assert task.versions[1].version_number == 2
            assert task.latest_version.version_number == 2

    def test_no_snapshot_for_draft_edits(self, app, two_users):
        uid1, _ = two_users
        with app.app_context():
            task = Task(title="Draft", status="draft", priority="low", created_by_id=uid1)
            _db.session.add(task)
            _db.session.commit()

            # Simulate free-form edits with no snapshot
            task.title = "Draft v2"
            task.description = "More detail"
            _db.session.commit()

            assert len(task.versions) == 0, "Draft edits must NOT create versions"

    def test_versioned_statuses_constant(self):
        assert "final" in VERSIONED_STATUSES
        assert "published" in VERSIONED_STATUSES
        assert "draft" not in VERSIONED_STATUSES
        assert "in_progress" not in VERSIONED_STATUSES
        assert "review" not in VERSIONED_STATUSES


# ---------------------------------------------------------------------------
# Auth route tests
# ---------------------------------------------------------------------------

class TestAuth:
    def test_register_and_login(self, client):
        rv = client.post(
            "/auth/register",
            data={
                "username": "tester",
                "email": "tester@example.com",
                "password": "secret123",
                "confirm_password": "secret123",
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200
        assert b"Account created" in rv.data or b"log in" in rv.data.lower()

        rv = client.post(
            "/auth/login",
            data={"username": "tester", "password": "secret123"},
            follow_redirects=True,
        )
        assert rv.status_code == 200

    def test_login_invalid_password(self, client, app, two_users):
        rv = client.post(
            "/auth/login",
            data={"username": "alice", "password": "wrongpass"},
            follow_redirects=True,
        )
        assert rv.status_code == 200
        assert b"Invalid" in rv.data

    def test_register_duplicate_username(self, client, app, two_users):
        rv = client.post(
            "/auth/register",
            data={
                "username": "alice",
                "email": "other@example.com",
                "password": "pass123",
                "confirm_password": "pass123",
            },
            follow_redirects=True,
        )
        assert b"taken" in rv.data.lower() or b"already" in rv.data.lower()

    def test_password_mismatch(self, client):
        rv = client.post(
            "/auth/register",
            data={
                "username": "newuser",
                "email": "new@example.com",
                "password": "abc",
                "confirm_password": "xyz",
            },
            follow_redirects=True,
        )
        assert b"match" in rv.data.lower()


# ---------------------------------------------------------------------------
# Task route tests
# ---------------------------------------------------------------------------

def _login(client, username="alice", password="pass"):
    client.post(
        "/auth/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


class TestTaskRoutes:
    def test_task_list_requires_login(self, client):
        rv = client.get("/tasks/", follow_redirects=False)
        assert rv.status_code == 302
        assert "/auth/login" in rv.headers.get("Location", "")

    def test_create_and_view_task(self, client, app, two_users):
        uid1, uid2 = two_users
        _login(client)

        rv = client.post(
            "/tasks/new",
            data={
                "title": "My first task",
                "description": "Some work",
                "priority": "high",
                "due_date": "2026-12-31",
                "assigned_to_id": str(uid2),
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200
        assert b"My first task" in rv.data

    def test_edit_draft_task_no_version_created(self, client, app, two_users):
        uid1, _ = two_users
        with app.app_context():
            task = Task(title="Draft", status="draft", priority="low", created_by_id=uid1)
            _db.session.add(task)
            _db.session.commit()
            task_id = task.id

        _login(client)
        rv = client.post(
            f"/tasks/{task_id}/edit",
            data={
                "title": "Draft updated",
                "description": "Still drafting",
                "priority": "low",
                "status": "draft",  # stays in draft
                "assigned_to_id": "",
                "due_date": "",
                "change_note": "",
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200

        with app.app_context():
            task = _db.session.get(Task, task_id)
            assert task.title == "Draft updated"
            assert len(task.versions) == 0, "No version should be created for draft edits"

    def test_transition_to_final_creates_version(self, client, app, two_users):
        uid1, _ = two_users
        with app.app_context():
            task = Task(title="Report", status="draft", priority="medium", created_by_id=uid1)
            _db.session.add(task)
            _db.session.commit()
            task_id = task.id

        _login(client)
        rv = client.post(
            f"/tasks/{task_id}/edit",
            data={
                "title": "Report",
                "description": "Finalized",
                "priority": "medium",
                "status": "final",  # transition to final
                "assigned_to_id": "",
                "due_date": "",
                "change_note": "Ready for review",
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200

        with app.app_context():
            task = _db.session.get(Task, task_id)
            assert task.status == "final"
            assert len(task.versions) == 1
            assert task.versions[0].change_note == "Ready for review"

    def test_edit_published_task_creates_version(self, client, app, two_users):
        uid1, _ = two_users
        with app.app_context():
            task = Task(title="Live", status="published", priority="high", created_by_id=uid1)
            _db.session.add(task)
            _db.session.commit()
            task_id = task.id

        _login(client)
        # First edit on published task
        client.post(
            f"/tasks/{task_id}/edit",
            data={
                "title": "Live (v2)",
                "description": "Updated",
                "priority": "high",
                "status": "published",
                "assigned_to_id": "",
                "due_date": "",
                "change_note": "Minor update",
            },
            follow_redirects=True,
        )
        # Second edit
        client.post(
            f"/tasks/{task_id}/edit",
            data={
                "title": "Live (v3)",
                "description": "Updated again",
                "priority": "high",
                "status": "published",
                "assigned_to_id": "",
                "due_date": "",
                "change_note": "Another update",
            },
            follow_redirects=True,
        )

        with app.app_context():
            task = _db.session.get(Task, task_id)
            assert len(task.versions) == 2
            assert task.versions[0].version_number == 1
            assert task.versions[1].version_number == 2

    def test_history_page_shows_versions(self, client, app, two_users):
        uid1, _ = two_users
        with app.app_context():
            u1 = _db.session.get(User, uid1)
            task = Task(title="Hist", status="published", priority="low", created_by_id=uid1)
            _db.session.add(task)
            _db.session.commit()
            _snapshot_task(task, u1, "first snapshot")
            _db.session.commit()
            task_id = task.id

        _login(client)
        rv = client.get(f"/tasks/{task_id}/history")
        assert rv.status_code == 200
        assert b"first snapshot" in rv.data

    def test_delete_task_by_creator(self, client, app, two_users):
        uid1, _ = two_users
        with app.app_context():
            task = Task(title="To delete", status="draft", priority="low", created_by_id=uid1)
            _db.session.add(task)
            _db.session.commit()
            task_id = task.id

        _login(client)
        rv = client.post(f"/tasks/{task_id}/delete", follow_redirects=True)
        assert rv.status_code == 200

        with app.app_context():
            assert _db.session.get(Task, task_id) is None

    def test_delete_task_forbidden_for_non_creator(self, client, app, two_users):
        uid1, uid2 = two_users
        with app.app_context():
            task = Task(title="Others task", status="draft", priority="low", created_by_id=uid2)
            _db.session.add(task)
            _db.session.commit()
            task_id = task.id

        _login(client, username="alice")  # alice, not creator (bob)
        rv = client.post(f"/tasks/{task_id}/delete", follow_redirects=False)
        assert rv.status_code == 403
