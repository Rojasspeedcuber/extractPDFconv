# 📄 PDF Extractor (100% Python + Streamlit)

Aplicação web desenvolvida **100% em Python** com **Streamlit** para upload, validação estrutural, inspeção de metadados e extração de informações de documentos PDF (com suporte a Cartas Convocatórias, documentos eleitorais e documentos gerais com extração cronológica de datas).

---

## 🚀 Tecnologias Utilizadas

- **Linguagem:** Python 3.12+ (compatível com 3.10+)
- **Interface Web:** Streamlit
- **Motor de Extração de PDF:** pypdf
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

### 3. Configurar variáveis de ambiente (opcional)

```bash
cp .env.example .env
```

### 4. Executar a aplicação

```bash
streamlit run app.py
```

Acesse no navegador: `http://localhost:8501` (ou `http://localhost:3000` conforme a configuração da variável `PORT`).

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
