"""Componente orquestrador do fluxo unificado de página única.

Encadeia, em uma única página:
    Passo 1 · Carta Convocatória  -> upload + extração dos dados
    Passo 2 · Comprovantes        -> upload por tipo (bloqueado até o Passo 1)
    Resumo  · Consolidação        -> dias ganhos + dados da carta + registros
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import streamlit as st

from config.settings import settings
from components.upload import render_upload_section, render_document_preview
from components.processing import render_processing_indicator
from components.results import (
    render_carta_confirmacao,
    render_detalhes_extracao,
    render_registros_usuario,
)
from components.comprovantes import (
    comprovantes_registrados,
    render_painel_dias_ganhos,
    render_passo_comprovantes,
)
from services.processing_service import ProcessingService
from services.pdf_service import PDFService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lógica de bloqueio do Passo 2
# ---------------------------------------------------------------------------
def passo2_liberado(
    extraction_result: Any,
    persist_to_db: bool,
    cpf_usuario: str | None,
    carta_existe_no_banco: Callable[[str], bool],
) -> bool:
    """Decide se o Passo 2 (comprovantes) está liberado.

    Libera quando a carta convocatória foi processada com sucesso nesta sessão
    (``extraction_result.status == "completed"``) OU quando já existe um
    instrumento de convocação persistido no banco para o CPF do usuário.

    Args:
        extraction_result: resultado da extração da sessão (ou None).
        persist_to_db: flag de integração com o banco (settings.PERSIST_TO_DB).
        cpf_usuario: CPF do usuário autenticado (ou None).
        carta_existe_no_banco: função que recebe o CPF e indica se já existe
            instrumento de convocação no banco. Falhas são ignoradas.

    Returns:
        bool: True se o Passo 2 deve ser liberado.
    """
    if extraction_result is not None and getattr(extraction_result, "status", None) == "completed":
        return True

    if persist_to_db and cpf_usuario:
        try:
            if carta_existe_no_banco(cpf_usuario):
                return True
        except Exception as exc:  # noqa: BLE001 - indisponibilidade do banco não quebra a UI
            logger.warning("Falha ao consultar carta no banco para bloqueio: %s", exc)

    return False


def _carta_processada() -> bool:
    """Lê o estado da sessão e responde se o Passo 2 está liberado."""
    def _existe_no_banco(cpf: str) -> bool:
        from database.db import cpf_exists_in_instrumento
        return cpf_exists_in_instrumento(cpf)

    return passo2_liberado(
        extraction_result=st.session_state.get("extraction_result"),
        persist_to_db=settings.PERSIST_TO_DB,
        cpf_usuario=st.session_state.get("cpf_usuario"),
        carta_existe_no_banco=_existe_no_banco,
    )


# ---------------------------------------------------------------------------
# Faixa visual dos passos
# ---------------------------------------------------------------------------
def _render_faixa_passos(liberado: bool) -> None:
    """Faixa visual com os três passos do fluxo (① carta → ② comprovantes → resumo)."""
    cor_passo2 = "#15803d" if liberado else "#94a3b8"
    icone_passo2 = "🔓" if liberado else "🔒"
    st.markdown(
        f"""
        <div style="display:flex; flex-wrap:wrap; gap:10px; align-items:center;
                    background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px;
                    padding:14px 18px; margin-bottom:20px; font-weight:600;">
            <span style="background:#1e3a8a; color:#fff; border-radius:9999px; padding:4px 12px;">① Carta Convocatória</span>
            <span style="color:#94a3b8;">→</span>
            <span style="background:{cor_passo2}; color:#fff; border-radius:9999px; padding:4px 12px;">{icone_passo2} ② Comprovantes</span>
            <span style="color:#94a3b8;">→</span>
            <span style="background:#475569; color:#fff; border-radius:9999px; padding:4px 12px;">📊 Resumo</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Passo 1 · Carta Convocatória
