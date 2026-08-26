"""Componente de autenticação do Sistema de Convocações Eleitorais (TRE-PE).

Dois fluxos de login são suportados:

1. **Keycloak (produção):** quando ``settings.KEYCLOAK_URL`` está configurado,
   usa ``streamlit_keycloak.login()`` para autenticação OIDC. Após o login,
   solicita/valida o CPF do usuário e o guarda na sessão.

2. **CPF direto (desenvolvimento):** quando o Keycloak não está configurado,
   aceita qualquer CPF válido (com dígitos verificadores corretos) como login.

Estado de sessão gravado:
    - ``st.session_state["autenticado"]``      -> bool
    - ``st.session_state["cpf_usuario"]``       -> str (11 dígitos, sem máscara)
    - ``st.session_state["cpf_usuario_fmt"]``   -> str (000.000.000-00)
"""
from __future__ import annotations

import re
import logging

import streamlit as st

from config.settings import settings

logger = logging.getLogger(__name__)

# Cor institucional (azul escuro TRE-PE)
COR_PRIMARIA = "#1e3a8a"


# ---------------------------------------------------------------------------
# Validação de CPF
# ---------------------------------------------------------------------------
def _cpf_digitos_validos(cpf: str) -> bool:
    """Valida um CPF (11 dígitos) pelos dígitos verificadores oficiais.

    Mesmo algoritmo utilizado em ``services/extraction_service.py``.
    """
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        soma = sum(int(cpf[num]) * ((i + 1) - num) for num in range(0, i))
        digito = ((soma * 10) % 11) % 10
        if digito != int(cpf[i]):
            return False
    return True


def _cpf_valido(cpf_raw: str | None) -> str | None:
    """Retorna os 11 dígitos do CPF se for válido; caso contrário, None.

    Args:
        cpf_raw: CPF em qualquer formato (ex.: '123.456.789-00').

    Returns:
        str | None: CPF com apenas dígitos (11 posições) e válido, ou None.
    """
    if not cpf_raw:
        return None
    digitos = re.sub(r"\D", "", str(cpf_raw))
    if len(digitos) != 11:
        return None
    if not _cpf_digitos_validos(digitos):
        return None
    return digitos


def _formatar_cpf(cpf_digitos: str) -> str:
    """Formata 11 dígitos como 000.000.000-00."""
    d = re.sub(r"\D", "", cpf_digitos or "")
    if len(d) != 11:
        return cpf_digitos
    return f"{d[0:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}"


def _mascara_cpf_parcial(valor: str) -> str:
    """Aplica máscara progressiva de CPF (000.000.000-00) durante a digitação."""
    d = re.sub(r"\D", "", valor or "")[:11]
    if len(d) <= 3:
        return d
    if len(d) <= 6:
        return f"{d[0:3]}.{d[3:]}"
    if len(d) <= 9:
        return f"{d[0:3]}.{d[3:6]}.{d[6:]}"
    return f"{d[0:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


