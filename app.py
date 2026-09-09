"""Aplicação Principal Streamlit para Upload e Extração de Informações de PDF."""
import logging
import streamlit as st
from config.settings import settings
from components.auth import render_login_page
from components.fluxo_unificado import render_fluxo_unificado

# Configuração de Logging centralizado
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("pdf_extractor_app")

# Configuração da página Streamlit
st.set_page_config(
    page_title="PDF Extractor - Processamento e Extração",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicialização segura do estado de sessão (st.session_state)
if "doc_info" not in st.session_state:
    st.session_state.doc_info = None

if "extraction_result" not in st.session_state:
    st.session_state.extraction_result = None

if "current_file_name" not in st.session_state:
    st.session_state.current_file_name = None

if "is_processing" not in st.session_state:
    st.session_state.is_processing = False

if "mock_mode" not in st.session_state:
    st.session_state.mock_mode = settings.USE_MOCK_EXTRACTION

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if "cpf_usuario" not in st.session_state:
    st.session_state.cpf_usuario = None

# --- GATE DE AUTENTICAÇÃO ---
# Bloqueia todo o conteúdo principal enquanto o usuário não estiver autenticado.
if not render_login_page():
    st.stop()

# --- BARRA LATERAL (CONFIGURAÇÕES E CONTROLES) ---
with st.sidebar:
    st.title("⚙️ Painel de Controle")
    st.caption("Configurações do ambiente de extração")

    # Bloco do usuário autenticado
    st.markdown("---")
    st.markdown(f"👤 **Usuário:** {st.session_state.get('cpf_usuario_fmt', '—')}")
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.autenticado = False
        st.session_state.cpf_usuario = None
        st.session_state.cpf_usuario_fmt = None
        st.rerun()

    st.markdown("---")
    mock_toggle = st.toggle(
        "Ativar Modo Mock",
        value=st.session_state.mock_mode,
        help="Quando ativado, retorna dados de demonstração sem processar o texto real do documento."
    )
    if mock_toggle != st.session_state.mock_mode:
        st.session_state.mock_mode = mock_toggle
        settings.USE_MOCK_EXTRACTION = mock_toggle
        st.rerun()

    st.markdown("---")
    st.markdown("### ℹ️ Sobre o Sistema")
    st.markdown(
        f"""
        - **Tecnologia:** 100% Python + Streamlit
        - **Motor de Leitura:** pypdf
        - **Limite de Arquivo:** {settings.MAX_FILE_SIZE_MB} MB
        - **Porta do Servidor:** {settings.PORT}
        - **Status:** Operacional
        """
    )

    if st.button("🔄 Limpar Sessão", use_container_width=True):
        st.session_state.doc_info = None
        st.session_state.extraction_result = None
        st.session_state.current_file_name = None
        st.session_state.is_processing = False
        st.session_state.comprovantes_sessao = {}
        st.rerun()

# --- CABEÇALHO PRINCIPAL ---
st.title("📄 PDF Extractor")
st.markdown(
    "Plataforma inteligente em **Python** para upload, validação e extração de dados "
    "da **carta convocatória** e dos **comprovantes de participação** — em um único "
    "fluxo guiado."
)
st.markdown("---")

# --- FLUXO UNIFICADO (Passo 1 → Passo 2 → Resumo) ---
render_fluxo_unificado()

# --- RODAPÉ ---
st.markdown("<br><br>", unsafe_allow_html=True)
st.caption("PDF Extractor • Arquitetura 100% Python modular • Pronto para EasyPanel / Docker")
