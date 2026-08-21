# 📄 PDF Extractor (100% Python + Streamlit)

Aplicação web desenvolvida **100% em Python** com **Streamlit** para upload, validação estrutural, inspeção de metadados e extração de informações de documentos PDF (com suporte a Cartas Convocatórias, documentos eleitorais e documentos gerais com extração cronológica de datas).

---

## 🚀 Tecnologias Utilizadas

- **Linguagem:** Python 3.12+ (compatível com 3.10+)
- **Interface Web:** Streamlit
- **Motor de Extração de PDF:** pypdf
- **Banco de Dados:** PostgreSQL (via `psycopg2-binary`)
- **Gestão de Ambiente:** python-dotenv
- **Testes Automatizados:** pytest
- **Containerização:** Docker & Docker Compose
- **Deploy:** Otimizado para **EasyPanel**, **Hostinger** e **Cloud Run / VPS**

---

## 🏛️ Arquitetura do Projeto

O projeto segue estrita separação de responsabilidades em camadas desacopladas:

```text
.
├── app.py                      # Ponto de entrada da aplicação Streamlit
├── config/                     # Configurações centralizadas
│   ├── __init__.py
│   └── settings.py
├── components/                 # Componentes visuais do Streamlit
│   ├── __init__.py
│   ├── upload.py               # Zona de Upload e Preview do Arquivo
│   ├── processing.py           # Indicador visual das etapas
│   └── results.py              # Renderizador polimórfico de resultados
├── services/                   # Camada de lógica de negócio e processamento
│   ├── __init__.py
│   ├── pdf_service.py          # Leitura e parsing de baixo nível com pypdf
│   ├── extraction_service.py   # Estratégias de extração extensíveis (BaseExtractor)
│   └── processing_service.py   # Orquestrador do fluxo completo
├── models/                     # Modelos de dados e contratos tipados
│   ├── __init__.py
│   ├── document.py             # Informações e metadados do documento
│   └── extraction.py           # Contrato de resultado da extração
├── database/                   # Integração com o banco de dados PostgreSQL
│   ├── __init__.py
│   ├── schema.sql              # DDL das tabelas (instrumento_convocacao e conv)
│   ├── db.py                   # Conexão, inserções e verificação de duplicatas
│   └── persistence_service.py  # Mapeia os dados extraídos para as tabelas
├── ingest_pdfs.py              # CLI para extrair PDFs e gravar no banco (lote)
├── utils/                      # Funções utilitárias
│   ├── __init__.py
│   └── file_validation.py      # Validação de formato, MIME, tamanho e integridade
├── mocks/                      # Mocks para validação rápida da interface
│   ├── __init__.py
│   └── extraction_mock.py
├── storage/                    # Armazenamento temporário seguro de arquivos
│   └── temp/
├── tests/                      # Suíte de testes automatizados com pytest
│   ├── __init__.py
│   ├── test_file_validation.py
│   └── test_extraction_service.py
├── requirements.txt            # Dependências Python do projeto
├── .env.example                # Exemplo de variáveis de ambiente
├── Dockerfile                  # Imagem Docker otimizada para produção
├── docker-compose.yml          # Orquestração local com Docker
└── README.md
```

---

## ⚙️ Instalação e Execução Local

### 1. Criar e ativar o ambiente virtual

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows:**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 2. Instalar as dependências

```bash
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Edite o arquivo `.env` e informe, principalmente, a URL de conexão do banco:

```dotenv
DATABASE_URL=postgresql://usuario:senha@host:5432/nome_do_banco
PERSIST_TO_DB=true
```

> Se `DATABASE_URL` não for definida, a aplicação continua funcionando normalmente,
> apenas **sem** gravar os dados no banco (`PERSIST_TO_DB` fica desativado por padrão).

### 4. Executar a aplicação

```bash
streamlit run app.py
```

Acesse no navegador: `http://localhost:8501` (ou `http://localhost:3000` conforme a configuração da variável `PORT`).

---

## 🗄️ Integração com Banco de Dados PostgreSQL

A aplicação grava automaticamente os dados extraídos das cartas convocatórias em um
banco **PostgreSQL** já existente, em duas tabelas:

### Tabelas

**`instrumento_convocacao`** — registro de cada instrumento/carta de convocação:

| Coluna             | Tipo         | Descrição                                            |
|--------------------|--------------|------------------------------------------------------|
| `id`               | SERIAL (PK)  | Identificador autoincremental                        |
| `tipo`             | INTEGER      | `0` = treinamento (28/08), `1` = 1º turno, `2` = 2º turno |
| `data`             | DATE         | Data associada ao tipo de convocação                 |
| `responsavel`      | TEXT         | Responsável/assinante do instrumento                 |
| `convocado_cpf`    | VARCHAR(11)  | CPF do convocado (apenas dígitos)                    |
| `orgao_convocador` | TEXT         | Órgão que emitiu a convocação                        |