# ---------------------------------------------------------------------------
# Estilo / cabeçalho da tela de login
# ---------------------------------------------------------------------------
def _render_cabecalho_login(subtitulo_modo: str = "") -> None:
    """Renderiza o cabeçalho visual (ícone, título e subtítulo) do login."""
    st.markdown(
        f"""
        <div style="text-align:center; margin: 8px auto 4px auto;">
            <div style="font-size:3.2rem; line-height:1;">🗳️</div>
            <div style="font-size:1.6rem; font-weight:800; color:{COR_PRIMARIA};
                        margin-top:6px;">
                Sistema de Convocações Eleitorais
            </div>
            <div style="font-size:1.05rem; font-weight:600; color:#334155;
                        letter-spacing:0.08em; margin-top:2px;">
                TRE-PE
            </div>
            <div style="height:3px; width:120px; background:{COR_PRIMARIA};
                        border-radius:2px; margin:12px auto 0 auto; opacity:0.85;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if subtitulo_modo:
        st.markdown(
            f"<div style='text-align:center; color:#64748b; font-size:0.85rem; "
            f"margin-top:8px;'>{subtitulo_modo}</div>",
            unsafe_allow_html=True,
        )


def _persistir_sessao(cpf_digitos: str) -> None:
    """Grava o CPF autenticado no session_state."""
    st.session_state["cpf_usuario"] = cpf_digitos
    st.session_state["cpf_usuario_fmt"] = _formatar_cpf(cpf_digitos)
    st.session_state["autenticado"] = True
    logger.info("Usuário autenticado com CPF %s.", cpf_digitos)


# ---------------------------------------------------------------------------
# Formulário de CPF (compartilhado pelos dois fluxos)
# ---------------------------------------------------------------------------
def _render_form_cpf(titulo: str, ajuda: str = "") -> bool:
    """Renderiza o formulário de CPF e trata a submissão.

    Returns:
        bool: True se o CPF foi validado e a sessão foi criada.
    """
    st.markdown(
        f"<div style='font-weight:600; color:{COR_PRIMARIA}; margin-bottom:4px;'>"
        f"{titulo}</div>",
        unsafe_allow_html=True,
    )

    with st.form("form_login_cpf", clear_on_submit=False):
        cpf_input = st.text_input(
            "CPF",
            value=st.session_state.get("_cpf_input_raw", ""),
            max_chars=14,
            placeholder="000.000.000-00",
            help=ajuda or "Informe seu CPF (apenas você tem acesso aos seus registros).",
            label_visibility="collapsed",
        )
        enviar = st.form_submit_button("Entrar", type="primary", use_container_width=True)

    # Aplica máscara em tempo real para exibição na próxima renderização
    mascarado = _mascara_cpf_parcial(cpf_input)
    if mascarado != st.session_state.get("_cpf_input_raw"):
        st.session_state["_cpf_input_raw"] = mascarado

    if enviar:
        cpf_digitos = _cpf_valido(cpf_input)
        if cpf_digitos is None:
            st.markdown(
                "<div style='color:#dc2626; font-weight:600; margin-top:8px;'>"
                "❌ CPF inválido. Verifique os números digitados e tente novamente."
                "</div>",
                unsafe_allow_html=True,
            )
            return False
        _persistir_sessao(cpf_digitos)
        st.rerun()

    return False


# ---------------------------------------------------------------------------
# Fluxos de login
# ---------------------------------------------------------------------------
def _login_keycloak() -> bool:
    """Fluxo de autenticação via Keycloak (OIDC).

    Após a autenticação OIDC, solicita/valida o CPF do usuário e cria a sessão.
    """
    try:
        from streamlit_keycloak import login as keycloak_login
    except ImportError:
        st.error(
            "Dependência 'streamlit-keycloak' não instalada. "
            "Execute: pip install streamlit-keycloak"
        )
        logger.error("streamlit-keycloak não está instalado.")
        return False

    keycloak = keycloak_login(
        url=settings.KEYCLOAK_URL,
        realm=settings.KEYCLOAK_REALM,
        client_id=settings.KEYCLOAK_CLIENT_ID,
    )

    if not getattr(keycloak, "authenticated", False):
        st.info("🔐 Redirecionando para a autenticação segura (Keycloak)…")
        return False

    # Tenta obter o CPF diretamente do token (claim 'preferred_username' ou 'cpf')
    user_info = getattr(keycloak, "user_info", {}) or {}
    cpf_token = (
        user_info.get("cpf")
        or user_info.get("preferred_username")
        or user_info.get("username")
    )
    cpf_digitos = _cpf_valido(cpf_token)
    if cpf_digitos:
        _persistir_sessao(cpf_digitos)
        st.rerun()
        return True

    # Se o token não trouxe um CPF válido, pede confirmação do CPF
    st.success("✅ Autenticado com sucesso. Confirme seu CPF para continuar.")
    return _render_form_cpf("Confirme seu CPF")


def _login_cpf_direto() -> bool:
    """Fluxo de login direto (desenvolvimento) baseado apenas no CPF."""
    st.markdown(
        "<div style='text-align:center; background:#fef9c3; border:1px solid #fde047; "
        "color:#854d0e; border-radius:8px; padding:6px 10px; font-size:0.8rem; "
        "margin-bottom:14px;'>⚠️ Modo de desenvolvimento – sem Keycloak</div>",
        unsafe_allow_html=True,
    )
    return _render_form_cpf(
        "Acesse com seu CPF",
        ajuda="Modo desenvolvimento: qualquer CPF válido é aceito.",
    )


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
def render_login_page() -> bool:
    """Renderiza a página de login e retorna o estado de autenticação.

    Returns:
        bool: True se o usuário já está autenticado, False caso contrário.
    """
    if st.session_state.get("autenticado") and st.session_state.get("cpf_usuario"):
        return True

    usa_keycloak = bool(settings.KEYCLOAK_URL)

    # Layout centralizado (card com sombra)
    _, col_centro, _ = st.columns([1, 1.4, 1])
    with col_centro:
        with st.container(border=True):
            _render_cabecalho_login(
                subtitulo_modo="Autenticação segura via Keycloak" if usa_keycloak else ""
            )
            st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

            if usa_keycloak:
                autenticado = _login_keycloak()
            else:
                autenticado = _login_cpf_direto()

            st.markdown(
                "<div style='text-align:center; color:#94a3b8; font-size:0.72rem; "
                "margin-top:16px;'>Tribunal Regional Eleitoral de Pernambuco</div>",
                unsafe_allow_html=True,
            )

    return bool(autenticado or st.session_state.get("autenticado"))
