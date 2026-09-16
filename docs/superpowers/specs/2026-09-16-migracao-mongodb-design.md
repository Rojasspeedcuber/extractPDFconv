# Design: Migração do PostgreSQL para MongoDB (PDFs em GridFS)

- **Data:** 2026-09-16
- **Escopo:** Camada de dados (`database/`, `services/document_storage_service.py`), configuração (`config/settings.py`, `.env*`), infraestrutura (`docker-compose.yml`, `requirements.txt`) e docs
- **Status:** Aprovado pelo usuário (brainstorming)

## 1. Contexto

A aplicação (Streamlit) usa hoje **PostgreSQL** (via `psycopg2`) para metadados e o
**sistema de arquivos** (`storage/documentos/<cpf>/`) para os PDFs comprobatórios:

- `database/db.py`: conexão, verificação de duplicatas e inserções nas tabelas
  `instrumento_convocacao`, `conv` e `documento_comprovante` (schema em `database/schema.sql`).
- `services/document_storage_service.py`: grava o PDF em disco e registra os metadados.
  Se o banco falha, o arquivo **ainda assim** é salvo em disco.
- `database/persistence_service.py`: ponte entre a extração do PDF e as tabelas.
- Consumidores da camada de dados: `components/comprovantes.py`, `components/results.py`,
  `components/fluxo_unificado.py`, `services/processing_service.py`, `ingest_pdfs.py`.

## 2. Objetivo

Substituir o PostgreSQL por **MongoDB** como único banco da aplicação, armazenando os
PDFs no **GridFS**.

Decisões confirmadas com o usuário:

- **Escopo:** substituir tudo — MongoDB vira o único banco (PDFs + todas as collections);
  a dependência do PostgreSQL é removida.
- **PDFs:** somente no GridFS; nada é gravado em `storage/documentos/`.
- **Dados existentes:** começar do zero — sem script de migração Postgres→Mongo.
- **Falha do MongoDB:** upload recusado com mensagem clara (sem fallback em disco).

## 3. Abordagem escolhida

**Abordagem 1 — Reescrita direta de `database/db.py` com `pymongo` + GridFS, mantendo a
API pública.** As mesmas funções (`sanitize_cpf`, `test_connection`, `insert_*`, `*_exists`,
`buscar_*`, `registrar_comparecimento`) continuam existindo com assinaturas compatíveis,
minimizando mudanças nos consumidores.

Alternativas descartadas:

- **2 (camada de abstração com backends plugáveis Postgres/Mongo):** código extra sem
  benefício — o pedido é de substituição total (YAGNI).
- **3 (ODM — mongoengine/beanie):** desencaixa do estilo do código (funções simples + dicts)
  e adiciona dependência pesada.

## 4. Arquitetura da camada de dados

- Conexão via `MONGO_URI` (ex.: `mongodb://localhost:27017/convocacoes`). O nome do banco
  vem do path da URI; na ausência, usa `convocacoes`.
- Cliente `pymongo.MongoClient` criado sob demanda (função interna `get_database()`),
  com `serverSelectionTimeoutMS` curto (ex.: 5000) para falhar rápido.
- Erros do pymongo são encapsulados em `DatabaseError` (exceção já existente).
- `test_connection()` executa `ping` via `admin.command`.
- PDFs no **GridFS**, bucket `documentos` (`gridfs.GridFSBucket(db, bucket_name="documentos")`).
- `init_schema()` / `database/schema.sql` são substituídos por **`ensure_indexes()`**,
  que cria os índices (idempotente). O arquivo `schema.sql` é removido.
  `ingest_pdfs.py --init-db` passa a chamar `ensure_indexes()`.

## 5. Modelo de dados (collections)

### `documento_comprovante`
```
{
  _id, cpf, tipo, nome_arquivo, gridfs_file_id,
  codigo_verificador, codigo_crc, url_conferencia,
  assinatura_valida, dias_ganhos, criado_em
}
```
- Índice **único** `(cpf, tipo)` com `partialFilterExpression: {cpf: {$type: "string"}}`.
- `caminho_arquivo` deixa de existir; entra `gridfs_file_id` (ObjectId do arquivo no GridFS).

### `instrumento_convocacao`
```
{ _id, tipo, data, responsavel, convocado_cpf, orgao_convocador, criado_em }
```
- Índice **único** `(convocado_cpf, tipo)` com filtro parcial análogo.

### `conv`
```
{ _id, cpf, tipo, data, realizado, criado_em }
```
- Índice **único** `(cpf, tipo)` com filtro parcial análogo.
- `registrar_comparecimento` vira **upsert** (`$set realizado=True`; `$setOnInsert` cpf/tipo/data/criado_em).

