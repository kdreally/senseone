# SenseOne — Productivity Task Manager

A Flask-based productivity task manager with task assigning, refinement, and version-tracked editing.

## Features

- **User accounts** — register, login, logout
- **Task management** — create, view, edit, delete tasks with title, description, priority, due date
- **Task assignment** — assign tasks to team members
- **Status workflow** — `Draft → In Progress → Review → Final Save → Published`
- **Draft-mode editing (no versioning)** — freely refine tasks while they are in `Draft`, `In Progress`, or `Review` status without any history being recorded
- **Version tracking** — once a task reaches **Final Save** or **Published** status, every subsequent edit is recorded as an immutable snapshot with a timestamp, the editor's name, and an optional change note
- **Edit history** — browse the full version history of any tracked task
- **Team page** — see all users, their assigned tasks and created tasks
- **Filtering** — filter tasks by status, priority, and assignment

## Tech Stack

- Python 3.10+ / [Flask](https://flask.palletsprojects.com/)
- [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/) + SQLite (swappable for Postgres)
- [Flask-Login](https://flask-login.readthedocs.io/) for session management
- Jinja2 server-rendered templates (no JavaScript framework)

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
SECRET_KEY="change-me-in-production" flask run
```

Open http://127.0.0.1:5000 in your browser.

## Project Structure

```
senseone/
├── app.py              # Flask application factory & main entry point
├── models.py           # SQLAlchemy models: User, Task, TaskVersion
├── routes/
│   ├── auth.py         # Register / login / logout
│   ├── tasks.py        # Task CRUD + version snapshot logic
│   └── users.py        # Team listing & user profiles
├── templates/
│   ├── base.html
│   ├── auth/           # login.html, register.html
│   ├── tasks/          # list, create, detail, edit, history
│   └── users/          # list, profile
├── static/css/
│   └── main.css
└── requirements.txt
```

## Versioning Logic

| Task status | Edits tracked? |
|-------------|---------------|
| Draft | ✗ No — freely edit without history |
| In Progress | ✗ No |
| Review | ✗ No |
| **Final Save** | ✓ Yes — every save creates a new version entry |
| **Published** | ✓ Yes |

The first save that moves a task into `Final Save` or `Published` creates version **v1**. Every subsequent save increments the version counter. Each version snapshot captures the full task state (title, description, priority, assignee, due date, status) plus the editor and an optional change note.
