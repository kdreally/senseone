from flask import Blueprint, render_template
from flask_login import login_required
from models import User, Task

users_bp = Blueprint("users", __name__, url_prefix="/users")


@users_bp.route("/")
@login_required
def list_users():
    users = User.query.order_by(User.username).all()
    return render_template("users/list.html", users=users)


@users_bp.route("/<int:user_id>")
@login_required
def user_profile(user_id):
    user = User.query.get_or_404(user_id)
    assigned = Task.query.filter_by(assigned_to_id=user_id).order_by(Task.updated_at.desc()).all()
    created = Task.query.filter_by(created_by_id=user_id).order_by(Task.updated_at.desc()).all()
    return render_template("users/profile.html", profile_user=user, assigned=assigned, created=created)
