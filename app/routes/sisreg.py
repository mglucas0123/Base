from datetime import datetime, timedelta, date
from flask import Blueprint, flash, redirect, render_template, request, session, url_for, abort, jsonify, current_app
from flask_login import current_user, login_required
from sqlalchemy import Date, cast, select, func, or_, case
from ..models import db, Formulario, User
import os
import sqlite3
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


def _now_brasilia() -> datetime:
    """Return current datetime in Brasília timezone (America/Sao_Paulo).
    Falls back to UTC-3 if IANA tz database is unavailable (e.g., Windows without tzdata).
    """
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("America/Sao_Paulo"))
        except Exception:
            pass
    # Fallback: approximate Brasília time as UTC-3 (no DST handling)
    return datetime.utcnow() - timedelta(hours=3)

sisreg_bp = Blueprint('sisreg', __name__, template_folder='../templates')
 
@sisreg_bp.route("/meus-trabalhos")
@login_required
def meus_trabalhos():
    profile = current_user.profile or ""
    if ("ALTERAR_STATUS" in profile) or ("ADMIN" in profile) or ("REGULACAO" in profile):
        return redirect(url_for('sisreg.setor_regulacao_lista'))
    if ("VER_RELATORIOS" in profile) or ("AMBULATORIO" in profile):
        return redirect(url_for('sisreg.setor_ambulatorio_lista'))
    if "CRIAR_RELATORIOS" in profile:
        return redirect(url_for('sisreg.formularios'))
    return redirect(url_for('main.panel'))

@sisreg_bp.route("/novo_formulario", methods=["GET", "POST"])
@login_required
def novo_formulario():
    
    if "CRIAR_RELATORIOS" not in current_user.profile and "ADMIN" not in current_user.profile:
        flash("Acesso negado! Você não tem permissão para criar novos formulários.", "danger")
        return redirect(url_for("main.panel"))

    if request.method == "POST":
        try:
            cpf_val = request.form.get("cpf") or request.form.get("cartao_sus")

            form = Formulario(
                data_registro=datetime.utcnow(),
                funcionario_id=current_user.id,
                nome_paciente=request.form["nome_paciente"],
                nascimento=datetime.strptime(request.form["nascimento"], "%Y-%m-%d").date(),
                cpf=cpf_val,
                status="EM_ANALISE",
                unidade_saude=request.form["unidade_saude"],
                medico_solicitante=request.form["medico_solicitante"],
                especialidade=request.form["especialidade"],
                observacao=request.form.get("observacao")
            )
            db.session.add(form)
            db.session.commit()
            flash("Formulário enviado com sucesso!", "success")
            return redirect(url_for("main.panel"))
        
        except KeyError as e:
            flash(f"Erro no formulário: campo obrigatório '{e.name}' ausente.", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Ocorreu um erro ao salvar o formulário: {str(e)}", "danger")

    return render_template("novo_formulario.html")


@sisreg_bp.get("/api/pacientes/busca")
@login_required
def buscar_pacientes():
    if "CRIAR_RELATORIOS" not in current_user.profile and "ADMIN" not in current_user.profile:
        return jsonify({"error": "forbidden"}), 403

    q = (request.args.get("q", "") or "").strip()
    if len(q) < 2:
        return jsonify([])

    db_path = os.path.join(current_app.instance_path, "pacientes.db")
    if not os.path.exists(db_path):
        return jsonify({"error": "database_not_found", "detail": db_path}), 500

    q_lower = q.lower()
    like_nome = f"%{q_lower}%"
    digits = "".join(ch for ch in q if ch.isdigit())
    like_digits = f"%{digits}%" if digits else like_nome

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        sql = (
            """
            SELECT id, nome, cpf, cns, data_nascimento
            FROM pacientes_paciente
            WHERE (
                lower(nome) LIKE ?
                OR replace(replace(replace(ifnull(cpf,''), '.', ''), '-', ''), ' ', '') LIKE ?
                OR replace(replace(replace(ifnull(cns,''), '.', ''), '-', ''), ' ', '') LIKE ?
                OR ifnull(cpf,'') LIKE ?
                OR ifnull(cns,'') LIKE ?
            )
            ORDER BY nome ASC
            LIMIT 10
            """
        )
        params = (like_nome, like_digits, like_digits, like_digits, like_digits)
        rows = cur.execute(sql, params).fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "nome": r["nome"] or "",
                "cpf": r["cpf"] or "",
                "cns": r["cns"] or "",
                "data_nascimento": r["data_nascimento"] or "",
            })
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": "query_failed", "detail": str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