# ---------------------------------------------------------------------------
def _render_passo1_carta() -> None:
    """Upload + processamento + confirmação resumida da carta convocatória."""
    st.subheader("📄 Passo 1 · Carta Convocatória")
    st.markdown(
        "Envie o PDF da **carta convocatória** para extrair os dados da convocação "
        "(nome, função, pleito, datas e local de votação). Esta etapa **libera** o "
        "envio dos comprovantes no Passo 2."
    )

    uploaded_file = render_upload_section()

    # Detecta se o arquivo mudou ou foi removido
    if uploaded_file is None:
        if st.session_state.current_file_name is not None:
            st.session_state.doc_info = None
            st.session_state.extraction_result = None
            st.session_state.current_file_name = None
            st.info("Aguardando upload de um arquivo PDF para iniciar.")
    else:
        if uploaded_file.name != st.session_state.current_file_name:
            logger.info(f"Novo arquivo carregado: {uploaded_file.name}")
            st.session_state.current_file_name = uploaded_file.name
            st.session_state.extraction_result = None

            file_bytes = uploaded_file.getvalue()
            doc_info = PDFService.inspect_pdf(file_bytes, uploaded_file.name)
            st.session_state.doc_info = doc_info

        if st.session_state.doc_info:
            render_document_preview(st.session_state.doc_info)

            if not st.session_state.doc_info.is_valid:
                st.error(f"⚠️ {st.session_state.doc_info.validation_message}")
            else:
                st.markdown("<div style='margin-top: 16px;'></div>", unsafe_allow_html=True)
                col_proc, _ = st.columns([1, 2])
                with col_proc:
                    process_button = st.button(
                        "🚀 Processar PDF",
                        type="primary",
                        use_container_width=True,
                        disabled=st.session_state.is_processing,
                    )

                if process_button:
                    st.session_state.is_processing = True
                    status_placeholder = st.empty()
                    progress_bar = st.progress(0)

                    def update_ui(msg: str, progress: float):
                        step_num = int(progress * 5) + 1
                        with status_placeholder.container():
                            render_processing_indicator(step_num, msg)
                        progress_bar.progress(progress)

                    try:
                        file_bytes = uploaded_file.getvalue()
                        doc_info, extraction_res = ProcessingService.process_document(
                            file_bytes,
                            uploaded_file.name,
                            progress_callback=update_ui,
                            cpf_usuario=st.session_state.get("cpf_usuario"),
                        )
                        st.session_state.doc_info = doc_info
                        st.session_state.extraction_result = extraction_res
                        logger.info(f"Processamento finalizado para {uploaded_file.name}")
                    except Exception as exc:
                        logger.error(f"Erro no fluxo do app: {exc}", exc_info=True)
                        st.error("Não foi possível processar o documento devido a uma falha inesperada.")
                    finally:
                        st.session_state.is_processing = False
                        progress_bar.empty()
                        status_placeholder.empty()
                        st.rerun()

    # Confirmação resumida da carta processada
    if st.session_state.extraction_result:
        st.markdown("---")
        render_carta_confirmacao(st.session_state.extraction_result)


# ---------------------------------------------------------------------------
# Passo 2 · Comprovantes de Participação (bloqueado até o Passo 1)
# ---------------------------------------------------------------------------
def _render_passo2_comprovantes(liberado: bool) -> None:
    """Envio dos comprovantes por tipo; bloqueado até a carta ser processada."""
    st.subheader("🗳️ Passo 2 · Comprovantes de Participação")

    if not liberado:
        st.warning(
            "🔒 **Passo 2 bloqueado.** Processe a **carta convocatória** no Passo 1 "
            "para liberar o envio dos documentos comprobatórios de participação."
        )
        return

    st.markdown(
        "Carta convocatória processada. Envie os **comprovantes** de cada etapa "
        "(Treinamento, 1º Turno, 2º Turno) para contabilizar os dias ganhos."
    )
    render_passo_comprovantes()


# ---------------------------------------------------------------------------
# Resumo consolidado
# ---------------------------------------------------------------------------
def _render_resumo() -> None:
    """Consolida dias ganhos + dados da carta + registros do banco."""
    st.subheader("📊 Resumo")

    render_painel_dias_ganhos(comprovantes_registrados())

    result = st.session_state.get("extraction_result")
    if result is not None and getattr(result, "status", None) != "error":
        st.markdown("### 📄 Dados da Carta Convocatória")
        render_detalhes_extracao(result)

    render_registros_usuario()


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------
def render_fluxo_unificado() -> None:
    """Renderiza o fluxo unificado de página única."""
    liberado = _carta_processada()
    _render_faixa_passos(liberado)
    _render_passo1_carta()
    st.markdown("---")
    _render_passo2_comprovantes(liberado)
    st.markdown("---")
    _render_resumo()
