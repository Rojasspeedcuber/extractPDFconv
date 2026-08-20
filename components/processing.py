"""Componente de exibição de status e progresso do processamento."""
import streamlit as st

def render_processing_indicator(step: int = 1, current_message: str = "Processando..."):
    """
    Renderiza um indicador visual das etapas do fluxo de processamento:
    1: Arquivo recebido
    2: PDF validado
    3: Processando documento
    4: Extraindo informações
    5: Finalizado
    """
    steps = [
        ("Arquivo recebido", 1),
        ("PDF validado", 2),
        ("Processando documento", 3),
        ("Extraindo informações", 4),
        ("Concluído", 5)
    ]
    
    st.markdown("#### ⚙️ Status do Processamento")
    
    progress_html = "<div style='display: flex; flex-direction: column; gap: 8px; margin: 16px 0;'>"
    for name, s_num in steps:
        if s_num < step:
            icon = "<span style='color: #16a34a; font-weight: bold;'>✓</span>"
            text_color = "#15803d"
        elif s_num == step:
            icon = "<span style='color: #2563eb; font-weight: bold;'>●</span>"
            text_color = "#1d4ed8"
        else:
            icon = "<span style='color: #94a3b8;'>○</span>"
            text_color = "#64748b"

        progress_html += f"<div style='display: flex; align-items: center; gap: 10px; color: {text_color}; font-size: 0.95rem;'>{icon} <span>{name}</span></div>"
    progress_html += "</div>"
    
    st.markdown(progress_html, unsafe_allow_html=True)
    st.caption(f"Status atual: **{current_message}**")
