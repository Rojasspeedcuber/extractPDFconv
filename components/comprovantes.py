"""Componente de upload dos documentos comprobatórios e cálculo dos dias ganhos.

Fluxo:
    1. O usuário seleciona o tipo de participação (Treinamento, 1º Turno ou
       2º Turno) e envia o PDF comprobatório correspondente.
    2. O sistema valida o arquivo e verifica a autenticidade do documento
       (assinatura + código de autenticidade).
    3. Somente documentos válidos são armazenados e têm seus dias
       contabilizados:
           Treinamento = 1 dia | 1º Turno = 4 dias | 2º Turno = 4 dias
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from config.settings import settings
from services.authenticity_service import extrair_texto_pdf, verify_pdf_authenticity
from services.days_service import DIAS_POR_TIPO, LABELS_POR_TIPO, calcular_dias_ganhos
from services.document_storage_service import (
    extrair_data_evento,
    salvar_documento_comprovante,
)
from utils.file_validation import validate_pdf

# Opções exibidas no seletor de tipo de participação
OPCOES_TIPO: dict[str, int] = {
    "🎓 Treinamento (1 dia)": 0,
    "🗳️ 1º Turno (4 dias)": 1,
    "🗳️ 2º Turno (4 dias)": 2,
}


def _comprovantes_da_sessao() -> dict[int, dict[str, Any]]:
    """Retorna o mapa tipo -> comprovante mantido na sessão do usuário."""
    return st.session_state.setdefault("comprovantes_sessao", {})


def _comprovantes_registrados() -> dict[int, dict[str, Any]]:
    """Consolida os comprovantes registrados (banco de dados + sessão).

    Quando a integração com o banco está ativa, os registros persistidos têm
    precedência; os registros apenas em sessão são usados como complemento
    (ex.: banco indisponível ou persistência desativada).
    """
    consolidado: dict[int, dict[str, Any]] = {}

    # 1. Registros apenas em sessão
    consolidado.update(_comprovantes_da_sessao())

    # 2. Registros persistidos no banco (precedência)
    cpf = st.session_state.get("cpf_usuario")
    if cpf and settings.PERSIST_TO_DB:
        try:
            from database.db import buscar_documentos_cpf

            for registro in buscar_documentos_cpf(cpf):
                consolidado[registro["tipo"]] = {
                    "nome_arquivo": registro.get("nome_arquivo"),
                    "codigo_verificador": registro.get("codigo_verificador"),
                    "codigo_crc": registro.get("codigo_crc"),
                    "url_conferencia": registro.get("url_conferencia"),
                    "dias_ganhos": registro.get("dias_ganhos", 0),
                    "persistido": True,
                }
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001 - indisponibilidade do banco não quebra a UI
            st.caption(f"Não foi possível consultar os comprovantes no banco: {exc}")

    return consolidado


def _render_regras() -> None:
    """Exibe as regras de contabilização dos dias ganhos."""
    st.info(
        "**Regras de contabilização dos dias ganhos:**\n\n"
        "- 🎓 **Treinamento** = 1 dia\n"
        "- 🗳️ **1º Turno** = 4 dias\n"
        "- 🗳️ **2º Turno** = 4 dias\n\n"
        "Os dias somente são contabilizados mediante **upload do documento "
        "comprobatório** correspondente, após verificação da **assinatura** e do "
        "**código de autenticidade** do PDF. Sem upload (ou documento inválido), "
        "os dias não são contabilizados.",
        icon="📜",
    )


def _render_detalhes_verificacao(detalhes: list[str], valido: bool) -> None:
    """Exibe o detalhamento da verificação de autenticidade."""
    with st.expander(
        "🔎 Detalhes da verificação de autenticidade", expanded=not valido
    ):
        for detalhe in detalhes:
            st.markdown(f"- {detalhe}")


def _processar_upload(uploaded, tipo: int) -> None:
    """Valida, verifica a autenticidade e armazena o documento enviado."""
    cpf = st.session_state.get("cpf_usuario")
    file_bytes = uploaded.getvalue()

    # 1. Validação estrutural do PDF (formato, tamanho, integridade)
    valido_arquivo, mensagem, _ = validate_pdf(file_bytes, uploaded.name)
    if not valido_arquivo:
        st.error(f"❌ Arquivo rejeitado: {mensagem}")
        return

    # 2. Verificação de autenticidade (assinatura + código de autenticidade)
    with st.spinner("Verificando assinatura e código de autenticidade do documento..."):
        report = verify_pdf_authenticity(file_bytes, uploaded.name)

    if not report.valido:
        st.error(
            f"❌ Documento INVÁLIDO para **{LABELS_POR_TIPO[tipo]}**: os dias "
            "correspondentes **não** serão contabilizados."
        )
        _render_detalhes_verificacao(report.detalhes, valido=False)
        return

    st.success(
        f"✅ Documento autêntico: assinatura e códigos de autenticidade verificados "
        f"(verificador {report.codigo_verificador} / CRC {report.codigo_crc})."
    )
    _render_detalhes_verificacao(report.detalhes, valido=True)

    # 3. Somente após a validação o cálculo e o armazenamento prosseguem
    try:
        texto = extrair_texto_pdf(file_bytes)
    except Exception:  # noqa: BLE001
        texto = ""
    data_evento = extrair_data_evento(texto, tipo, report)

    resumo = salvar_documento_comprovante(
        cpf_usuario=cpf,
        tipo=tipo,
        file_bytes=file_bytes,
        filename=uploaded.name,
        report=report,
        data_evento=data_evento,
    )

    if resumo.get("duplicado"):
        st.warning(f"⚠️ {resumo['erro']}")
        return

    if not resumo.get("sucesso"):
        st.error(f"❌ {resumo.get('erro')}")
        return

    # Atualiza o estado da sessão para exibição imediata
    _comprovantes_da_sessao()[tipo] = {
        "nome_arquivo": uploaded.name,
        "codigo_verificador": report.codigo_verificador,
        "codigo_crc": report.codigo_crc,
        "url_conferencia": report.url_conferencia,
        "dias_ganhos": resumo["dias"],
        "persistido": resumo.get("persistido", False),
    }

    persistido_txt = (
        "Registro gravado no banco de dados."
        if resumo.get("persistido")
        else "Banco de dados indisponível — documento salvo apenas no servidor."
    )
    st.success(
        f"📦 Documento armazenado com sucesso! Você ganhou "
        f"**{resumo['dias']} dia(s)** por **{LABELS_POR_TIPO[tipo]}**. {persistido_txt}"
    )

    # Limpa o uploader para permitir o envio do próximo documento
    st.session_state["_uploader_comprovante_key"] = (
        st.session_state.get("_uploader_comprovante_key", 0) + 1
    )


def _render_formulario_upload() -> None:
    """Renderiza o formulário de envio de documento comprobatório."""
    st.markdown("#### 📤 Enviar Documento Comprobatório")

    opcao = st.selectbox(
        "Tipo de participação que este documento comprova",
        options=list(OPCOES_TIPO.keys()),
        help="Selecione a etapa (Treinamento, 1º Turno ou 2º Turno) que o PDF enviado comprova.",
    )
    tipo = OPCOES_TIPO[opcao]

    uploader_key = st.session_state.get("_uploader_comprovante_key", 0)
    uploaded = st.file_uploader(
        "Selecione o PDF comprobatório",
        type=["pdf"],
        key=f"uploader_comprovante_{uploader_key}",
        help=f"Apenas arquivos .pdf de até {settings.MAX_FILE_SIZE_MB} MB.",
    )

    col_btn, _ = st.columns([1, 2])
    with col_btn:
        enviar = st.button(
            "🔍 Verificar autenticidade e armazenar",
            type="primary",
            use_container_width=True,
            disabled=uploaded is None,
        )

    if enviar and uploaded is not None:
        _processar_upload(uploaded, tipo)
        st.rerun()


def _render_painel_dias_ganhos(registrados: dict[int, dict[str, Any]]) -> None:
    """Renderiza o painel com o cálculo dos dias ganhos."""
    st.markdown("---")
    st.markdown("### 🏆 Cálculo dos Dias Ganho")

    calculo = calcular_dias_ganhos(registrados.keys())

    cols = st.columns(4)
    for col, item in zip(cols[:3], calculo["itens"]):
        with col:
            st.metric(
                label=item["label"],
                value=f"{item['dias']} dia(s)",
                delta="Comprovado" if item["comprovado"] else "Sem comprovante",
                delta_color="normal" if item["comprovado"] else "off",
            )
    with cols[3]:
        st.metric(
            label="Total de dias ganhos",
            value=f"{calculo['total']} de {calculo['maximo']}",
            delta=f"Máximo: {calculo['maximo']} dias",
            delta_color="off",
        )

    if not registrados:
        st.info(
            "Nenhum documento comprobatório enviado até o momento. "
            "Envie os PDFs acima para contabilizar seus dias."
        )
        return

    st.markdown("#### 📂 Documentos Armazenados")
    for tipo in sorted(registrados):
        doc = registrados[tipo]
        verificador = doc.get("codigo_verificador") or "—"
        crc = doc.get("codigo_crc") or "—"
        origem = "🗄️ banco de dados" if doc.get("persistido") else "💾 servidor (sessão)"
        st.markdown(
            f"""
            <div style="border:1px solid #e2e8f0; border-radius:10px; padding:12px 16px;
                        margin-bottom:10px; box-shadow:0 1px 2px rgba(0,0,0,0.04);">
                <div style="display:flex; justify-content:space-between; align-items:center;
                            flex-wrap:wrap; gap:8px;">
                    <div style="font-weight:600; color:#0f172a;">
                        {LABELS_POR_TIPO.get(tipo, f'Tipo {tipo}')} —
                        📄 {doc.get('nome_arquivo') or 'documento.pdf'}
                    </div>
                    <div style="font-size:0.9rem; font-weight:700; color:#15803d;">
                        +{doc.get('dias_ganhos', DIAS_POR_TIPO.get(tipo, 0))} dia(s)
                    </div>
                </div>
                <div style="margin-top:6px; font-size:0.85rem; color:#334155;">
                    🔐 Autenticidade: verificador <b>{verificador}</b> • CRC <b>{crc}</b>
                </div>
                <div style="font-size:0.8rem; color:#64748b;">Armazenado em: {origem}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_secao_comprovantes() -> None:
    """Renderiza a seção completa de comprovação de participação."""
    st.subheader("🗳️ Comprovação de Participação nas Eleições")
    st.markdown(
        "Envie os documentos (PDF) que comprovam sua participação nas eleições. "
        "O sistema verifica a **assinatura** e o **código de autenticidade** de "
        "cada documento antes de armazená-lo e calcular os dias ganhos."
    )

    _render_regras()
    _render_formulario_upload()
    _render_painel_dias_ganhos(_comprovantes_registrados())
