"""Componente para renderização e visualização dos resultados da extração."""
import json
import streamlit as st
from typing import Any
from models.extraction import ExtractionResult

def _render_value_safely(val: Any) -> None:
    """Renderiza de forma polimórfica diferentes tipos de dados primitivos e compostos."""
    if val is None:
        st.markdown("*Não informado*")
    elif isinstance(val, bool):
        st.write("✅ Sim" if val else "❌ Não")
    elif isinstance(val, (int, float)):
        st.write(f"**{val}**")
    elif isinstance(val, str):
        st.write(val)
    elif isinstance(val, list):
        if not val:
            st.markdown("*Lista vazia*")
        elif all(isinstance(i, (str, int, float, bool)) for i in val):
            for item in val:
                st.markdown(f"- {item}")
        else:
            st.json(val)
    elif isinstance(val, dict):
        st.json(val)
    else:
        st.write(str(val))


def render_extraction_results(result: ExtractionResult):
    """Renderiza a interface completa de resultados estruturados."""
    if result.status == "error":
        st.error(f"❌ Falha na extração: {result.error}")
        return

    st.success(f"✨ Extração realizada com sucesso! ({result.processing_time_seconds}s)")

    # 1. Cabeçalho de Destaque
    data = result.data or {}

    # 0. Status da gravação no banco de dados (se a integração estiver ativa)
    persistencia = data.get("_persistencia_banco")
    if isinstance(persistencia, dict):
        if persistencia.get("sucesso"):
            n_instr = len(persistencia.get("instrumentos_inseridos", []))
            n_conv = len(persistencia.get("conv_inseridos", []))
            n_ign = len(persistencia.get("ignorados", []))
            if n_instr or n_conv:
                st.info(
                    f"🗄️ Dados gravados no banco: **{n_instr}** instrumento(s) de "
                    f"convocação e **{n_conv}** registro(s) de comparecimento."
                    + (f" ({n_ign} já existiam e foram ignorados.)" if n_ign else "")
                )
            elif n_ign:
                st.info("🗄️ Registros já existiam no banco de dados (nenhuma duplicata inserida).")
        elif persistencia.get("erro"):
            st.warning(f"🗄️ Não foi possível gravar no banco: {persistencia['erro']}")
    is_convocacao = "nome_convocado" in data or "datas_identificadas" in data

    if is_convocacao and "nome_convocado" in data:
        local_vot = data.get('local_votacao', 'Local não informado')
        endereco_vot = data.get('endereco_local_votacao', '')
        local_completo = f"{local_vot} — {endereco_vot}" if endereco_vot and endereco_vot != "Não especificado" else local_vot

        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%); color: white; border-radius: 12px; padding: 22px; margin-bottom: 24px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
                <div style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; opacity: 0.85; margin-bottom: 4px;">
                    {data.get('orgao_emissor', 'Tribunal Regional Eleitoral')} • {data.get('zona_eleitoral', 'Justiça Eleitoral')}
                </div>
                <div style="font-size: 1.6rem; font-weight: 700; margin-bottom: 8px;">
                    👤 {data.get('nome_convocado', 'Convocado(a)')}
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 16px; margin-top: 12px; font-size: 0.95rem; opacity: 0.95;">
                    <div><strong>Função:</strong> {data.get('funcao_cargo', 'Convocação')}</div>
                    <div><strong>Pleito:</strong> {data.get('eleicao', 'Eleições')}</div>
                </div>
                <div style="margin-top: 10px; font-size: 0.9rem; opacity: 0.9; border-top: 1px solid rgba(255,255,255,0.2); padding-top: 8px;">
                    <strong>Local de Votação:</strong> {local_completo}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # 2. Painel de Datas em Destaque (Se presente)
    datas_info = data.get("datas_identificadas")
    if datas_info and isinstance(datas_info, dict):
        st.markdown("### 📅 Cronograma e Datas do Documento")
        
        d_cols = st.columns(3)
        
        # 1º Turno
        with d_cols[0]:
            p_turno = datas_info.get("primeiro_turno", {})
            datas_1t = p_turno.get("datas", []) if isinstance(p_turno, dict) else []
            st.markdown(
                f"""
                <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 14px; min-height: 140px;">
                    <div style="font-weight: 600; color: #1d4ed8; font-size: 1rem; margin-bottom: 6px;">🗳️ 1º Turno</div>
                    <div style="font-size: 0.85rem; color: #334155; margin-bottom: 8px;">Eleições Gerais</div>
                    <div style="font-size: 0.95rem; color: #0f172a; font-weight: 500;">
                        {", ".join(datas_1t) if datas_1t else "Conforme edital"}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            
        # 2º Turno
        with d_cols[1]:
            s_turno = datas_info.get("segundo_turno", {})
            datas_2t = s_turno.get("datas", []) if isinstance(s_turno, dict) else []
            st.markdown(
                f"""
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; min-height: 140px;">
                    <div style="font-weight: 600; color: #475569; font-size: 1rem; margin-bottom: 6px;">🗳️ 2º Turno (Se houver)</div>
                    <div style="font-size: 0.85rem; color: #64748b; margin-bottom: 8px;">Segundo Turno</div>
                    <div style="font-size: 0.95rem; color: #0f172a; font-weight: 500;">
                        {", ".join(datas_2t) if datas_2t else "Se houver segundo turno"}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

        # Treinamento
        with d_cols[2]:
            treino = datas_info.get("treinamento", {})
            data_tr = treino.get("data", "A definir") if isinstance(treino, dict) else "A definir"
            hora_tr = treino.get("horario", "") if isinstance(treino, dict) else ""
            local_tr = treino.get("local", "") if isinstance(treino, dict) else ""
            st.markdown(
                f"""
                <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 14px; min-height: 140px;">
                    <div style="font-weight: 600; color: #15803d; font-size: 1rem; margin-bottom: 6px;">🎓 Treinamento</div>
                    <div style="font-size: 0.95rem; color: #0f172a; font-weight: 600;">{data_tr} {hora_tr}</div>
                    <div style="font-size: 0.8rem; color: #166534; margin-top: 4px;">{local_tr[:45] + '...' if len(local_tr) > 45 else local_tr}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

        # Outras datas (Vistoria, Transferência Temporária, Emissão)
        sub_col1, sub_col2, sub_col3 = st.columns(3)
        with sub_col1:
            vist = datas_info.get("vistoria", {})
            if vist:
                st.info(f"🔍 **Vistoria no Local:** {vist.get('data', '-')}")
        with sub_col2:
            transf = datas_info.get("transferencia_temporaria", {})
            if transf:
                st.warning(f"🔄 **Prazo Transf. Temporária:** {transf.get('periodo', '-')}")
        with sub_col3:
            emissao = datas_info.get("data_emissao")
            if emissao:
                st.caption(f"🗓️ **Emissão:** {emissao}")

        st.divider()

    # 3. Lista Consolidada de Todas as Datas Encontradas
    todas_datas = data.get("todas_as_datas_encontradas") or data.get("datas_identificadas")
    if todas_datas and isinstance(todas_datas, list):
        st.markdown("#### 📆 Todas as Datas Detectadas no Documento")
        cols = st.columns(min(len(todas_datas), 6) if len(todas_datas) > 0 else 1)
        for i, dt in enumerate(todas_datas):
            with cols[i % len(cols)]:
                st.code(dt, language="text")

    # 4. Exibição Geral de Campos Estruturados (Genérico para qualquer PDF)
    st.markdown("### 📊 Informações Estruturadas do Documento")
    
    # Renderiza os campos não especiais em formato de cards / tabelas
    campos_principais = {
        k: v for k, v in data.items()
        if k not in ("datas_identificadas", "todas_as_datas_encontradas")
        and not k.startswith("_")
    }

    if campos_principais:
        for campo, valor in campos_principais.items():
            nome_amigavel = campo.replace("_", " ").title()
            with st.container():
                st.markdown(f"**{nome_amigavel}:**")
                _render_value_safely(valor)
                st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #f1f5f9;'>", unsafe_allow_html=True)
    else:
        st.info("Nenhum campo específico adicional extraído.")

    # 5. Exportação e Download
    st.divider()
    col_dl1, col_dl2 = st.columns([2, 1])
    with col_dl1:
        st.caption(f"Tipo de Documento detectado: **{result.document_type}** | Total de campos: **{result.extracted_fields_count}**")
    with col_dl2:
        json_data = json.dumps(result.data, ensure_ascii=False, indent=2)
        st.download_button(
            label="📥 Baixar Dados (JSON)",
            data=json_data,
            file_name="dados_extraidos_pdf.json",
            mime="application/json",
            use_container_width=True
        )

    # 6. Visualizador JSON Bruto
    with st.expander("🛠️ Ver Estrutura JSON Completa"):
        st.json(result.data)

    # 7. Registros do usuário logado no banco de dados
    render_registros_usuario()


# Rótulos e cores por tipo de convocação
_TIPO_LABELS = {0: "Treinamento", 1: "1º Turno", 2: "2º Turno"}
_TIPO_CORES = {
    0: ("#f0fdf4", "#bbf7d0", "#15803d"),  # verde (treinamento)
    1: ("#eff6ff", "#bfdbfe", "#1d4ed8"),  # azul (1º turno)
    2: ("#f8fafc", "#e2e8f0", "#475569"),  # cinza (2º turno)
}


def _badge_tipo(tipo: Any) -> str:
    """Retorna um badge HTML colorido para o tipo de convocação."""
    try:
        tipo_int = int(tipo)
    except (TypeError, ValueError):
        tipo_int = -1
    label = _TIPO_LABELS.get(tipo_int, f"Tipo {tipo}")
    bg, borda, cor = _TIPO_CORES.get(tipo_int, ("#f1f5f9", "#e2e8f0", "#334155"))
    return (
        f"<span style='background:{bg}; border:1px solid {borda}; color:{cor}; "
        f"border-radius:6px; padding:2px 10px; font-size:0.82rem; font-weight:600;'>"
        f"{label}</span>"
    )


def _fmt_data(valor: Any) -> str:
    """Formata uma data (date/str) como DD/MM/AAAA, ou '—' se ausente."""
    if not valor:
        return "—"
    try:
        return valor.strftime("%d/%m/%Y")  # objeto date
    except AttributeError:
        return str(valor)


def render_registros_usuario() -> None:
    """Renderiza a seção "📋 Seus Registros no Banco" para o CPF logado."""
    cpf = st.session_state.get("cpf_usuario")
    cpf_fmt = st.session_state.get("cpf_usuario_fmt")
    if not cpf:
        return

    st.divider()
    st.markdown("### 📋 Seus Registros no Banco")

    # Badge azul com o CPF formatado
    st.markdown(
        f"<div style='display:inline-block; background:#1e3a8a; color:white; "
        f"border-radius:8px; padding:6px 14px; font-weight:600; margin-bottom:10px;'>"
        f"👤 CPF: {cpf_fmt or cpf}</div>",
        unsafe_allow_html=True,
    )

    try:
        from database.db import buscar_registros_cpf
        registros = buscar_registros_cpf(cpf)
    except ImportError:
        st.warning("🗄️ Integração com o banco indisponível (psycopg2 não instalado).")
        return
    except Exception as exc:  # noqa: BLE001 - não deve quebrar a interface
        st.warning(f"🗄️ Não foi possível consultar o banco: {exc}")
        return

    instrumentos = registros.get("instrumentos", [])
    conv = registros.get("conv", [])

    if not instrumentos and not conv:
        st.info("Nenhum registro encontrado para este CPF.")
        return

    # Mapeia comparecimento (conv) por tipo para cruzar com instrumentos
    conv_por_tipo = {c.get("tipo"): c for c in conv}

    st.markdown("#### 🗂️ Instrumentos de Convocação")
    if instrumentos:
        for inst in instrumentos:
            tipo = inst.get("tipo")
            conv_rel = conv_por_tipo.get(tipo, {})
            realizado = conv_rel.get("realizado")
            realizado_txt = "✅ Realizado" if realizado else "❌ Não realizado"
            st.markdown(
                f"""
                <div style="border:1px solid #e2e8f0; border-radius:10px; padding:12px 16px;
                            margin-bottom:10px; box-shadow:0 1px 2px rgba(0,0,0,0.04);">
                    <div style="display:flex; justify-content:space-between; align-items:center;
                                flex-wrap:wrap; gap:8px;">
                        <div>{_badge_tipo(tipo)}
                            <span style="margin-left:10px; color:#0f172a; font-weight:600;">
                                📅 {_fmt_data(inst.get('data'))}
                            </span>
                        </div>
                        <div style="font-size:0.9rem; font-weight:600;
                                    color:{'#15803d' if realizado else '#b91c1c'};">
                            {realizado_txt}
                        </div>
                    </div>
                    <div style="margin-top:6px; font-size:0.88rem; color:#334155;">
                        <strong>Órgão convocador:</strong> {inst.get('orgao_convocador') or '—'}
                    </div>
                    <div style="font-size:0.85rem; color:#64748b;">
                        <strong>Responsável:</strong> {inst.get('responsavel') or '—'}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.caption("Nenhum instrumento de convocação registrado.")

    st.markdown("#### 📝 Controle de Comparecimento")
    if conv:
        for c in conv:
            realizado = c.get("realizado")
            st.markdown(
                f"{_badge_tipo(c.get('tipo'))} &nbsp; "
                f"📅 **{_fmt_data(c.get('data'))}** &nbsp; "
                f"{'✅ Realizado' if realizado else '❌ Não realizado'}",
                unsafe_allow_html=True,
            )
    else:
        st.caption("Nenhum registro de comparecimento.")