**`conv`** — controle de comparecimento por convocação:

| Coluna      | Tipo         | Descrição                                            |
|-------------|--------------|------------------------------------------------------|
| `id`        | SERIAL (PK)  | Identificador autoincremental                        |
| `cpf`       | VARCHAR(11)  | CPF da pessoa (apenas dígitos)                       |
| `tipo`      | INTEGER      | `0` = treinamento, `1` = 1º turno, `2` = 2º turno    |
| `data`      | DATE         | Data associada ao tipo                               |
| `realizado` | BOOLEAN      | Se o comparecimento foi realizado (padrão `false`)   |

### Criar as tabelas no banco

Você pode criar/verificar as tabelas de duas formas:

**Opção A — via CLI do projeto:**
```bash
python ingest_pdfs.py --init-db
```

**Opção B — diretamente com o `psql`:**
```bash
psql "$DATABASE_URL" -f database/schema.sql
```

O script usa `CREATE TABLE IF NOT EXISTS`, portanto é seguro executá-lo em um banco
já existente sem apagar dados.

### Como os dados são gravados

- **Pela interface (Streamlit):** ao processar um PDF, os dados extraídos são
  automaticamente gravados no banco (quando `PERSIST_TO_DB` está ativo). Um aviso
  na tela confirma quantos registros foram inseridos.
- **Por linha de comando (lote):** útil para processar vários PDFs de uma vez.

```bash
# Testar a conexão com o banco
python ingest_pdfs.py --test-conn

# Processar um único PDF
python ingest_pdfs.py caminho/para/convocacao.pdf

# Processar todos os PDFs de uma pasta
python ingest_pdfs.py caminho/para/pasta_de_pdfs/
```

### Prevenção de duplicatas

Antes de inserir, o sistema verifica se já existe registro para o mesmo **CPF + tipo**
em cada tabela. Se já existir, a inserção é **ignorada** (não duplica), e isso é
informado nos logs e no resumo de processamento.

---

## 🧪 Executando os Testes Automatizados

Para rodar a suíte completa de testes com `pytest`:

```bash
pytest -v
```

Cenários validados:
- ✅ Validação de PDF íntegro
- ❌ Rejeição de formatos não-PDF
- ❌ Rejeição de arquivo vazio (0 bytes)
- ❌ Rejeição de arquivo que ultrapassa limite de tamanho (ex: 20 MB)
- ❌ Rejeição de PDF corrompido / assinatura inválida
- ✅ Extração de convocação eleitoral (Convocado, Cargo, Local, Datas de 1º Turno, 2º Turno, Treinamento, Vistoria, Transferência Temporária)
- ✅ Extração genérica e modo Mock

---

## 🐳 Executando com Docker

### Build da Imagem:
```bash
docker build -t pdf-extractor .
```

### Execução do Container:
```bash
docker run -d -p 8501:8501 --name pdf_app pdf-extractor
```

### Com Docker Compose:
```bash
docker compose up -d
```

---

## 🌐 Deployment no EasyPanel / Hostinger

A imagem Docker foi estruturada para rodar sem atrito no **EasyPanel**:
1. Conecte o repositório Git ao EasyPanel.
2. Defina o tipo de serviço como **App / Dockerfile**.
3. Defina a porta de aplicação para `8501` (ou a porta exposta pelo EasyPanel).
4. Configure as variáveis de ambiente no painel:
   - `PORT=8501`
   - `MAX_FILE_SIZE_MB=20`
   - `USE_MOCK_EXTRACTION=false`
5. Clique em **Deploy**. O Healthcheck interno (`/_stcore/health`) verificará a prontidão do container automaticamente.

---

## 🎭 Modo Mock (Desenvolvimento e Teste de UI)

Para testar a interface sem processar o texto real do PDF:
- Defina no `.env`: `USE_MOCK_EXTRACTION=true`
- Ou ative o switch **"Ativar Modo Mock"** diretamente na barra lateral do Streamlit.

---

## 🔮 Próximas Etapas (Extensibilidade)

A arquitetura foi projetada com o padrão **Strategy (BaseExtractor)**. Para plugar novos extratores específicos, OCR ou modelos de IA:

1. **Adicionar novo Extrator:** Crie uma subclasse de `BaseExtractor` em `services/extraction_service.py`.
2. **Implementar OCR:** Instale `pytesseract` ou `pdf2image` e registre um `OCRExtractor` na cadeia.
3. **Integrar IA / LLM:** Adicione o client no serviço Python sem acoplamento direto com o frontend.
