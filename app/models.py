import enum
from flask import url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from flask_security import UserMixin as FSUserMixin, RoleMixin
from flask_security import AsaList
from sqlalchemy.ext.mutable import MutableList

db = SQLAlchemy()

user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True)
)

class Role(db.Model, RoleMixin):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    sector = db.Column(db.String(50), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    permissions = db.Column(MutableList.as_mutable(AsaList()), nullable=True, default=list)
    
    def has_permission(self, permission_name):
        if self.permissions and permission_name in set(self.permissions):
            return True
        return False
    
    def __repr__(self):
        return f'<Role {self.name}>'

class User(db.Model, FSUserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    profile = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    creation_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    fs_uniquifier = db.Column(db.String(64), unique=True, nullable=True)
    
    roles = db.relationship('Role', secondary=user_roles, backref='users')

    @property
    def active(self):
        return self.is_active

    @active.setter
    def active(self, value: bool):
        self.is_active = bool(value)
    
    def has_permission(self, permission_name):
        """Check permission via Flask-Security role permissions only."""
        try:
            if super().has_permission(permission_name):
                return True
        except Exception:
            pass
        for role in self.roles:
            if role.has_permission(permission_name):
                return True
        return False
    
    def get_permissions(self):
        """Retorna todas as permissões do usuário (diretas + através de papéis)"""
        permissions = set()
        
        for role in self.roles:
            if role.permissions:
                for perm_name in role.permissions:
                    permissions.add(perm_name)
        
        return list(permissions)

    def __repr__(self):
        return f'<User {self.username}>'


class PermissionCatalog(db.Model):
    __tablename__ = 'permission_catalog'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<Permission {self.name}>'

class Formulario(db.Model):
    __tablename__ = 'formulario'
    id = db.Column(db.Integer, primary_key=True)
    data_registro = db.Column(db.DateTime, nullable=False)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    nome_paciente = db.Column(db.String(100), nullable=False)
    nascimento = db.Column(db.Date, nullable=False)
    cpf = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(30), default="EM_ANALISE", nullable=False)
    unidade_saude = db.Column(db.String(100), nullable=False)
    medico_solicitante = db.Column(db.String(100), nullable=False)
    especialidade = db.Column(db.String(100), nullable=False)
    anexo = db.Column(db.String(200), nullable=True)
    medico_atendimento = db.Column(db.String(100), nullable=True)
    data_atendimento = db.Column(db.Date, nullable=True)
    hora_agendamento = db.Column(db.String(10), nullable=True)
    local_destino = db.Column(db.String(100), nullable=True)
    observacao = db.Column(db.Text, nullable=True)
    autorizador_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    assinatura = db.Column(db.String(200), nullable=True)
    pdf = db.Column(db.String(200), nullable=True)
    # Workflow: Regulação e Ambulatório
    justificativa_negativa = db.Column(db.Text, nullable=True)
    compareceu = db.Column(db.Boolean, nullable=True)
    procedimento_realizado = db.Column(db.Boolean, nullable=True)
    resultado_procedimento = db.Column(db.Text, nullable=True)

    funcionario = db.relationship('User', foreign_keys=[funcionario_id], backref="formularios_criados")
    autorizador = db.relationship('User', foreign_keys=[autorizador_id], backref="formularios_autorizados")


class UnidadeSaude(db.Model):
    __tablename__ = 'unidade_saude'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    status = db.Column(db.String(20), default='ATIVA', nullable=False)
    data_ultimo_atendimento = db.Column(db.Date, nullable=True)