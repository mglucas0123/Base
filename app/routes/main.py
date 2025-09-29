from flask import Blueprint, render_template, redirect, session, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, select
from app.models import db, Formulario, User
from datetime import date, timedelta

main_bp = Blueprint('main', __name__, template_folder='../templates')

@main_bp.route("/")
def index():
    return redirect(url_for("main.panel"))

#<-- PAINEL PRINCIPAL -->
@main_bp.route("/panel")
@login_required
def panel():
    dados_dashboard = {}
    
    dados_dashboard['labels_grafico'] = []
    dados_dashboard['data_grafico'] = []
    
    if 'ADMIN' in current_user.profile or 'VER_RELATORIOS' in current_user.profile:
        stmt_em_analise = db.select(func.count(Formulario.id)).where(Formulario.status == 'EM_ANALISE')
        dados_dashboard['formularios_em_analise'] = db.session.execute(stmt_em_analise).scalar_one_or_none() or 0
        
        hoje = date.today()
        stmt_agendados_hoje = db.select(func.count(Formulario.id)).where(
            Formulario.status == 'AGENDADO',
            Formulario.data_atendimento == hoje
        )
        dados_dashboard['agendados_hoje'] = db.session.execute(stmt_agendados_hoje).scalar_one_or_none() or 0
        dados_dashboard['data_hoje'] = hoje.isoformat()
        
        data_inicio_grafico = date.today() - timedelta(days=30)
        stmt_grafico = db.select(Formulario.especialidade, func.count(Formulario.id).label('total'))\
            .where(Formulario.data_registro >= data_inicio_grafico)\
            .group_by(Formulario.especialidade)\
            .order_by(func.count(Formulario.id).desc())\
            .limit(6)
        resultados_grafico = db.session.execute(stmt_grafico).all()
        dados_dashboard['labels_grafico'] = [r.especialidade for r in resultados_grafico]
        dados_dashboard['data_grafico'] = [r.total for r in resultados_grafico]

    if 'ADMIN' in current_user.profile:
        stmt_total_users = db.select(func.count(User.id))
        dados_dashboard['total_usuarios'] = db.session.execute(stmt_total_users).scalar_one_or_none() or 0
            
    if 'CRIAR_RELATORIOS' in current_user.profile:
        stmt_meus_envios = db.select(Formulario)\
            .where(Formulario.funcionario_id == current_user.id)\
            .order_by(Formulario.data_registro.desc())\
            .limit(5)
        meus_envios = db.session.execute(stmt_meus_envios).scalars().all()
        dados_dashboard['meus_envios'] = meus_envios
    return render_template("panel.html", dados_dashboard=dados_dashboard)