@sisreg_bp.route("/formularios")
@login_required
def formularios():
    if "VER_RELATORIOS" not in current_user.profile and "ADMIN" not in current_user.profile:
        flash("Acesso negado! Você não tem permissão para visualizar os formulários.", "danger")
        return redirect(url_for("main.panel"))

    status_filtro = request.args.get('status', '').strip()
    data_inicio_str = request.args.get('data_inicio', '').strip()
    data_fim_str = request.args.get('data_fim', '').strip()
    tipo_data = request.args.get('tipo_data', 'registro').strip()

    query = select(Formulario).order_by(Formulario.data_registro.desc())

    if status_filtro:
        query = query.where(Formulario.status == status_filtro.upper())

    if data_inicio_str or data_fim_str:
        if tipo_data == 'agendamento':
            coluna_data = Formulario.data_atendimento
            query = query.where(Formulario.data_atendimento.isnot(None))
            query = query.order_by(Formulario.data_atendimento.desc())
        else:
            coluna_data = cast(Formulario.data_registro, Date)

        if data_inicio_str:
            try:
                data_inicio_obj = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
                query = query.where(coluna_data >= data_inicio_obj)
            except ValueError:
                flash(f"Formato de 'Data Início' inválido: '{data_inicio_str}'.", "warning")
        
        if data_fim_str:
            try:
                data_fim_obj = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
                query = query.where(coluna_data <= data_fim_obj)
            except ValueError:
                flash(f"Formato de 'Data Fim' inválido: '{data_fim_str}'.", "warning")

    todos_formularios = db.session.execute(query).scalars().all()

    return render_template(
        "workflow/requests.html", 
        formularios=todos_formularios, 
        status_atual=status_filtro,
        data_inicio_atual=data_inicio_str,
        data_fim_atual=data_fim_str,
        tipo_data_atual=tipo_data
    )

@sisreg_bp.route("/agenda")
@login_required
def agenda():
    if "VER_RELATORIOS" not in current_user.profile and "ADMIN" not in current_user.profile:
        flash("Acesso negado! Você não tem permissão para visualizar a agenda.", "danger")
        return redirect(url_for("main.panel"))

    hoje = datetime.utcnow().date()
    padrao_inicio = request.args.get('data_inicio', '').strip()
    padrao_fim = request.args.get('data_fim', '').strip()
    medico = request.args.get('medico', '').strip()
    local = request.args.get('local', '').strip()
    especialidade = request.args.get('especialidade', '').strip()

    if padrao_inicio:
        try:
            data_inicio = datetime.strptime(padrao_inicio, '%Y-%m-%d').date()
        except ValueError:
            flash(f"Formato de 'Data Início' inválido: '{padrao_inicio}'.", "warning")
            data_inicio = hoje
    else:
        data_inicio = hoje

    if padrao_fim:
        try:
            data_fim = datetime.strptime(padrao_fim, '%Y-%m-%d').date()
        except ValueError:
            flash(f"Formato de 'Data Fim' inválido: '{padrao_fim}'.", "warning")
            data_fim = hoje + timedelta(days=30)
    else:
        data_fim = hoje + timedelta(days=30)

    query = (
        select(Formulario)
        .where(Formulario.status == 'AGENDADO')
        .where(Formulario.data_atendimento.isnot(None))
        .where(Formulario.data_atendimento >= data_inicio)
        .where(Formulario.data_atendimento <= data_fim)
        .order_by(Formulario.data_atendimento.asc(), Formulario.hora_agendamento.asc())
    )

    if medico:
        query = query.where(Formulario.medico_atendimento.ilike(f"%{medico}%"))
    if local:
        query = query.where(Formulario.local_destino.ilike(f"%{local}%"))
    if especialidade:
        query = query.where(Formulario.especialidade.ilike(f"%{especialidade}%"))

    agendados = db.session.execute(query).scalars().all()

    from collections import OrderedDict
    agendados_ordenados = sorted(
        agendados,
        key=lambda f: ((f.data_atendimento or date.min), (f.hora_agendamento or ""))
    )
    agendados_por_dia: OrderedDict[date, list[Formulario]] = OrderedDict()
    for f in agendados_ordenados:
        chave = f.data_atendimento
        agendados_por_dia.setdefault(chave, []).append(f)

    distinct_medicos = [r[0] for r in db.session.execute(
        select(Formulario.medico_atendimento).where(Formulario.medico_atendimento.isnot(None)).distinct()
    ).all() if r[0]]
    distinct_locais = [r[0] for r in db.session.execute(
        select(Formulario.local_destino).where(Formulario.local_destino.isnot(None)).distinct()
    ).all() if r[0]]
    distinct_especialidades = [r[0] for r in db.session.execute(
        select(Formulario.especialidade).where(Formulario.especialidade.isnot(None)).distinct()
    ).all() if r[0]]

    return render_template(
        "agenda.html",
    agendados_por_dia=agendados_por_dia,
        data_inicio_atual=data_inicio.isoformat(),
        data_fim_atual=data_fim.isoformat(),
        medico_atual=medico,
        local_atual=local,
        especialidade_atual=especialidade,
        opcoes_medicos=sorted(distinct_medicos),
        opcoes_locais=sorted(distinct_locais),
        opcoes_especialidades=sorted(distinct_especialidades),
        quick_ranges={
            'today': {
                'start': hoje.isoformat(),
                'end': hoje.isoformat()
            },
            'this_week': {
                'start': (hoje - timedelta(days=hoje.weekday())).isoformat(),
                'end': (hoje + timedelta(days=(6 - hoje.weekday()))).isoformat()
            },
            'next_30_days': {
                'start': hoje.isoformat(),
                'end': (hoje + timedelta(days=30)).isoformat()
            }
        }
    )
    
