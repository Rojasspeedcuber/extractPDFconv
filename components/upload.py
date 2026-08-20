"""Componente de Upload e Preview inicial de arquivo PDF."""
import streamlit as st
from config.settings import settings
from models.document import DocumentInfo
from services.pdf_service import PDFService

def render_upload_section():
    """Renderiza a zona de upload do arquivo PDF."""
    st.markdown(
        f"""
        <div style="background-color: #f8fafc; border: 2px dashed #cbd5e1; border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 20px;">
            <h3 style="margin: 0 0 8px 0; color: #1e293b; font-size: 1.25rem;">📄 Envio de Documento PDF</h3>
            <p style="margin: 0 0 12px 0; color: #64748b; font-size: 0.95rem;">Arraste e solte o arquivo PDF ou clique abaixo para selecionar</p>
            <span style="display: inline-block; background: #e2e8f0; color: #475569; font-size: 0.8rem; padding: 4px 12px; border-radius: 9999px; font-weight: 500;">
                Tamanho máximo permitido: {settings.MAX_FILE_SIZE_MB} MB
            </span>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    uploaded_file = st.file_uploader(
        "Selecione um arquivo PDF para upload",
        type=["pdf"],
        help=f"Apenas arquivos com extensão .pdf e tamanho de até {settings.MAX_FILE_SIZE_MB}MB são suportados.",
        label_visibility="collapsed"
    )
    
    return uploaded_file

def render_document_preview(doc_info: DocumentInfo):
    """Renderiza o resumo e metadados básicos do documento antes do processamento."""
    st.subheader("📋 Informações Básicas do Arquivo")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="Arquivo", value=doc_info.filename[:20] + "..." if len(doc_info.filename) > 20 else doc_info.filename)
    with col2:
        st.metric(label="Tamanho", value=doc_info.size_formatted)
    with col3:
        st.metric(label="Páginas", value=str(doc_info.page_count) if doc_info.page_count > 0 else "Calculando...")
    with col4:
        status_label = "✅ Pronto" if doc_info.is_valid else "❌ Inválido"
        st.metric(label="Validação", value=status_label)

    # Detalhes adicionais se disponíveis
    if doc_info.metadata:
        with st.expander("🔍 Ver Metadados Detalhados do Cabeçalho", expanded=False):
            st.json(doc_info.metadata)
