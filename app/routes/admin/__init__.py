from flask import Blueprint, redirect, url_for
from flask_login import login_required
from .utils import admin_required

from .users import users_bp
from .roles import roles_bp
# Blueprints removidos: notices, repositories, courses, quiz
# Mantendo apenas gerenciamento de usuários

def create_admin_blueprint():    
    admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
    
    admin_bp.register_blueprint(users_bp)
    admin_bp.register_blueprint(roles_bp)
    # Registrando apenas blueprint de usuários
    
    @admin_bp.route("/")
    @login_required
    @admin_required
    def admin_dashboard():
        """Dashboard principal do admin"""
        return redirect(url_for('admin.users.list_users'))
    
    return admin_bp