@sisreg_bp.route("/formulario/<int:form_id>/detalhes")
@login_required
def detalhes_formulario(form_id):
    formulario = db.session.get(Formulario, form_id)
    if not formulario:
        flash("Formulário não encontrado.", "danger")
        return redirect(url_for('sisreg.formularios'))
    
    can_view_all = "ADMIN" in current_user.profile or "VER_RELATORIOS" in current_user.profile
    is_owner = "CRIAR_RELATORIOS" in current_user.profile and formulario.funcionario_id == current_user.id
    
    if not (can_view_all or is_owner):
        flash("Acesso negado! Você não tem permissão para visualizar os detalhes deste formulário.", "danger")
        return redirect(url_for("sisreg.formularios"))
    
    return render_template("detalhes_formulario.html", formulario=formulario)


@sisreg_bp.route("/formulario/alterar_status/<int:form_id>", methods=["POST"])
@login_required
def alterar_status_formulario(form_id):

    if "ALTERAR_STATUS" not in current_user.profile and "ADMIN" not in current_user.profile:
        flash("Acesso negado! Você não tem permissão para alterar o status dos formulários.", "danger")
        return redirect(url_for("sisreg.detalhes_formulario", form_id=form_id))

    formulario_para_alterar = db.session.get(Formulario, form_id)
    if not formulario_para_alterar:
        flash("Formulário não encontrado.", "danger")
        return redirect(url_for('sisreg.formularios'))

    novo_status = request.form.get("novo_status")
    if not novo_status:
        flash("Novo status inválido ou não fornecido.", "warning")
        return redirect(url_for("sisreg.detalhes_formulario", form_id=form_id))
    
    status_validos = ["EM_ANALISE", "PENDENTE", "CONCLUIDO", "CANCELADO"]
    if novo_status.upper() not in status_validos:
        flash(f"Status '{novo_status}' é inválido.", "warning")
        return redirect(url_for("sisreg.detalhes_formulario", form_id=form_id))

    formulario_para_alterar.status = novo_status.upper()
    try:
        db.session.commit()
        flash(f"Status do formulário ID {formulario_para_alterar.id} atualizado para '{formulario_para_alterar.status}'.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao atualizar status: {str(e)}", "danger")
    
    return redirect(url_for("sisreg.detalhes_formulario", form_id=form_id))

