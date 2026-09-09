# Unificar Abas em Fluxo Guiado — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unificar as duas abas (comprovantes e extração da carta convocatória) em uma única página com fluxo guiado: Passo 1 (carta) → Passo 2 (comprovantes, bloqueado até o Passo 1) → Resumo consolidado.

**Architecture:** Camada de apresentação apenas. Um novo componente orquestrador `components/fluxo_unificado.py` monta o fluxo reaproveitando funções existentes; `results.py` e `comprovantes.py` são divididos em peças reutilizáveis (confirmação resumida vs. detalhes/painéis); `app.py` fica enxuto. Serviços, modelos e banco permanecem intactos.

**Tech Stack:** Python 3.14, Streamlit 1.62, pytest. Executar sempre a partir da raiz do repositório (`C:\Users\henri\OneDrive\Desktop\extractPDFconv`).

---

## File Structure

- **Create** `components/fluxo_unificado.py` — orquestra o fluxo (faixa de passos, Passo 1, bloqueio, Passo 2, Resumo) e contém a lógica de bloqueio.
- **Create** `tests/test_fluxo_unificado.py` — testa a função pura de bloqueio `passo2_liberado`.
- **Modify** `components/comprovantes.py` — expor `render_passo_comprovantes`, `render_painel_dias_ganhos`, `comprovantes_registrados`.
- **Modify** `components/results.py` — dividir `render_extraction_results` em `render_carta_confirmacao` + `render_detalhes_extracao`.
- **Modify** `app.py` — remover abas e orquestração inline; chamar `render_fluxo_unificado()`; ajustar "Limpar Sessão".

**Ordem dos commits:** a lógica de bloqueio é desenvolvida primeiro (TDD), mas o `components/fluxo_unificado.py` só importa as novas funções de `results.py`/`comprovantes.py` a partir da Tarefa 3. Por isso, as Tarefas 1–2 usam uma versão temporária (somente a função pura) que é substituída na Tarefa 3.

---

## Task 1: Lógica de bloqueio do Passo 2 (função pura) — TDD

**Files:**
- Create: `components/fluxo_unificado.py` (versão temporária, somente a função pura)
- Test: `tests/test_fluxo_unificado.py`

- [ ] **Step 1: Escrever o teste que falha**

Crie `tests/test_fluxo_unificado.py`:

```python
"""Testes da lógica de bloqueio do Passo 2 no fluxo unificado."""
from types import SimpleNamespace

from components.fluxo_unificado import passo2_liberado


def _resultado(status):
    return SimpleNamespace(status=status)


def test_libera_quando_carta_processada_na_sessao():
    assert passo2_liberado(_resultado("completed"), False, None, lambda cpf: False) is True


def test_bloqueado_sem_carta_e_sem_banco():
    assert passo2_liberado(None, False, None, lambda cpf: False) is False


def test_erro_na_extracao_nao_libera_por_si():
    # status "error" não libera pela condição de sessão.
    assert passo2_liberado(_resultado("error"), False, None, lambda cpf: False) is False


def test_libera_quando_carta_existe_no_banco():
    assert passo2_liberado(None, True, "12345678900", lambda cpf: True) is True


def test_persist_desativado_ignora_banco():
    chamadas = []

    def _fn(cpf):
        chamadas.append(cpf)
        return True

    assert passo2_liberado(None, False, "12345678900", _fn) is False
    assert chamadas == []  # não consulta o banco quando PERSIST_TO_DB é False


def test_sem_cpf_ignora_banco():
    chamadas = []

    def _fn(cpf):
        chamadas.append(cpf)
        return True

    assert passo2_liberado(None, True, None, _fn) is False
    assert chamadas == []


def test_falha_no_banco_nao_quebra_e_bloqueia():
    def _fn(cpf):
        raise RuntimeError("banco indisponível")

    assert passo2_liberado(None, True, "12345678900", _fn) is False
```

- [ ] **Step 2: Criar a implementação temporária (somente a função pura)**

Crie `components/fluxo_unificado.py` com EXATAMENTE este conteúdo (as importações de UI e o restante do fluxo entram na Tarefa 3):

```python
"""Componente orquestrador do fluxo unificado de página única."""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


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
```

- [ ] **Step 3: Rodar o teste para confirmar que passa**

Run: `python -m pytest tests/test_fluxo_unificado.py -v`
Expected: 7 testes PASSAM.

