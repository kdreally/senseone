import os
from datetime import datetime, timezone
from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    abort,
)
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from models import db, User, Task, TaskVersion, TASK_STATUSES, VERSIONED_STATUSES

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app(config=None):
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config.setdefault(
        "SQLALCHEMY_DATABASE_URI",
        os.environ.get("DATABASE_URL", "sqlite:///taskmanager.db"),
    )
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)

    if config:
        app.config.update(config)

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    with app.app_context():
        db.create_all()

    # Register blueprints
    from routes.auth import auth_bp
    from routes.tasks import tasks_bp
    from routes.users import users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(users_bp)

    # Context processor: make TASK_STATUSES available in every template
    @app.context_processor
    def inject_globals():
        return {
            "TASK_STATUSES": TASK_STATUSES,
            "VERSIONED_STATUSES": VERSIONED_STATUSES,
            "now": datetime.now(timezone.utc),
        }

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("tasks.list_tasks"))
        return redirect(url_for("auth.login"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
