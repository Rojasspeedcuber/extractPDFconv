"""Aplicação Principal Streamlit para Upload e Extração de Informações de PDF."""
import logging
import streamlit as st
from config.settings import settings
from services.processing_service import ProcessingService
from services.pdf_service import PDFService
from components.upload import render_upload_section, render_document_preview
from components.processing import render_processing_indicator
from components.results import render_extraction_results
from components.auth import render_login_page
from mocks.extraction_mock import get_mock_extraction_result

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
        st.rerun()

# --- CABEÇALHO PRINCIPAL ---
st.title("📄 PDF Extractor")
st.markdown(
    "Plataforma inteligente em **Python** para upload, validação estrutural e extração organizada de informações em documentos PDF."
)
st.markdown("---")

# --- ÁREA DE UPLOAD ---
uploaded_file = render_upload_section()

# Detecta se o arquivo mudou ou foi removido
if uploaded_file is None:
    if st.session_state.current_file_name is not None:
        # Arquivo foi removido pelo usuário
        st.session_state.doc_info = None
        st.session_state.extraction_result = None
        st.session_state.current_file_name = None
        st.info("Aguardando upload de um arquivo PDF para iniciar.")
else:
    # Se um novo arquivo foi carregado
    if uploaded_file.name != st.session_state.current_file_name:
        logger.info(f"Novo arquivo carregado: {uploaded_file.name}")
        st.session_state.current_file_name = uploaded_file.name
        st.session_state.extraction_result = None
        
        # Inspeciona metadados básicos
        file_bytes = uploaded_file.getvalue()
        doc_info = PDFService.inspect_pdf(file_bytes, uploaded_file.name)
        st.session_state.doc_info = doc_info

    # Exibe informações prévias do documento
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
                    disabled=st.session_state.is_processing
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
                        cpf_usuario=st.session_state.get("cpf_usuario")
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

# --- EXIBIÇÃO DE RESULTADOS ---
if st.session_state.extraction_result:
    st.markdown("---")
    render_extraction_results(st.session_state.extraction_result)

# --- RODAPÉ ---
st.markdown("<br><br>", unsafe_allow_html=True)
st.caption("PDF Extractor • Arquitetura 100% Python modular • Pronto para EasyPanel / Docker")
