from flask import Blueprint, render_template, redirect, session, url_for, flash
from flask_login import login_required, current_user
from app.models import db

main_bp = Blueprint('main', __name__, template_folder='../templates')

@main_bp.route("/")
def index():
    return redirect(url_for("main.panel"))

#<-- PAINEL PRINCIPAL -->
@main_bp.route("/panel")
@login_required
def panel():
    # Painel simplificado sem avisos/notificações
    return render_template("panel.html")