@sisreg_bp.route('/formulario/<int:form_id>/atualizar', methods=['POST'])
@login_required
def atualizar_formulario(form_id):
    form_to_update = db.session.get(Formulario, form_id)
    if not form_to_update:
        flash("Formulário não encontrado.", "danger")
        return redirect(url_for('sisreg.formularios'))

    if "ADMIN" not in current_user.profile and "ALTERAR_STATUS" not in current_user.profile:
        flash("Acesso negado!", "danger")
        return redirect(url_for('main.panel'))

    novo_status = request.form.get("novo_status")

    if novo_status == 'AGENDADO':
        data_atendimento_str = request.form.get('data_atendimento')
        hora_agendamento = request.form.get('hora_agendamento')
        local_destino = request.form.get('local_destino')
        medico_atendimento = request.form.get('medico_atendimento')

        if not all([data_atendimento_str, hora_agendamento, local_destino, medico_atendimento]):
            flash('Para agendar, todos os campos (Data, Hora, Local e Médico) são obrigatórios!', 'danger')
            return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))

        try:
            data_atendimento_obj = datetime.strptime(data_atendimento_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Data do agendamento inválida.', 'warning')
            return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))

        conflito_q = (
            select(func.count(Formulario.id))
            .where(Formulario.id != form_id)
            .where(Formulario.status == 'AGENDADO')
            .where(Formulario.data_atendimento == data_atendimento_obj)
            .where(Formulario.hora_agendamento == hora_agendamento)
            .where(
                or_(
                    Formulario.medico_atendimento == medico_atendimento,
                    Formulario.local_destino == local_destino
                )
            )
        )
        conflitos = db.session.execute(conflito_q).scalar_one() or 0
        if conflitos > 0:
            flash('Horário indisponível: já existe agendamento nesse horário para o mesmo médico ou local. Escolha outro horário.', 'warning')
            return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))

        form_to_update.status = 'AGENDADO'
        form_to_update.data_atendimento = data_atendimento_obj
        form_to_update.hora_agendamento = hora_agendamento
        form_to_update.local_destino = local_destino
        form_to_update.medico_atendimento = medico_atendimento
        form_to_update.autorizador_id = current_user.id
    
    else:
        form_to_update.status = novo_status
        form_to_update.data_atendimento = None
        form_to_update.hora_agendamento = None
        form_to_update.local_destino = None
        form_to_update.medico_atendimento = None
        form_to_update.autorizador_id = None

    try:
        db.session.commit()
        flash("Solicitação atualizada com sucesso!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao atualizar a solicitação: {str(e)}", "danger")
    
    return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))

@sisreg_bp.route('/setor/regulacao/<int:form_id>/autorizar', methods=['POST'])
@login_required
def setor_regulacao_autorizar(form_id):
    if "ALTERAR_STATUS" not in current_user.profile and "ADMIN" not in current_user.profile:
        flash("Acesso negado!", "danger")
        return redirect(url_for('sisreg.setor_regulacao_lista'))
    f = db.session.get(Formulario, form_id)
    if not f:
        flash('Solicitação não encontrada.', 'danger')
        return redirect(url_for('sisreg.setor_regulacao_lista'))

    data_atendimento_str = request.form.get('data_atendimento')
    hora_agendamento = request.form.get('hora_agendamento')
    local_destino = request.form.get('local_destino')
    medico_atendimento = request.form.get('medico_atendimento')
    obs = (request.form.get('observacao_autorizacao') or '').strip()

    if not all([data_atendimento_str, hora_agendamento, local_destino, medico_atendimento]):
        flash('Para autorizar e encaminhar ao ambulatório, preencha Data, Hora, Local e Médico.', 'warning')
        return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))

    try:
        data_atendimento_obj = datetime.strptime(data_atendimento_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Data do agendamento inválida.', 'warning')
        return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))

    conflito_q = (
        select(func.count(Formulario.id))
        .where(Formulario.id != form_id)
        .where(Formulario.status == 'AGENDADO')
        .where(Formulario.data_atendimento == data_atendimento_obj)
        .where(Formulario.hora_agendamento == hora_agendamento)
        .where(or_(Formulario.medico_atendimento == medico_atendimento, Formulario.local_destino == local_destino))
    )
    conflitos = db.session.execute(conflito_q).scalar_one() or 0
    if conflitos > 0:
        flash('Horário indisponível: já existe agendamento nesse horário para o mesmo médico ou local.', 'warning')
        return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))

    f.status = 'AGENDADO'
    f.data_atendimento = data_atendimento_obj
    f.hora_agendamento = hora_agendamento
    f.local_destino = local_destino
    f.medico_atendimento = medico_atendimento
    f.autorizador_id = current_user.id
    # Registrar evento com timestamp e autor
    _stamp = _now_brasilia().strftime('%d/%m/%Y %H:%M')
    _actor = getattr(current_user, 'name', None) or 'Usuário'
    # Se está voltando do ambulatório por falta (compareceu == False), tratamos como REAGENDAR
    is_reschedule = (f.compareceu is False)
    if is_reschedule:
        # limpar presença para o novo agendamento
        f.compareceu = None
    _header = 'REAGENDAR' if is_reschedule else 'AUTORIZAR'
    _msg = f"[REGULAÇÃO - {_header}]{f' {obs}' if obs else ''} - {_stamp} | por {_actor}"
    f.observacao = (f.observacao or '')
    if f.observacao:
        f.observacao += f"\n{_msg}"
    else:
        f.observacao = f"\n{_msg}"

    try:
        db.session.commit()
        if is_reschedule:
            flash('Solicitação reagendada e encaminhada ao ambulatório.', 'success')
        else:
            flash('Solicitação autorizada e encaminhada ao ambulatório.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao autorizar solicitação: {str(e)}', 'danger')
    return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))


