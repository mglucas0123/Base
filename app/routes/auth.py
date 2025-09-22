
from flask import Blueprint, render_template, request, redirect, session, url_for, flash
from werkzeug.security import check_password_hash
from flask_login import login_user, logout_user, login_required 
from app.models import db, User

auth_bp = Blueprint('auth', __name__, template_folder='../templates')

#<!--- LOGIN --->
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("username")
        senha = request.form.get("password")

        user = db.session.execute(db.select(User).filter_by(username=usuario)).scalar_one_or_none()

        if user and user.is_active and check_password_hash(user.password, senha):
            # Ensure fs_uniquifier is set for Flask-Security compatibility
            if not getattr(user, 'fs_uniquifier', None):
                import secrets
                user.fs_uniquifier = secrets.token_hex(16)
                db.session.commit()
            login_user(user)
            
            # Login realizado com sucesso
            
            next_page = request.args.get('next')
            # Only allow local redirects to avoid issues
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for("main.panel"))
        else:
            flash("Usuário ou senha inválidos.", "danger")

    return render_template("login.html")

#<!--- LOGOUT --->
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Você foi desconectado com sucesso.", "info")
    return redirect(url_for("auth.login"))