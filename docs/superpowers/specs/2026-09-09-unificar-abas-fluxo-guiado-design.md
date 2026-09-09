# Design: Unificar as abas em um fluxo guiado de página única

- **Data:** 2026-09-09
- **Escopo:** Camada de apresentação (`app.py` + `components/`)
- **Status:** Aprovado pelo usuário (brainstorming)

## 1. Contexto

O aplicativo Streamlit (`app.py`) apresenta hoje duas abas independentes:

- **Aba 1 · "Participação nas Eleições"** (`components/comprovantes.py::render_secao_comprovantes`):
  o usuário seleciona o tipo de participação (Treinamento / 1º Turno / 2º Turno), envia o PDF
  comprobatório, o sistema verifica a autenticidade (assinatura + código), grava em
  `documento_comprovante`, marca `conv.realizado = TRUE` e calcula os dias ganhos
  (1 / 4 / 4, com o total multiplicado por 2 — máximo de 18 dias).

- **Aba 2 · "Extração de Carta Convocatória"** (upload/extração inline no `app.py`):
  o usuário envia a carta convocatória, o sistema extrai os dados (nome, CPF, função, pleito,
  datas de Treinamento/1º/2º Turno, local de votação), grava em `instrumento_convocacao` e
  `conv`, exibe o painel completo da extração e a seção "Seus Registros no Banco".

As duas abas compartilham o **CPF do usuário** e o campo **`tipo`** (0=treinamento, 1=1º turno,
2=2º turno). Conceitualmente, a carta convocatória define as **convocações** (instrumentos) e os
comprovantes provam o **comparecimento** (gerando dias). Hoje essa relação fica obscurecida por
estarem em abas separadas.

## 2. Objetivo

Unificar as duas abas em **uma única página com fluxo guiado e encadeado**:

1. **Passo 1** — enviar e processar a carta convocatória (extração dos dados/convocações).
2. **Passo 2** — enviar os comprovantes de participação (ganhar dias), **bloqueado** até o Passo 1
   ser concluído.
3. **Resumo** — painel consolidado no fim com dados extraídos, dias ganhos e registros do banco.

Decisões confirmadas com o usuário:

- **Estrutura:** fluxo guiado em página única (não wizard, não apenas empilhar).
- **Sequência:** **bloqueada** — o Passo 2 só libera após a carta ser processada (nesta sessão) ou
  já constar no banco para o CPF.
- **Resultados:** **resumo consolidado no fim** — cada passo mostra o upload e uma confirmação
  resumida; um único painel "Resumo" consolida tudo.

## 3. Abordagem escolhida

**Abordagem A — Componente orquestrador novo + refatoração dos renders em peças reutilizáveis.**

- Criar `components/fluxo_unificado.py`, que monta o fluxo completo (Passo 1 → bloqueio → Passo 2 →
  Resumo), reaproveitando funções existentes.
- `app.py` fica enxuto: cabeçalho + sidebar + uma chamada a `render_fluxo_unificado()`.

Alternativas descartadas:

- **B (mínima, tudo inline no `app.py`):** manteria `app.py` grande e faria os painéis ricos
  aparecerem dentro de cada passo, duplicando dias/dados e conflitando com o "resumo consolidado".
- **C (wizard com navegação por estado):** não condiz com a escolha de fluxo guiado empilhado +
  bloqueado.

## 4. Layout da página unificada

```
📄 PDF Extractor  (título + introdução atualizada)
🧭 Faixa de passos:  ① Carta Convocatória → ② Comprovantes → 📊 Resumo

┌─ PASSO 1 · 📄 Carta Convocatória ───────────────────────
│  • Zona de upload (render_upload_section)
│  • Preview + métricas do arquivo (render_document_preview)
│  • Botão "🚀 Processar" com indicador de progresso (render_processing_indicator)
│    (orquestração movida do app.py para o fluxo_unificado.py)
│  • Após processar: CONFIRMAÇÃO RESUMIDA
│      - banner de sucesso
│      - cartão azul: nome / função / pleito / datas / local de votação
│      - aviso de gravação no banco (quando aplicável)
└─────────────────────────────────────────────────────────

┌─ PASSO 2 · 🗳️ Comprovantes de Participação  [BLOQUEADO até Passo 1] ─
│  • Se bloqueado: st.warning orientando processar a carta no Passo 1.
│  • Se liberado:
│      - regras de contabilização dos dias
│      - formulário de upload por tipo (Treinamento / 1º / 2º Turno)
│      - a confirmação resumida de cada envio já é produzida pelo _processar_upload
└─────────────────────────────────────────────────────────

┌─ 📊 RESUMO CONSOLIDADO ─────────────────────────────────
│  • Painel de dias ganhos (métricas por tipo + "Total X de 18")
│  • Dados extraídos da carta (painel de datas + campos estruturados + download JSON)
│  • "Seus Registros no Banco" (instrumentos de convocação + controle de comparecimento)
└─────────────────────────────────────────────────────────
```

## 5. Lógica de bloqueio do Passo 2

Helper `_carta_processada() -> bool` em `components/fluxo_unificado.py`. Libera o Passo 2 se
**qualquer** condição for verdadeira:

1. `st.session_state.extraction_result` existe **e** `.status == "completed"`
   (carta processada nesta sessão); **ou**
2. `settings.PERSIST_TO_DB` está ativo **e** `database.db.cpf_exists_in_instrumento(cpf_usuario)`
   retorna `True` (carta já registrada no banco — cobre sessões anteriores e relogin).

Qualquer exceção de banco na verificação (2) é tratada de forma defensiva (não quebra a UI); nesse
caso vale apenas a condição (1).

## 6. Estrutura de código / refatoração

### 6.1 Novo: `components/fluxo_unificado.py`

- `render_fluxo_unificado() -> None`: orquestra cabeçalho do fluxo, Passo 1, verificação de
  bloqueio, Passo 2 e Resumo.
- `_render_faixa_passos() -> None`: faixa visual com os 3 passos (HTML/markdown simples, nos moldes
  do HTML inline já usado no projeto).
- `_render_passo1_carta() -> None`: contém a orquestração hoje inline no `app.py` (upload →
  preview → botão processar → barra de progresso → `ProcessingService.process_document` →
  grava `doc_info`/`extraction_result` em `session_state` → `render_carta_confirmacao`).
- `_render_passo2_comprovantes() -> None`: aplica o bloqueio; se liberado chama
  `render_passo_comprovantes()`.
- `_render_resumo() -> None`: chama `render_painel_dias_ganhos(comprovantes_registrados())`,
  `render_detalhes_extracao(extraction_result)` e `render_registros_usuario()`.
- `_carta_processada() -> bool`: lógica da seção 5.

### 6.2 `app.py`

- Remover `st.tabs` e o bloco inline da Aba 2.
- Manter: `set_page_config`, inicialização do `session_state`, gate de autenticação, sidebar e
  cabeçalho.
- Atualizar o texto de introdução para refletir o fluxo unificado.
- Após o cabeçalho, chamar `render_fluxo_unificado()`.
- Botão "🔄 Limpar Sessão" também zera `comprovantes_sessao` (além dos campos já resetados).

### 6.3 `components/results.py`

- Dividir `render_extraction_results(result)` em duas funções reutilizáveis:
  - `render_carta_confirmacao(result)`: confirmação resumida do Passo 1 (banner de sucesso + cartão
    azul de destaque + aviso de persistência no banco).
  - `render_detalhes_extracao(result)`: painel de datas + todas as datas + campos estruturados +
    download JSON (usado no Resumo).
- `render_registros_usuario()` permanece pública (usada no Resumo).
- `render_extraction_results()` pode ser mantida como composição das duas (compatibilidade), mas
  deixa de ser chamada diretamente pelo fluxo.

### 6.4 `components/comprovantes.py`

- Expor `render_passo_comprovantes()`: regras + formulário de upload (o Passo 2), **sem** o painel
  de dias (que passa para o Resumo).
- Tornar `render_painel_dias_ganhos(registrados)` e `comprovantes_registrados()` públicas (hoje
  `_render_painel_dias_ganhos` / `_comprovantes_registrados`), para uso no Resumo.
- `render_secao_comprovantes()` vira a composição `render_passo_comprovantes()` +
  `render_painel_dias_ganhos(...)` (mantida para compatibilidade/uso isolado).

## 7. Escopo e riscos

- Mudança **exclusivamente na camada de apresentação** (`app.py` + `components/`).
- **Serviços, modelos, banco e `schema.sql` permanecem intactos.** Nenhuma alteração em
  `services/`, `database/`, `models/`, `config/`, `utils/`.
- **Sem novas dependências.**
- Testes existentes cobrem apenas serviços (`tests/`), portanto **não são afetados** pela
  refatoração de UI. Não há testes de componentes Streamlit.
- Convenções mantidas: textos em PT-BR, emojis nos títulos de seção, uso de `st.session_state`,
  HTML inline com `unsafe_allow_html=True` (padrão já adotado).

## 8. Casos-limite

- **Banco indisponível ou modo mock:** o desbloqueio do Passo 2 se dá pela condição (1) —
  `extraction_result` da sessão.
- **Carta genérica (não-convocatória) processada com sucesso:** ainda libera o Passo 2, pois houve
  processamento concluído no Passo 1 (`status == "completed"`).
- **Usuário sem comprovantes:** o Resumo exibe a mensagem "Nenhum documento comprobatório enviado…
  envie os PDFs para contabilizar seus dias" (comportamento já existente).
- **Relogin / nova sessão com carta já no banco:** o Passo 2 já inicia liberado via condição (2).
- **Falha no processamento da carta (`status == "error"`):** Passo 2 permanece bloqueado; a
  confirmação do Passo 1 exibe o erro de extração.

## 9. Verificação

- Executar o app (`python run.py` ou `streamlit run app.py`) e validar manualmente o fluxo:
  1. Sem carta processada → Passo 2 bloqueado com aviso.
  2. Processar carta no Passo 1 → confirmação resumida; Passo 2 libera.
  3. Enviar comprovante no Passo 2 → confirmação de autenticidade/dias.
  4. Resumo consolida dias + dados da carta + registros do banco.
- Rodar a suíte de testes existente (`pytest`) para garantir que nada quebrou nos serviços.