- [ ] **Step 4: Commit**

```bash
git add components/fluxo_unificado.py tests/test_fluxo_unificado.py
git commit -m "feat: logica de bloqueio do passo 2 (passo2_liberado) + testes"
```

---

## Task 2: Expor peças reutilizáveis em `components/comprovantes.py`

**Files:**
- Modify: `components/comprovantes.py`

Objetivo: tornar públicas as funções de dias/registros e criar `render_passo_comprovantes()` (regras + formulário, sem o painel de dias), mantendo `render_secao_comprovantes()` como composição compatível.

- [ ] **Step 1: Tornar `_comprovantes_registrados` pública**

Em `components/comprovantes.py`, renomeie a definição (linha ~40):

```python
def comprovantes_registrados() -> dict[int, dict[str, Any]]:
```

(alterar apenas o nome de `_comprovantes_registrados` para `comprovantes_registrados`; o corpo permanece idêntico.)

- [ ] **Step 2: Tornar `_render_painel_dias_ganhos` pública**

Renomeie a definição (linha ~211):

```python
def render_painel_dias_ganhos(registrados: dict[int, dict[str, Any]]) -> None:
```

(corpo permanece idêntico.)

- [ ] **Step 3: Substituir `render_secao_comprovantes` e adicionar `render_passo_comprovantes`**

Substitua a função `render_secao_comprovantes()` atual (fim do arquivo) por estas duas:

```python
def render_passo_comprovantes() -> None:
    """Regras + formulário de envio de comprovantes (Passo 2 do fluxo).

    Não inclui o painel de dias ganhos, que é exibido no Resumo consolidado.
    """
    _render_regras()
    _render_formulario_upload()


def render_secao_comprovantes() -> None:
    """Renderiza a seção completa de comprovação (uso isolado/compatibilidade)."""
    st.subheader("🗳️ Comprovação de Participação nas Eleições")
    st.markdown(
        "Envie os documentos (PDF) que comprovam sua participação nas eleições. "
        "O sistema verifica a **assinatura** e o **código de autenticidade** de "
        "cada documento antes de armazená-lo e calcular os dias ganhos."
    )

    render_passo_comprovantes()
    render_painel_dias_ganhos(comprovantes_registrados())
```

- [ ] **Step 4: Validar sintaxe e imports**

Run: `python -m py_compile components/comprovantes.py; python -c "import components.comprovantes"`
Expected: sem erros (saída vazia).

- [ ] **Step 5: Rodar a suíte existente (regressão)**

Run: `python -m pytest -q`
Expected: `53 passed, 1 skipped` + os 7 novos = **60 passed, 1 skipped** (nenhuma falha).

- [ ] **Step 6: Commit**

```bash
git add components/comprovantes.py
git commit -m "refactor: expor render_passo_comprovantes e funcoes publicas de dias"
```

---

## Task 3: Dividir `render_extraction_results` em `components/results.py`

**Files:**
- Modify: `components/results.py`

Objetivo: separar a **confirmação resumida** (status + banner de persistência + cartão azul) dos **detalhes completos** (datas + campos estruturados + JSON), mantendo `render_extraction_results()` como composição compatível.

- [ ] **Step 1: Substituir a função `render_extraction_results` inteira**

Em `components/results.py`, substitua TODA a função `render_extraction_results(result)` atual (do `def` até a chamada `render_registros_usuario()`, linhas ~31 a ~211) pelas três funções abaixo. Os helpers `_render_value_safely`, `_TIPO_LABELS`, `_TIPO_CORES`, `_badge_tipo`, `_fmt_data` e `render_registros_usuario` permanecem inalterados.