@sisreg_bp.route('/setor/regulacao')
@login_required
def setor_regulacao_lista():
    if "VER_RELATORIOS" not in current_user.profile and "ADMIN" not in current_user.profile and "ALTERAR_STATUS" not in current_user.profile:
        flash("Acesso negado!", "danger")
        return redirect(url_for('main.panel'))

    status = request.args.get('status', '').upper().strip()
    q = request.args.get('q', '').strip()
    query = select(Formulario)
    if status == 'PENDENTES':
        query = query.where(Formulario.status.in_(['EM_ANALISE', 'PENDENTE']))
    elif status:
        query = query.where(Formulario.status == status)
    if q:
        like = f"%{q}%"
        query = query.where(
            or_(
                Formulario.nome_paciente.ilike(like),
                Formulario.cpf.ilike(like)
            )
        )
    status_priority = case(
        (Formulario.status.in_(['EM_ANALISE', 'PENDENTE']), 0),
        (Formulario.status == 'AGENDADO', 1),
        else_=2
    )
    query = query.order_by(status_priority.asc(), Formulario.data_registro.desc())

    itens = db.session.execute(query).scalars().all()
    total = db.session.execute(select(func.count(Formulario.id))).scalar_one() or 0
    pend_q = select(func.count(Formulario.id)).where(Formulario.status.in_(['EM_ANALISE', 'PENDENTE']))
    pendentes = db.session.execute(pend_q).scalar_one() or 0
    ag_q = select(func.count(Formulario.id)).where(Formulario.status == 'AGENDADO')
    agendados = db.session.execute(ag_q).scalar_one() or 0
    neg_q = select(func.count(Formulario.id)).where(Formulario.status == 'CANCELADO')
    negados = db.session.execute(neg_q).scalar_one() or 0

    stats_counts = {
        'total': total,
        'pendentes': pendentes,
        'agendados': agendados,
        'negados': negados
    }

    return render_template('workflow/setor_regulacao_lista.html', itens=itens, status=status, stats_counts=stats_counts)

@sisreg_bp.route('/setor/regulacao/<int:form_id>/negar', methods=['POST'])
@login_required
def setor_regulacao_negar(form_id):
    if "ALTERAR_STATUS" not in current_user.profile and "ADMIN" not in current_user.profile:
        flash("Acesso negado!", "danger")
        return redirect(url_for('sisreg.setor_regulacao_lista'))
    f = db.session.get(Formulario, form_id)
    if not f:
        flash('Solicitação não encontrada.', 'danger')
        return redirect(url_for('sisreg.setor_regulacao_lista'))
    justificativa = request.form.get('justificativa_negativa', '').strip()
    observacao_extra = (request.form.get('observacao') or '').strip()
    if not justificativa:
        flash('Informe uma justificativa para negar a solicitação.', 'warning')
        return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))
    f.status = 'CANCELADO'
    f.justificativa_negativa = justificativa
    # Registrar evento com timestamp e autor (inclui justificativa e obs extra quando houver)
    _stamp = _now_brasilia().strftime('%d/%m/%Y %H:%M')
    _actor = getattr(current_user, 'nome', None) or 'Usuário'
    _extra = f" | Obs: {observacao_extra}" if observacao_extra else ''
    _msg = f"[REGULAÇÃO - NEGAR] {justificativa}{_extra} - {_stamp} | por {_actor}"
    f.observacao = (f.observacao or '')
    if f.observacao:
        f.observacao += f"\n{_msg}"
    else:
        f.observacao = _msg
    try:
        db.session.commit()
        flash('Solicitação negada e registrada com justificativa.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao negar solicitação: {str(e)}', 'danger')
    return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))

