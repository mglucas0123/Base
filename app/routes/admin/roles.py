from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import db, Role, PermissionCatalog
from .utils import admin_required, handle_database_error

roles_bp = Blueprint('roles', __name__, url_prefix='/roles')


@roles_bp.route('/permissions', methods=['GET'])
@login_required
@admin_required
def permissions_page():
    roles = Role.query.order_by(Role.name.asc()).all()
    catalog = [p.name for p in PermissionCatalog.query.order_by(PermissionCatalog.name.asc()).all()]
    return render_template('roles_permissions.html', roles=roles, catalog=catalog)


@roles_bp.route('/permissions/<int:role_id>', methods=['POST'])
@login_required
@admin_required
@handle_database_error('atualizar permissões da role')
def update_role_permissions(role_id: int):
    role = Role.query.get_or_404(role_id)

    # Lista marcada no formulário
    selected = request.form.getlist('permissions')

    # Normaliza e remove vazios/duplicados
    normalized = []
    for p in selected:
        p = (p or '').strip()
        if p and p not in normalized:
            normalized.append(p)

    # Validate against catalog - only allow permissions that exist in catalog
    catalog_set = {p.name for p in PermissionCatalog.query.all()}
    normalized = [p for p in normalized if p in catalog_set]

    # Lock Admin role to only 'admin-total'
    if role.name and role.name.lower() in ('administrador', 'admin'):
        normalized = ['admin-total'] if 'admin-total' in catalog_set else []

    role.permissions = normalized
    db.session.commit()

    flash(f"Permissões da role '{role.name}' atualizadas!", 'success')
    return redirect(url_for('admin.roles.permissions_page'))


@roles_bp.route('/create', methods=['POST'])
@login_required
@admin_required
@handle_database_error('criar role')
def create_role():
    name = (request.form.get('role_name') or '').strip()
    description = (request.form.get('role_description') or '').strip()
    sector = (request.form.get('role_sector') or '').strip()
    initial_perms = request.form.getlist('role_permissions')

    if not name:
        flash('Nome da role é obrigatório.', 'warning')
        return redirect(url_for('admin.roles.permissions_page'))

    # Unicidade por nome
    if Role.query.filter_by(name=name).first():
        flash('Já existe uma role com este nome.', 'warning')
        return redirect(url_for('admin.roles.permissions_page'))

    # Normaliza permissões
    perms_norm = []
    for p in initial_perms:
        p = (p or '').strip()
        if p and p not in perms_norm:
            perms_norm.append(p)

    # Filter by catalog
    catalog_set = {p.name for p in PermissionCatalog.query.all()}
    perms_norm = [p for p in perms_norm if p in catalog_set]

    role = Role(name=name, description=description or None, sector=sector or None)
    role.permissions = perms_norm
    db.session.add(role)
    db.session.commit()

    flash(f"Role '{name}' criada com sucesso!", 'success')
    return redirect(url_for('admin.roles.permissions_page'))


@roles_bp.route('/<int:role_id>/delete', methods=['POST'])
@login_required
@admin_required
@handle_database_error('excluir role')
def delete_role(role_id: int):
    role = Role.query.get_or_404(role_id)

    # Impede excluir a role Administrador por segurança (opcional)
    if role.name.lower() in ('administrador', 'admin'):
        flash('Não é permitido excluir a role Administrador.', 'warning')
        return redirect(url_for('admin.roles.permissions_page'))

    # Desanexar dos usuários
    for u in list(role.users):
        u.roles.remove(role)

    db.session.delete(role)
    db.session.commit()
    flash(f"Role '{role.name}' excluída com sucesso!", 'success')
    return redirect(url_for('admin.roles.permissions_page'))

@roles_bp.route('/catalog/add', methods=['POST'])
@login_required
@admin_required
@handle_database_error('adicionar permissão no catálogo')
def add_permission_to_catalog():
    name = (request.form.get('permission_name') or '').strip()
    if name == 'admin-total':
        # ensure it exists - idempotent
        if not PermissionCatalog.query.filter_by(name=name).first():
            db.session.add(PermissionCatalog(name=name))
            db.session.commit()
        flash('Permissão admin-total já é obrigatória no catálogo.', 'info')
        return redirect(url_for('admin.roles.permissions_page'))
    if not name:
        flash('Informe um nome de permissão.', 'warning')
        return redirect(url_for('admin.roles.permissions_page'))

    # Enforce kebab-case pattern
    import re
    if not re.fullmatch(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', name):
        flash('Permissão inválida. Use kebab-case (letras minúsculas, números e hífen).', 'warning')
        return redirect(url_for('admin.roles.permissions_page'))

    if PermissionCatalog.query.filter_by(name=name).first():
        flash('Já existe essa permissão no catálogo.', 'info')
        return redirect(url_for('admin.roles.permissions_page'))

    db.session.add(PermissionCatalog(name=name))
    db.session.commit()
    flash(f"Permissão '{name}' adicionada ao catálogo.", 'success')
    return redirect(url_for('admin.roles.permissions_page'))


@roles_bp.route('/catalog/<string:name>/delete', methods=['POST'])
@login_required
@admin_required
@handle_database_error('excluir permissão do catálogo')
def delete_permission_from_catalog(name: str):
    name = (name or '').strip()
    if name == 'admin-total':
        flash('A permissão admin-total é obrigatória e não pode ser excluída.', 'warning')
        return redirect(url_for('admin.roles.permissions_page'))
    perm = PermissionCatalog.query.filter_by(name=name).first()
    if not perm:
        flash('Permissão não encontrada no catálogo.', 'warning')
        return redirect(url_for('admin.roles.permissions_page'))

    # Remove from roles as well, so DB remains consistent
    roles = Role.query.all()
    for r in roles:
        if r.permissions:
            r.permissions = [p for p in r.permissions if p != name]
    db.session.delete(perm)
    db.session.commit()
    flash(f"Permissão '{name}' removida do catálogo e desatribuída das roles.", 'success')
    return redirect(url_for('admin.roles.permissions_page'))