```python
def render_carta_confirmacao(result: ExtractionResult) -> bool:
    """Confirmação resumida do processamento da carta convocatória (Passo 1).

    Exibe o status (sucesso/erro), o aviso de persistência no banco e o cartão
    de destaque com os dados principais do convocado.

    Returns:
        bool: True quando a extração está válida; False em caso de erro.
    """
    if result.status == "error":
        st.error(f"❌ Falha na extração: {result.error}")
        return False

    st.success(f"✨ Extração realizada com sucesso! ({result.processing_time_seconds}s)")

    data = result.data or {}

    # Status da gravação no banco de dados (se a integração estiver ativa)
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

    # Cartão de destaque do convocado
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

    return True


def render_detalhes_extracao(result: ExtractionResult) -> None:
    """Detalhes completos da extração (datas, campos e JSON) para o Resumo."""
    if result.status == "error":
        return

    data = result.data or {}

    # Painel de datas em destaque
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

    # Lista consolidada de todas as datas encontradas
    todas_datas = data.get("todas_as_datas_encontradas") or data.get("datas_identificadas")
    if todas_datas and isinstance(todas_datas, list):
        st.markdown("#### 📆 Todas as Datas Detectadas no Documento")
        cols = st.columns(min(len(todas_datas), 6) if len(todas_datas) > 0 else 1)
        for i, dt in enumerate(todas_datas):
            with cols[i % len(cols)]:
                st.code(dt, language="text")

    # Campos estruturados (genérico para qualquer PDF)
    st.markdown("### 📊 Informações Estruturadas do Documento")

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

    # Exportação e download
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

    # Visualizador JSON bruto
    with st.expander("🛠️ Ver Estrutura JSON Completa"):
        st.json(result.data)


def render_extraction_results(result: ExtractionResult) -> None:
    """Composição compatível: confirmação + detalhes + registros do usuário."""
    if not render_carta_confirmacao(result):
        return
    render_detalhes_extracao(result)
    render_registros_usuario()
```

- [ ] **Step 2: Validar sintaxe e imports**

Run: `python -m py_compile components/results.py; python -c "import components.results"`
Expected: sem erros (saída vazia).

- [ ] **Step 3: Regressão**

Run: `python -m pytest -q`
Expected: **60 passed, 1 skipped** (nenhuma falha).

- [ ] **Step 4: Commit**

```bash
git add components/results.py
git commit -m "refactor: dividir render_extraction_results em confirmacao + detalhes"
```

---

## Task 4: Construir o orquestrador `components/fluxo_unificado.py`

**Files:**
- Modify: `components/fluxo_unificado.py` (substituir a versão temporária da Tarefa 1 pela versão completa)

- [ ] **Step 1: Substituir o conteúdo de `components/fluxo_unificado.py` pela versão completa**

MANTER a função `passo2_liberado` (testada) e ADICIONAR as importações e o restante do fluxo. Conteúdo completo do arquivo:

```python
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
```

- [ ] **Step 2: Validar sintaxe e imports**

Run: `python -m py_compile components/fluxo_unificado.py; python -c "import components.fluxo_unificado"`
Expected: sem erros (saída vazia).

- [ ] **Step 3: Regressão (o teste da Tarefa 1 continua passando)**

Run: `python -m pytest tests/test_fluxo_unificado.py -q`
Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
git add components/fluxo_unificado.py
git commit -m "feat: orquestrador do fluxo unificado (passo 1, passo 2 bloqueado, resumo)"
```

---

## Task 5: Conectar o fluxo no `app.py`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Ajustar as importações**

Em `app.py`, substitua o bloco de imports de componentes/serviços (linhas 5 a 12):

```python
from services.processing_service import ProcessingService
from services.pdf_service import PDFService
from components.upload import render_upload_section, render_document_preview
from components.processing import render_processing_indicator
from components.results import render_extraction_results
from components.auth import render_login_page
from components.comprovantes import render_secao_comprovantes
from mocks.extraction_mock import get_mock_extraction_result
```

por:

```python
from components.auth import render_login_page
from components.fluxo_unificado import render_fluxo_unificado
```

- [ ] **Step 2: Zerar os comprovantes no "Limpar Sessão"**

No bloco da sidebar, localize o botão "🔄 Limpar Sessão" e acrescente a linha dos comprovantes:

```python
    if st.button("🔄 Limpar Sessão", use_container_width=True):
        st.session_state.doc_info = None
        st.session_state.extraction_result = None
        st.session_state.current_file_name = None
        st.session_state.is_processing = False
        st.session_state.comprovantes_sessao = {}
        st.rerun()
```

- [ ] **Step 3: Substituir cabeçalho + abas pelo fluxo unificado**

Substitua TODO o trecho a partir de `# --- CABEÇALHO PRINCIPAL ---` até o fim do bloco `with tab_extracao:` (linhas ~100 a ~191, isto é, o `st.title`, o `st.markdown` de introdução, o `st.tabs`, `with tab_participacao:` e `with tab_extracao:` completos) por:

```python
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
```

O rodapé (`# --- RODAPÉ ---` em diante) permanece inalterado.

- [ ] **Step 4: Validar sintaxe e imports do app**

Run: `python -m py_compile app.py; python -c "import ast; ast.parse(open('app.py', encoding='utf-8').read()); print('app.py OK')"`
Expected: `app.py OK` (sem erros).

> Obs.: não importar `app.py` diretamente (ele executa `st.set_page_config` e requer o runtime do Streamlit). A validação é por compilação/AST; o comportamento é verificado no smoke test (Tarefa 6).

- [ ] **Step 5: Regressão completa**

Run: `python -m pytest -q`
Expected: **60 passed, 1 skipped**.

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat: conectar fluxo unificado no app e remover abas"
```

---

## Task 6: Smoke test manual do fluxo

**Files:** nenhum (validação em execução)

- [ ] **Step 1: Iniciar o app**

Run: `python run.py`
Expected: Streamlit sobe na porta configurada (padrão 3000). Abra a URL no navegador.

- [ ] **Step 2: Validar o estado bloqueado**

Após o login (CPF), confirme:
- A faixa de passos mostra **② Comprovantes** com cadeado (🔒).
- O **Passo 2** exibe o aviso "🔒 Passo 2 bloqueado…".
- O **Resumo** mostra o painel de dias com "Nenhum documento comprobatório enviado…".

- [ ] **Step 3: Processar a carta no Passo 1**

- Envie um PDF de carta convocatória e clique em "🚀 Processar PDF".
- Confirme que aparece a **confirmação resumida** (banner de sucesso + cartão azul com nome/função/pleito/local).
- Confirme que a faixa passa a mostrar **② Comprovantes** liberado (🔓) e o **Passo 2** libera o formulário.

- [ ] **Step 4: Enviar um comprovante no Passo 2**

- Selecione um tipo (ex.: Treinamento) e envie o PDF comprobatório.
- Confirme a mensagem de autenticidade e de dias ganhos.
- Confirme que o **Resumo** atualiza: painel de dias (total), "Dados da Carta Convocatória" e "Seus Registros no Banco".

- [ ] **Step 5: Verificação opcional de relogin (banco ativo)**

Somente se `DATABASE_URL`/`PERSIST_TO_DB` estiverem ativos: saia ("🚪 Sair") e entre novamente com o mesmo CPF. O **Passo 2** já deve iniciar **liberado** (a carta consta no banco).

- [ ] **Step 6: Encerrar**

Pare o servidor (Ctrl+C). Não há commit nesta tarefa (apenas validação).

---

## Self-Review

**Spec coverage:**
- Fluxo guiado em página única → Tarefa 4 (`render_fluxo_unificado`) + Tarefa 5 (`app.py`). ✔
- Sequência bloqueada → Tarefa 1 (`passo2_liberado`) + Tarefa 4 (`_carta_processada`, `_render_passo2_comprovantes`). ✔
- Resumo consolidado no fim → Tarefa 4 (`_render_resumo`) usando `render_painel_dias_ganhos` + `render_detalhes_extracao` + `render_registros_usuario`. ✔
- Refatoração `results.py` (confirmação vs. detalhes) → Tarefa 3. ✔
- Refatoração `comprovantes.py` (passo vs. painel/registros) → Tarefa 2. ✔
- `app.py` enxuto + "Limpar Sessão" zera comprovantes → Tarefa 5. ✔
- Escopo: só apresentação; serviços/banco intactos → nenhuma tarefa toca `services/`, `database/`, `models/`. ✔
- Verificação: pytest + smoke manual → Tarefas 2–6. ✔

**Placeholder scan:** sem TBD/TODO; todo passo de código traz o conteúdo completo. ✔

**Type consistency:** `passo2_liberado(extraction_result, persist_to_db, cpf_usuario, carta_existe_no_banco)` é idêntica na Tarefa 1 (definição+testes) e na Tarefa 4 (reaproveitada). `render_passo_comprovantes`, `render_painel_dias_ganhos`, `comprovantes_registrados` (Tarefa 2) e `render_carta_confirmacao`, `render_detalhes_extracao`, `render_registros_usuario` (Tarefa 3) batem com os imports da Tarefa 4. `render_fluxo_unificado()` (Tarefa 4) bate com a chamada na Tarefa 5. ✔