@sisreg_bp.route('/setor/regulacao/<int:form_id>/solicitar-revisao', methods=['POST'])
@login_required
def setor_regulacao_solicitar_revisao(form_id):
    if "ALTERAR_STATUS" not in current_user.profile and "ADMIN" not in current_user.profile:
        flash("Acesso negado!", "danger")
        return redirect(url_for('sisreg.setor_regulacao_lista'))
    f = db.session.get(Formulario, form_id)
    if not f:
        flash('Solicitação não encontrada.', 'danger')
        return redirect(url_for('sisreg.setor_regulacao_lista'))
    motivo = (request.form.get('observacao_revisao') or '').strip()
    if not motivo:
        flash('Informe o motivo da solicitação de revisão.', 'warning')
        return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))
    # Enviar de volta para UBS para correção: voltar ao estado de pendência e limpar qualquer agendamento
    f.status = 'PENDENTE'
    f.observacao = (f.observacao or '')
    _stamp = _now_brasilia().strftime('%d/%m/%Y %H:%M')
    _actor = getattr(current_user, 'name', None) or 'Usuário'
    _entry = f"[REGULAÇÃO - SOLICITAR REVISÃO] {motivo} - {_stamp} | por {_actor}"
    if f.observacao:
        f.observacao += f"\n{_entry}"
    else:
        f.observacao = _entry
    f.data_atendimento = None
    f.hora_agendamento = None
    f.local_destino = None
    f.medico_atendimento = None
    f.autorizador_id = None
    try:
        db.session.commit()
        flash('Revisão solicitada à UBS com sucesso.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao solicitar revisão: {str(e)}', 'danger')
    return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))

@sisreg_bp.route('/setor/ambulatorio')
@login_required
def setor_ambulatorio_lista():
    # Filtro por nome/cpf (opcional)
    q = (request.args.get('q', '') or '').strip()
    base = select(Formulario).where(Formulario.status == 'AGENDADO')
    if q:
        like = f"%{q}%"
        base = base.where(or_(Formulario.nome_paciente.ilike(like), Formulario.cpf.ilike(like)))

    itens = db.session.execute(
        base.order_by(Formulario.data_atendimento.asc(), Formulario.hora_agendamento.asc())
    ).scalars().all()

    # Estatísticas (apenas sobre AGENDADO + filtro q)
    total = db.session.execute(select(func.count()).select_from(base.subquery())).scalar_one() or 0
    presentes = db.session.execute(
        select(func.count()).select_from(base.where(Formulario.compareceu.is_(True)).subquery())
    ).scalar_one() or 0
    faltas = db.session.execute(
        select(func.count()).select_from(base.where(Formulario.compareceu.is_(False)).subquery())
    ).scalar_one() or 0
    sem_registro = total - presentes - faltas
    stats_counts = {
        'total': total,
        'presentes': presentes,
        'faltas': faltas,
        'sem_registro': sem_registro,
    }

    return render_template('workflow/setor_ambulatorio_lista.html', itens=itens, stats_counts=stats_counts, q=q)

