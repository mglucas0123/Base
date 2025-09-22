from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user
from app.models import db, Role, PermissionCatalog

class RBACManager:
        
    @staticmethod
    def init_default_permissions():
        """Retorna a lista padrão e garante que constem no catálogo persistido."""
        defaults = ['admin-total', 'manage-users', 'view-users', 'access-panel', 'change-password']
        # Ensure DB catalog has these
        for p in defaults:
            if not PermissionCatalog.query.filter_by(name=p).first():
                db.session.add(PermissionCatalog(name=p))
        db.session.commit()
        return defaults

    @staticmethod
    def init_default_roles():
        """Inicializa apenas os papéis essenciais para a base"""
        default_roles = [
            {
                'name': 'Administrador', 
                'description': 'Acesso total ao sistema', 
                'sector': 'TI',
                'permissions': ['admin-total']
            },
            {
                'name': 'Usuário', 
                'description': 'Usuário padrão do sistema', 
                'sector': 'GERAL',
                'permissions': ['access-panel', 'change-password']
            },
        ]
        
        for role_data in default_roles:
            if not Role.query.filter_by(name=role_data['name']).first():
                role = Role(
                    name=role_data['name'],
                    description=role_data['description'],
                    sector=role_data['sector']
                )
                
                for perm_name in role_data['permissions']:
                    if role.permissions is None:
                        role.permissions = []
                    if perm_name not in (role.permissions or []):
                        role.permissions.append(perm_name)
                
                db.session.add(role)
        
        db.session.commit()

def require_permission(permission_name):
    """Decorator para verificar se o usuário possui uma permissão específica"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            if current_user.has_permission('admin-total'):
                return f(*args, **kwargs)
            
            if not current_user.has_permission(permission_name):
                flash(f"Acesso negado! Você não possui a permissão '{permission_name}' necessária.", "danger")
                return redirect(url_for('main.panel'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Module access checks removed with legacy Permission model. Use fine-grained permissions if needed.

def require_any_permission(permission_list):
    """Decorator para verificar se o usuário possui pelo menos uma das permissões da lista"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            if current_user.has_permission('admin-total'):
                return f(*args, **kwargs)
            
            has_permission = any(current_user.has_permission(perm) for perm in permission_list)
            
            if not has_permission:
                flash("Acesso negado! Você não possui as permissões necessárias.", "danger")
                return redirect(url_for('main.panel'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def initialize_rbac():
    """Inicializa o sistema RBAC completo"""
    try:
        # Garante catálogo e roles base
        RBACManager.init_default_permissions()
        RBACManager.init_default_roles()
        print("Sistema RBAC inicializado com sucesso!")
    except Exception as e:
        print(f"Erro ao inicializar RBAC: {str(e)}")
        db.session.rollback()
        raise

def assign_role_to_user(user, role_name):
    """Atribui um papel específico a um usuário"""
    try:
        role = Role.query.filter_by(name=role_name).first()
        if role and role not in user.roles:
            user.roles.append(role)
            db.session.commit()
            return True
        elif role and role in user.roles:
            return True
        else:
            print(f"Papel '{role_name}' não encontrado")
            return False
    except Exception as e:
        print(f"Erro ao atribuir papel: {str(e)}")
        db.session.rollback()
        return False