### Convenções
- `criado_em`: `datetime` UTC (equivalente ao `DEFAULT now()` do Postgres).
- `data`: armazenada como `date`/`datetime` nativo do BSON.
- IDs retornados pelas funções de inserção/busca: `str(_id)` (antes eram `int`).
  Consumidores usam o id apenas de forma opaca (exibição/log), sem impacto.
- Funções `buscar_*` mantêm as mesmas chaves dos dicts retornados, exceto
  `caminho_arquivo` → `gridfs_file_id`.

## 6. Fluxo de upload de comprovantes (`document_storage_service`)

`salvar_documento_comprovante` passa a:

1. Validar `report`, `tipo` e `cpf` (como hoje).
2. Verificar duplicata via `db.documento_exists(cpf, tipo)` → retorna `duplicado=True` (como hoje).
3. Gravar os bytes no **GridFS** (`upload_pdf(cpf, tipo, filename, file_bytes) -> ObjectId`),
   com metadata `{cpf, tipo, filename, content_type: "application/pdf"}`.
4. Inserir o documento em `documento_comprovante` (com `gridfs_file_id`).
5. `db.registrar_comparecimento(cpf, tipo, data_evento)`.

**Compensação de falha:** se os passos 4/5 falharem após o passo 3, o arquivo GridFS
órfão é **apagado** e a função retorna `sucesso=False` com o erro.

**Mongo indisponível / `PERSIST_TO_DB=false`:** upload **recusado** com mensagem clara
(sem gravação em disco). O resumo deixa de ter `caminho` e passa a ter `gridfs_file_id`.

**Nova função:** `db.obter_pdf_documento(documento_id) -> bytes | None` — busca o
`documento_comprovante` e devolve o conteúdo do GridFS (base para download/visualização).

## 7. Configuração e infraestrutura

- `config/settings.py`:
  - `MONGO_URI: str | None = os.getenv("MONGO_URI")` substitui `DATABASE_URL`.
  - `PERSIST_TO_DB`: default `true` quando `MONGO_URI` estiver definida (mesma lógica de antes).
  - `DOCUMENTS_DIR` **removido** (incluindo o `mkdir` do fim do módulo). `STORAGE_DIR`
    (temporários da extração) permanece.
- `requirements.txt`: **+`pymongo>=4.7`**, **−`psycopg2-binary`**.
- `.env` / `.env.example`: `DATABASE_URL` → `MONGO_URI`
  (ex.: `mongodb://usuario:senha@host:27017/convocacoes`).
- `docker-compose.yml`:
  - Serviço `postgres` → **`mongo:7`** (container `mongo_convocacoes`, porta 27017,
    volume `mongo_data:/data/db`, healthcheck `mongosh --quiet --eval "db.adminCommand('ping')"`).
  - App: `MONGO_URI=mongodb://mongo:27017/convocacoes`; removidos `DATABASE_URL` e o
    mount de `schema.sql`; `depends_on: mongo (service_healthy)`.
- `database/schema.sql`: **removido**.
- Mensagens de UI/log que citam psycopg2/PostgreSQL (`components/results.py`,
  `services/processing_service.py`, docstrings) atualizadas para pymongo/MongoDB.
  O `ImportError` nesses pontos passa a capturar ausência de `pymongo`.
- Docs: `README.md` atualizado (seções de banco); `INTEGRACAO_DBEAVER.md` e
  `RELATORIO_INTEGRACAO.md` (específicos de Postgres) **removidos**.

## 8. Tratamento de erros

- Toda operação de banco envolve `pymongo.errors.PyMongoError` em `DatabaseError`
  com mensagem em português (padrão atual).
- A UI mantém o comportamento defensivo existente: falha de consulta não quebra a página
  (captura genérica + `st.warning`/`st.caption`).
- Duplicatas: além da checagem no nível da aplicação (`evitar_duplicata`), os índices únicos garantem
  integridade; `DuplicateKeyError` é tratado como "inserção ignorada" (retorna `None`).

## 9. Testes

- `tests/test_database.py`: testes de lógica pura (sanitize_cpf, parse de datas,
  `persistir_extracao` com dublês) permanecem; adicionar testes de mapeamento
  documento↔dict e do tratamento de `DuplicateKeyError`.
- `tests/test_document_storage_service.py`: reescrito com dublês para as funções de db
  e GridFS, cobrindo: sucesso, duplicata, documento inválido, CPF inválido,
  falha após gravação GridFS (cleanup do órfão) e Mongo indisponível (upload recusado).
- `tests/test_fluxo_unificado.py` e demais: ajustar apenas se referenciarem chaves removidas.
- `pytest` completo deve passar **sem** um MongoDB real (dublês/monkeypatch).

## 10. Fora de escopo

- Migração de dados existentes (Postgres/disco).
- Download/visualização de PDF na UI (apenas a função `obter_pdf_documento` fica pronta).
- Autenticação/replica set/TLS do MongoDB (URI suporta, mas nada será configurado aqui).