@sisreg_bp.route('/setor/ambulatorio/<int:form_id>/atualizar', methods=['POST'])
@login_required
def setor_ambulatorio_atualizar(form_id):
    f = db.session.get(Formulario, form_id)
    if not f:
        flash('Solicitação não encontrada.', 'danger')
        return redirect(url_for('sisreg.setor_ambulatorio_lista'))
    # Triagem do estado de presença: só alterar se o usuário escolheu uma opção
    compareceu_choice = request.form.get('compareceu_choice', None)
    resultado = (request.form.get('resultado_procedimento') or '').strip()

    presence_changed = False
    if compareceu_choice is not None:
        new_compareceu = True if compareceu_choice == '1' else False
        if f.compareceu != new_compareceu:
            presence_changed = True
        f.compareceu = new_compareceu
        # Se não compareceu, devolve para Regulação decidir reagendamento/cancelamento
        if new_compareceu is False:
            f.status = 'EM_ANALISE'
            f.data_atendimento = None
            f.hora_agendamento = None
            f.local_destino = None
            f.medico_atendimento = None
            f.autorizador_id = None
    # Não sobrescrever 'procedimento_realizado' se campo não veio no form
    if 'procedimento_realizado' in request.form:
        realizado = request.form.get('procedimento_realizado') == 'on'
        f.procedimento_realizado = realizado
        if realizado:
            f.status = 'CONCLUIDO'
    # Atualizar resultado/observação se fornecido
    if resultado:
        f.resultado_procedimento = resultado

    # Registrar evento nos comentários (observação)
    if compareceu_choice is not None:
        _stamp = _now_brasilia().strftime('%d/%m/%Y %H:%M')
        _actor = getattr(current_user, 'name', None) or 'Usuário'
        header = 'PRESENÇA' if f.compareceu else 'FALTA'
        body = resultado if resultado else ''
        entry = f"[AMBULATÓRIO - {header}] {body} - {_stamp} | por {_actor}"
        f.observacao = (f.observacao or '')
        if f.observacao:
            f.observacao += f"\n{entry}"
        else:
            f.observacao = entry
    try:
        db.session.commit()
        if compareceu_choice == '0':
            flash('Falta registrada. Solicitação devolvida para Regulação.', 'info')
        else:
            flash('Registro ambulatorial atualizado.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao salvar: {str(e)}', 'danger')
    return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))

@sisreg_bp.route("/formulario/deletar/<int:form_id>", methods=["POST"])
@login_required
def deletar_formulario(form_id):

    if "ADMIN" not in current_user.profile:
        flash("Acesso negado! Você não tem permissão para deletar formulários.", "danger")
        return redirect(url_for("sisreg.detalhes_formulario", form_id=form_id)) 

    formulario_para_deletar = db.session.get(Formulario, form_id)

    if not formulario_para_deletar:
        flash("Formulário não encontrado para deleção.", "danger")
        return redirect(url_for('sisreg.formularios'))

    try:
        db.session.delete(formulario_para_deletar)
        db.session.commit()
        flash(f"Formulário ID {form_id} (Paciente: {formulario_para_deletar.nome_paciente}) foi deletado com sucesso.", "success")
        return redirect(url_for('sisreg.formularios'))
    except Exception as e:
        db.session.rollback()
        flash(f"Ocorreu um erro ao deletar o formulário: {str(e)}", "danger")
        print(f"Erro ao deletar formulário ID {form_id}: {e}")
        return redirect(url_for("sisreg.detalhes_formulario", form_id=form_id))

@sisreg_bp.route('/setor/ubs')
@login_required
def sector_ubs_lista():
    if "CRIAR_RELATORIOS" not in current_user.profile and "ADMIN" not in current_user.profile:
        flash("Acesso negado!", "danger")
        return redirect(url_for('main.panel'))

    # Filtros
    filter_status = (request.args.get('filter_status', '') or '').strip().lower()
    q = (request.args.get('q', '') or '').strip()
    meus = (request.args.get('meus', '') or '').strip().lower() in ("1", "true", "on", "yes")

    base_query = select(Formulario)
    if meus:
        base_query = base_query.where(Formulario.funcionario_id == current_user.id)
    if q:
        like = f"%{q}%"
        base_query = base_query.where(
            or_(
                Formulario.nome_paciente.ilike(like),
                Formulario.cpf.ilike(like)
            )
        )

    # Aplicar filtro de status selecionado
    if filter_status == 'pendente':
        query = base_query.where(Formulario.status == 'PENDENTE')
    elif filter_status == 'em_andamento':
        query = base_query.where(Formulario.status == 'EM_ANALISE')
    elif filter_status == 'agendado':
        query = base_query.where(Formulario.status == 'AGENDADO')
    elif filter_status == 'concluido':
        query = base_query.where(Formulario.status == 'CONCLUIDO')
    elif filter_status == 'cancelado':
        query = base_query.where(Formulario.status == 'CANCELADO')
    else:
        query = base_query

    status_priority = case(
        (Formulario.status == 'PENDENTE', 0),
        (Formulario.status == 'EM_ANALISE', 1),
        (Formulario.status == 'AGENDADO', 2),
        (Formulario.status == 'CONCLUIDO', 3),
        else_=4
    )
    query = query.order_by(status_priority.asc(), Formulario.data_registro.desc())

    itens = db.session.execute(query).scalars().all()

    # Contadores (respeitando filtros base: q e meus)
    total = db.session.execute(
        select(func.count()).select_from(base_query.subquery())
    ).scalar_one() or 0
    pendentes = db.session.execute(
        select(func.count()).select_from(
            base_query.where(Formulario.status == 'PENDENTE').subquery()
        )
    ).scalar_one() or 0
    em_andamento = db.session.execute(
        select(func.count()).select_from(
            base_query.where(Formulario.status == 'EM_ANALISE').subquery()
        )
    ).scalar_one() or 0
    concluidos = db.session.execute(
        select(func.count()).select_from(
            base_query.where(Formulario.status == 'CONCLUIDO').subquery()
        )
    ).scalar_one() or 0
    cancelados = db.session.execute(
        select(func.count()).select_from(
            base_query.where(Formulario.status == 'CANCELADO').subquery()
        )
    ).scalar_one() or 0

    stats_counts = {
        'total': total,
        'pendentes': pendentes,
        'em_andamento': em_andamento,
        'concluidos': concluidos,
        'cancelados': cancelados,
    }

    return render_template(
        'workflow/sector_ubs_lista.html',
        itens=itens,
        stats_counts=stats_counts,
        filter_status=filter_status,
        q=q,
        meus=meus
    )

@sisreg_bp.route('/setor/ubs/<int:form_id>/editar', methods=['GET', 'POST'])
@login_required
def sector_ubs_editar(form_id):
    # UBS edita todos os dados originais e reenvia para Regulação
    if "CRIAR_RELATORIOS" not in current_user.profile and "ADMIN" not in current_user.profile:
        flash("Acesso negado!", "danger")
        return redirect(url_for('main.panel'))

    f = db.session.get(Formulario, form_id)
    if not f:
        flash('Solicitação não encontrada.', 'danger')
        return redirect(url_for('sisreg.sector_ubs_lista'))

    # Somente o criador pode editar (a não ser admin)
    if ("ADMIN" not in current_user.profile) and (f.funcionario_id != current_user.id):
        flash('Você não tem permissão para editar esta solicitação.', 'danger')
        return redirect(url_for('sisreg.sector_ubs_lista'))

    # Encontrar último motivo de revisão
    motivo_revisao = None
    if f.observacao:
        try:
            for line in reversed((f.observacao or '').split('\n')):
                if '[REGULAÇÃO - SOLICITAR REVISÃO]' in line:
                    motivo_revisao = line.replace('[REGULAÇÃO - SOLICITAR REVISÃO] ', '')
                    break
        except Exception:
            pass

    if request.method == 'POST':
        try:
            f.nome_paciente = (request.form.get('nome_paciente') or f.nome_paciente).strip()
            nasc_str = (request.form.get('nascimento') or '').strip()
            if nasc_str:
                f.nascimento = datetime.strptime(nasc_str, '%Y-%m-%d').date()
            f.cpf = (request.form.get('cpf') or f.cpf).strip()
            f.unidade_saude = (request.form.get('unidade_saude') or f.unidade_saude).strip()
            f.medico_solicitante = (request.form.get('medico_solicitante') or f.medico_solicitante).strip()
            f.especialidade = (request.form.get('especialidade') or f.especialidade).strip()
            f.anexo = (request.form.get('anexo') or '').strip() or None

            resposta = (request.form.get('observacao_resposta') or '').strip()
            if not resposta:
                flash('Informe a resposta/correção.', 'warning')
                return redirect(url_for('sisreg.sector_ubs_editar', form_id=form_id))

            # Devolver à regulação
            f.status = 'EM_ANALISE'
            f.observacao = (f.observacao or '')
            _stamp = _now_brasilia().strftime('%d/%m/%Y %H:%M')
            _actor = getattr(current_user, 'name', None) or 'Usuário'
            _entry = f"[UBS - RESPOSTA REVISÃO] {resposta} - {_stamp} | por {_actor}"
            if f.observacao:
                f.observacao += f"\n{_entry}"
            else:
                f.observacao = _entry

            db.session.commit()
            flash('Solicitação atualizada e enviada para Regulação.', 'success')
            return redirect(url_for('sisreg.detalhes_formulario', form_id=form_id))
        except ValueError:
            db.session.rollback()
            flash('Data de nascimento inválida.', 'warning')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao salvar: {str(e)}', 'danger')

    return render_template('workflow/ubs_editar_solicitacao.html', formulario=f, motivo_revisao=motivo_revisao)
