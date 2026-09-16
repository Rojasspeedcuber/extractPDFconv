# Migração PostgreSQL → MongoDB (GridFS) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o PostgreSQL pelo MongoDB como único banco da aplicação, armazenando os PDFs comprobatórios no GridFS (sem gravação em disco).

**Architecture:** Reescrita direta de `database/db.py` com `pymongo` + `gridfs`, mantendo a API pública (mesmas funções/assinaturas, ids agora `str`). O serviço de armazenamento passa a gravar GridFS → metadados → comparecimento, com compensação (apaga arquivo órfão) em caso de falha; sem MongoDB, o upload é recusado.

**Tech Stack:** Python 3.12+, pymongo (MongoDB + GridFS), Streamlit, pytest (dublês/monkeypatch, sem servidor real).

**Spec:** `docs/superpowers/specs/2026-09-16-migracao-mongodb-design.md`

---

## Estrutura de arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `requirements.txt` | Modificar | −psycopg2-binary, +pymongo |
| `database/db.py` | Reescrever | Conexão Mongo, índices, CRUD, GridFS |
| `database/__init__.py` | Modificar | Docstring do pacote |
| `database/persistence_service.py` | Modificar | Só docstrings (lógica intacta) |
| `database/schema.sql` | **Remover** | Substituído por `ensure_indexes()` |
| `services/document_storage_service.py` | Reescrever função principal | Upload → GridFS + metadados + compensação |
| `components/comprovantes.py` | Modificar | Textos de UI (persistido/origem) |
| `components/results.py` | Modificar | Mensagem ImportError (psycopg2→pymongo) |
| `services/processing_service.py` | Modificar | Docstrings/mensagens |
| `ingest_pdfs.py` | Modificar | `--init-db` → `ensure_indexes()`, textos |
| `config/settings.py` | Modificar | `MONGO_URI`, remover `DOCUMENTS_DIR` |
| `.env` / `.env.example` | Modificar | `DATABASE_URL` → `MONGO_URI` |
| `docker-compose.yml` | Reescrever | serviço `mongo:7` no lugar do `postgres` |
| `README.md` | Modificar | Seções de banco/config |
| `INTEGRACAO_DBEAVER.md`, `RELATORIO_INTEGRACAO.md` | **Remover** | Obsoletos (específicos de Postgres) |
| `tests/test_database.py` | Modificar (adicionar) | Testes de mapeamento/duplicata com dublês |
| `tests/test_document_storage_service.py` | Reescrever | Dublês de db/GridFS, cenários de falha |

**Convenções usadas em todo o plano:**
- Comando de teste: `python -m pytest <arquivo> -v` na raiz do projeto.
- Commits em português no estilo do repositório (`feat:`, `refactor:`, `chore:`, `docs:`).
- `tipo`: 0=treinamento, 1=1º turno, 2=2º turno.

---

### Task 1: Trocar a dependência psycopg2 → pymongo

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Editar `requirements.txt`**

Conteúdo final do arquivo:

```text
streamlit>=1.35.0
pypdf>=4.2.0
python-dotenv>=1.0.1
pymongo>=4.7
streamlit-keycloak>=0.3.0
pytest>=8.0.0
```

(Removido `psycopg2-binary>=2.9.9`; adicionado `pymongo>=4.7` — o pacote `gridfs` e o `bson` já vêm com o pymongo.)

- [ ] **Step 2: Instalar o pymongo no ambiente local**

Run: `pip install "pymongo>=4.7"`
Expected: `Successfully installed pymongo-...` (sem erros)

Verifique: `python -c "import pymongo, gridfs, bson; print(pymongo.version)"` → imprime a versão (ex.: `4.10.1`).

**Não desinstale o psycopg2-binary ainda** — `database/db.py` só é reescrito na Task 2 e os testes atuais ainda podem importá-lo.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: substituir psycopg2-binary por pymongo nas dependencias"
```

---

### Task 2: Reescrever `database/db.py` com pymongo + GridFS (TDD)

**Files:**
- Modify: `tests/test_database.py` (adicionar dublês e novos testes; manter os existentes)
- Rewrite: `database/db.py`
- Modify: `database/__init__.py` (docstring)

- [ ] **Step 1: Adicionar os testes novos (falhantes) em `tests/test_database.py`**

Acrescentar no TOPO do arquivo (após os imports existentes `from database import db` / `from database import persistence_service as ps`):

```python
from types import SimpleNamespace

from bson import ObjectId
from pymongo.errors import DuplicateKeyError
```

Acrescentar no FIM do arquivo:

```python
# ---------------------------------------------------------------------------
# Dublês para operações MongoDB (sem servidor real)
# ---------------------------------------------------------------------------
class _FakeCollection:
    def __init__(self):
        self.inseridos = []
        self.erro = None

    def insert_one(self, documento):
        if self.erro is not None:
            raise self.erro
        self.inseridos.append(documento)
        return SimpleNamespace(inserted_id=ObjectId())

    def find_one(self, filtro, projecao=None):
        return None


class _FakeDb:
    def __init__(self):
        self.colecoes = {}

    def __getitem__(self, nome):
        return self.colecoes.setdefault(nome, _FakeCollection())


# ---------------------------------------------------------------------------
# Mapeamento de documentos MongoDB
# ---------------------------------------------------------------------------
def test_mapear_documento_converte_ids():
    oid = ObjectId()
    gridfs_id = ObjectId()
    resultado = db._mapear_documento(
        {"_id": oid, "tipo": 1, "gridfs_file_id": gridfs_id}
    )
    assert resultado["id"] == str(oid)
    assert "_id" not in resultado
    assert resultado["gridfs_file_id"] == str(gridfs_id)


def test_mapear_documento_sem_gridfs():
    oid = ObjectId()
    resultado = db._mapear_documento({"_id": oid, "tipo": 0})
    assert resultado == {"id": str(oid), "tipo": 0}


# ---------------------------------------------------------------------------
# Inserção de documento comprobatório (com dublês)
# ---------------------------------------------------------------------------
def test_insert_documento_comprovante_grava_campos(monkeypatch):
    fake = _FakeDb()
    monkeypatch.setattr(db, "get_database", lambda: fake)
    gridfs_id = ObjectId()

    novo_id = db.insert_documento_comprovante(
        cpf="111.444.777-35",
        tipo=1,
        nome_arquivo="comprovante.pdf",
        gridfs_file_id=str(gridfs_id),
        codigo_verificador="3443939",
        codigo_crc="BCE2B28E",
        url_conferencia="https://example.gov.br/conferencia",
        assinatura_valida=True,
        dias_ganhos=4,
    )

    assert novo_id is not None
    gravado = fake["documento_comprovante"].inseridos[0]
    assert gravado["cpf"] == "11144477735"          # CPF normalizado
    assert gravado["tipo"] == 1
    assert gravado["nome_arquivo"] == "comprovante.pdf"
    assert gravado["gridfs_file_id"] == gridfs_id   # ObjectId, não str
    assert gravado["assinatura_valida"] is True
    assert gravado["dias_ganhos"] == 4
    assert gravado["criado_em"] is not None


def test_insert_documento_comprovante_duplicado_retorna_none(monkeypatch):
    fake = _FakeDb()
    fake["documento_comprovante"].erro = DuplicateKeyError("E11000 duplicate key")
    monkeypatch.setattr(db, "get_database", lambda: fake)

    resultado = db.insert_documento_comprovante(cpf="11144477735", tipo=1)
    assert resultado is None


def test_insert_documento_gridfs_id_invalido_lanca_erro(monkeypatch):
    import pytest

    fake = _FakeDb()
    monkeypatch.setattr(db, "get_database", lambda: fake)
    with pytest.raises(db.DatabaseError):
        db.insert_documento_comprovante(
            cpf="11144477735", tipo=1, gridfs_file_id="nao-e-objectid"
        )


# ---------------------------------------------------------------------------
# Comparecimento (upsert)
# ---------------------------------------------------------------------------
def test_registrar_comparecimento_faz_upsert(monkeypatch):
    fake = _FakeDb()
    atualizacoes = []
    fake["conv"].update_one = lambda filtro, update, upsert=False: atualizacoes.append(
        (filtro, update, upsert)
    )
    monkeypatch.setattr(db, "get_database", lambda: fake)

    assert db.registrar_comparecimento("111.444.777-35", 1) is True
    filtro, update, upsert = atualizacoes[0]
    assert filtro == {"cpf": "11144477735", "tipo": 1}
    assert update["$set"] == {"realizado": True}
    assert update["$setOnInsert"]["cpf"] == "11144477735"
    assert upsert is True


def test_registrar_comparecimento_cpf_invalido(monkeypatch):
    fake = _FakeDb()
    monkeypatch.setattr(db, "get_database", lambda: fake)
    assert db.registrar_comparecimento("123", 1) is False


# ---------------------------------------------------------------------------
# URI ausente
# ---------------------------------------------------------------------------
def test_get_mongo_uri_ausente_lanca_erro(monkeypatch):
    monkeypatch.delenv("MONGO_URI", raising=False)
    import pytest

    with pytest.raises(db.DatabaseError):
        db.get_mongo_uri()
```

- [ ] **Step 2: Rodar os testes novos e confirmar que FALHAM**

Run: `python -m pytest tests/test_database.py -v`
Expected: os testes novos FALHAM com `AttributeError` (ex.: `monkeypatch.setattr ... 'get_database'` / `db has no attribute '_mapear_documento'`), pois o `db.py` atual ainda é a versão psycopg2. Os testes antigos (sanitize_cpf, persistir_extracao, auth) continuam passando.

- [ ] **Step 3: Reescrever `database/db.py` (conteúdo completo do arquivo)**

```python
"""Módulo de acesso ao banco de dados MongoDB para o projeto extractPDFconv.

Responsável por:
  - Conectar ao MongoDB a partir da variável de ambiente MONGO_URI.
  - Criar/verificar os índices das collections (``ensure_indexes``).
  - Inserir e consultar documentos em `instrumento_convocacao`, `conv` e
    `documento_comprovante`.
  - Armazenar/ler os PDFs comprobatórios no GridFS (bucket ``documentos``).
  - Verificar a existência de um CPF antes de inserir (evitando duplicatas).

Todas as mensagens de log estão em português para facilitar o acompanhamento.
"""
from __future__ import annotations

import io
import os
import re
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

import gridfs
import pymongo
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError, PyMongoError
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env (se existir)
load_dotenv()

logger = logging.getLogger(__name__)

NOME_BANCO_PADRAO = "convocacoes"
BUCKET_DOCUMENTOS = "documentos"


class DatabaseError(Exception):
    """Erro genérico relacionado a operações de banco de dados."""


def get_mongo_uri() -> str:
    """Retorna a URI de conexão do MongoDB a partir do ambiente.

    Returns:
        str: valor de MONGO_URI.

    Raises:
        DatabaseError: se a variável de ambiente não estiver configurada.
    """
    uri = os.getenv("MONGO_URI")
    if not uri:
        raise DatabaseError(
            "A variável de ambiente MONGO_URI não está definida. "
            "Configure-a no arquivo .env (veja o .env.example)."
        )
    return uri


def get_database() -> "pymongo.database.Database":
    """Retorna o banco MongoDB configurado (conexão criada sob demanda).

    O nome do banco é extraído do path da MONGO_URI; na ausência, usa
    ``convocacoes``.

    Raises:
        DatabaseError: se a conexão não puder ser criada.
    """
    try:
        cliente = pymongo.MongoClient(get_mongo_uri(), serverSelectionTimeoutMS=5000)
        return cliente.get_default_database(default_db_name=NOME_BANCO_PADRAO)
    except PyMongoError as exc:
        logger.error("Erro ao conectar ao MongoDB: %s", exc)
        raise DatabaseError(f"Falha na conexão com o MongoDB: {exc}") from exc


def _agora() -> datetime:
    """Timestamp UTC atual (substitui o ``DEFAULT now()`` do PostgreSQL)."""
    return datetime.now(timezone.utc)


def sanitize_cpf(cpf: Optional[str]) -> Optional[str]:
    """Normaliza um CPF mantendo apenas os 11 dígitos.

    Args:
        cpf: CPF em qualquer formato (ex.: '123.456.789-00').

    Returns:
        str | None: CPF com apenas dígitos (11 posições) ou None se inválido.
    """
    if not cpf:
        return None
    digits = re.sub(r"\D", "", str(cpf))
    if len(digits) != 11:
        logger.warning("CPF ignorado por não conter 11 dígitos: %r", cpf)
        return None
    return digits


def _mapear_documento(doc: dict[str, Any]) -> dict[str, Any]:
    """Converte um documento MongoDB no formato esperado pelos consumidores.

    - ``_id`` (ObjectId) -> ``id`` (str)
    - ``gridfs_file_id`` (ObjectId) -> str (quando presente)
    """
    resultado = dict(doc)
    resultado["id"] = str(resultado.pop("_id"))
    arquivo = resultado.get("gridfs_file_id")
    if arquivo is not None:
        resultado["gridfs_file_id"] = str(arquivo)
    return resultado


def test_connection() -> bool:
    """Testa a conexão com o banco executando um ping no MongoDB.

    Returns:
        bool: True se a conexão foi bem sucedida.
    """
    try:
        banco = get_database()
        banco.client.admin.command("ping")
        logger.info("Teste de conexão com o MongoDB concluído com sucesso.")
        return True
    except (DatabaseError, PyMongoError) as exc:
        logger.error("Teste de conexão com o MongoDB falhou: %s", exc)
        return False


def ensure_indexes() -> None:
    """Cria/verifica os índices das collections (operação idempotente).

    Substitui o antigo ``database/schema.sql`` do PostgreSQL. Índices únicos
    usam ``partialFilterExpression`` para ignorar CPFs nulos (equivalente ao
    ``WHERE cpf IS NOT NULL`` do Postgres).
    """
    banco = get_database()
    try:
        banco["documento_comprovante"].create_index(
            [("cpf", pymongo.ASCENDING), ("tipo", pymongo.ASCENDING)],
            unique=True,
            name="uq_documento_comprovante_cpf_tipo",
            partialFilterExpression={"cpf": {"$type": "string"}},
        )
        banco["documento_comprovante"].create_index(
            [("tipo", pymongo.ASCENDING)], name="idx_documento_comprovante_tipo"
        )
        banco["instrumento_convocacao"].create_index(
            [("convocado_cpf", pymongo.ASCENDING), ("tipo", pymongo.ASCENDING)],
            unique=True,
            name="uq_instrumento_convocacao_cpf_tipo",
            partialFilterExpression={"convocado_cpf": {"$type": "string"}},
        )
        banco["instrumento_convocacao"].create_index(
            [("tipo", pymongo.ASCENDING)], name="idx_instrumento_convocacao_tipo"
        )
        banco["conv"].create_index(
            [("cpf", pymongo.ASCENDING), ("tipo", pymongo.ASCENDING)],
            unique=True,
            name="uq_conv_cpf_tipo",
            partialFilterExpression={"cpf": {"$type": "string"}},
        )
        banco["conv"].create_index([("cpf", pymongo.ASCENDING)], name="idx_conv_cpf")
    except PyMongoError as exc:
        logger.error("Erro ao criar índices no MongoDB: %s", exc)
        raise DatabaseError(f"Falha ao criar índices no MongoDB: {exc}") from exc
    logger.info("Índices do MongoDB criados/verificados com sucesso.")


# ---------------------------------------------------------------------------
# Verificações de existência (evita duplicatas)
# ---------------------------------------------------------------------------
def cpf_exists_in_conv(cpf: str, tipo: Optional[int] = None) -> bool:
    """Verifica se já existe um documento na collection `conv` para o CPF.

    Args:
        cpf: CPF (com ou sem formatação).
        tipo: se informado, restringe a verificação ao tipo de convocação.

    Returns:
        bool: True se já existir documento correspondente.
    """
    cpf_norm = sanitize_cpf(cpf)
    if not cpf_norm:
        return False

    filtro: dict[str, Any] = {"cpf": cpf_norm}
    if tipo is not None:
        filtro["tipo"] = tipo

    banco = get_database()
    try:
        return banco["conv"].find_one(filtro, {"_id": 1}) is not None
    except PyMongoError as exc:
        raise DatabaseError(f"Falha ao consultar a collection conv: {exc}") from exc


def cpf_exists_in_instrumento(cpf: str, tipo: Optional[int] = None) -> bool:
    """Verifica se já existe um documento em `instrumento_convocacao` para o CPF.

    Args:
        cpf: CPF (com ou sem formatação).
        tipo: se informado, restringe a verificação ao tipo de convocação.

    Returns:
        bool: True se já existir documento correspondente.
    """
    cpf_norm = sanitize_cpf(cpf)
    if not cpf_norm:
        return False

    filtro: dict[str, Any] = {"convocado_cpf": cpf_norm}
    if tipo is not None:
        filtro["tipo"] = tipo

    banco = get_database()
    try:
        return banco["instrumento_convocacao"].find_one(filtro, {"_id": 1}) is not None
    except PyMongoError as exc:
        raise DatabaseError(
            f"Falha ao consultar a collection instrumento_convocacao: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Inserções
# ---------------------------------------------------------------------------
def insert_instrumento_convocacao(
    tipo: int,
    data: Optional[date] = None,
    responsavel: Optional[str] = None,
    convocado_cpf: Optional[str] = None,
    orgao_convocador: Optional[str] = None,
    evitar_duplicata: bool = True,
) -> Optional[str]:
    """Insere um documento na collection `instrumento_convocacao`.

    Args:
        tipo: 0=treinamento, 1=1º turno, 2=2º turno.
        data: data associada à convocação.
        responsavel: responsável/assinante do instrumento.
        convocado_cpf: CPF do convocado (será normalizado para 11 dígitos).
        orgao_convocador: órgão emissor da convocação.
        evitar_duplicata: se True, não insere caso já exista CPF+tipo.

    Returns:
        str | None: id do documento inserido, ou None se ignorado (duplicata).
    """
    cpf_norm = sanitize_cpf(convocado_cpf) if convocado_cpf else None

    if evitar_duplicata and cpf_norm and cpf_exists_in_instrumento(cpf_norm, tipo):
        logger.info(
            "Instrumento de convocação já existente para CPF %s e tipo %s. Inserção ignorada.",
            cpf_norm, tipo,
        )
        return None

    documento = {
        "tipo": tipo,
        "data": data,
        "responsavel": responsavel,
        "convocado_cpf": cpf_norm,
        "orgao_convocador": orgao_convocador,
        "criado_em": _agora(),
    }
    banco = get_database()
    try:
        resultado = banco["instrumento_convocacao"].insert_one(documento)
    except DuplicateKeyError:
        logger.info(
            "Instrumento de convocação já existente (índice único) para CPF %s e tipo %s.",
            cpf_norm, tipo,
        )
        return None
    except PyMongoError as exc:
        logger.error("Erro ao inserir instrumento de convocação: %s", exc)
        raise DatabaseError(
            f"Falha ao inserir instrumento de convocação: {exc}"
        ) from exc

    novo_id = str(resultado.inserted_id)
    logger.info(
        "Instrumento de convocação inserido (id=%s, tipo=%s, cpf=%s).",
        novo_id, tipo, cpf_norm,
    )
    return novo_id


def buscar_registros_cpf(cpf: str) -> dict:
    """Retorna instrumentos e registros conv para o CPF informado.

    Args:
        cpf: CPF (com ou sem formatação).

    Returns:
        dict: {"instrumentos": [...], "conv": [...]} com uma lista de dicts.
    """
    cpf_limpo = sanitize_cpf(cpf)
    if not cpf_limpo:
        return {"instrumentos": [], "conv": []}

    banco = get_database()
    try:
        instrumentos = banco["instrumento_convocacao"].find(
            {"convocado_cpf": cpf_limpo},
            {
                "tipo": 1, "data": 1, "responsavel": 1,
                "orgao_convocador": 1, "criado_em": 1,
            },
        ).sort("tipo", pymongo.ASCENDING)
        conv = banco["conv"].find(
            {"cpf": cpf_limpo},
            {"cpf": 1, "tipo": 1, "data": 1, "realizado": 1, "criado_em": 1},
        ).sort("tipo", pymongo.ASCENDING)
        return {
            "instrumentos": [_mapear_documento(d) for d in instrumentos],
            "conv": [_mapear_documento(d) for d in conv],
        }
    except PyMongoError as exc:
        raise DatabaseError(f"Falha ao consultar registros do CPF: {exc}") from exc


# ---------------------------------------------------------------------------
# Documentos comprobatórios de participação (upload de PDFs no GridFS)
# ---------------------------------------------------------------------------
def documento_exists(cpf: str, tipo: int) -> bool:
    """Verifica se já existe um documento comprobatório para o CPF e tipo.

    Args:
        cpf: CPF (com ou sem formatação).
        tipo: 0=treinamento, 1=1º turno, 2=2º turno.

    Returns:
        bool: True se já existir comprovante correspondente.
    """
    cpf_norm = sanitize_cpf(cpf)
    if not cpf_norm:
        return False

    banco = get_database()
    try:
        achou = banco["documento_comprovante"].find_one(
            {"cpf": cpf_norm, "tipo": tipo}, {"_id": 1}
        )
        return achou is not None
    except PyMongoError as exc:
        raise DatabaseError(
            f"Falha ao consultar documentos comprobatórios: {exc}"
        ) from exc


def insert_documento_comprovante(
    cpf: Optional[str],
    tipo: int,
    nome_arquivo: Optional[str] = None,
    gridfs_file_id: Optional[str] = None,
    codigo_verificador: Optional[str] = None,
    codigo_crc: Optional[str] = None,
    url_conferencia: Optional[str] = None,
    assinatura_valida: bool = False,
    dias_ganhos: int = 0,
    evitar_duplicata: bool = True,
) -> Optional[str]:
    """Insere um documento na collection `documento_comprovante`.

    Args:
        cpf: CPF do participante (será normalizado para 11 dígitos).
        tipo: 0=treinamento, 1=1º turno, 2=2º turno.
        nome_arquivo: nome original do arquivo enviado.
        gridfs_file_id: id (str) do PDF já gravado no GridFS.
        codigo_verificador: código verificador de autenticidade do documento.
        codigo_crc: código CRC de autenticidade do documento.
        url_conferencia: URL oficial de conferência da autenticidade.
        assinatura_valida: se a assinatura foi identificada no documento.
        dias_ganhos: dias contabilizados por este documento.
        evitar_duplicata: se True, não insere caso já exista CPF+tipo.

    Returns:
        str | None: id do documento inserido, ou None se ignorado (duplicata).

    Raises:
        DatabaseError: se o gridfs_file_id for inválido ou a inserção falhar.
    """
    cpf_norm = sanitize_cpf(cpf) if cpf else None

    if evitar_duplicata and cpf_norm and documento_exists(cpf_norm, tipo):
        logger.info(
            "Documento comprobatório já existente para CPF %s e tipo %s. Inserção ignorada.",
            cpf_norm, tipo,
        )
        return None

    arquivo_oid: Optional[ObjectId] = None
    if gridfs_file_id is not None:
        try:
            arquivo_oid = ObjectId(str(gridfs_file_id))
        except (InvalidId, TypeError) as exc:
            raise DatabaseError(
                f"gridfs_file_id inválido: {gridfs_file_id!r}"
            ) from exc

    documento = {
        "cpf": cpf_norm,
        "tipo": tipo,
        "nome_arquivo": nome_arquivo,
        "gridfs_file_id": arquivo_oid,
        "codigo_verificador": codigo_verificador,
        "codigo_crc": codigo_crc,
        "url_conferencia": url_conferencia,
        "assinatura_valida": assinatura_valida,
        "dias_ganhos": dias_ganhos,
        "criado_em": _agora(),
    }
    banco = get_database()
    try:
        resultado = banco["documento_comprovante"].insert_one(documento)
    except DuplicateKeyError:
        logger.info(
            "Documento comprobatório já existente (índice único) para CPF %s e tipo %s.",
            cpf_norm, tipo,
        )
        return None
    except PyMongoError as exc:
        logger.error("Erro ao inserir documento comprobatório: %s", exc)
        raise DatabaseError(
            f"Falha ao inserir documento comprobatório: {exc}"
        ) from exc

    novo_id = str(resultado.inserted_id)
    logger.info(
        "Documento comprobatório inserido (id=%s, tipo=%s, cpf=%s, dias=%s).",
        novo_id, tipo, cpf_norm, dias_ganhos,
    )
    return novo_id


def buscar_documentos_cpf(cpf: str) -> list[dict]:
    """Retorna os documentos comprobatórios do CPF informado.

    Args:
        cpf: CPF (com ou sem formatação).

    Returns:
        list[dict]: uma entrada por documento, ordenada por tipo. As chaves são
            as mesmas da versão PostgreSQL, com ``gridfs_file_id`` no lugar de
            ``caminho_arquivo``.
    """
    cpf_limpo = sanitize_cpf(cpf)
    if not cpf_limpo:
        return []

    banco = get_database()
    try:
        docs = banco["documento_comprovante"].find(
            {"cpf": cpf_limpo},
            {
                "cpf": 1, "tipo": 1, "nome_arquivo": 1, "gridfs_file_id": 1,
                "codigo_verificador": 1, "codigo_crc": 1, "url_conferencia": 1,
                "assinatura_valida": 1, "dias_ganhos": 1, "criado_em": 1,
            },
        ).sort("tipo", pymongo.ASCENDING)
        return [_mapear_documento(d) for d in docs]
    except PyMongoError as exc:
        raise DatabaseError(
            f"Falha ao consultar documentos comprobatórios: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# GridFS — armazenamento binário dos PDFs
# ---------------------------------------------------------------------------
def _gridfs(banco: "pymongo.database.Database") -> "gridfs.GridFSBucket":
    """Retorna o bucket GridFS usado para os PDFs comprobatórios."""
    return gridfs.GridFSBucket(banco, bucket_name=BUCKET_DOCUMENTOS)


def upload_pdf(cpf: str, tipo: int, filename: str, file_bytes: bytes) -> str:
    """Grava os bytes de um PDF no GridFS.

    Args:
        cpf: CPF do participante (já normalizado).
        tipo: 0=treinamento, 1=1º turno, 2=2º turno.
        filename: nome original do arquivo.
        file_bytes: conteúdo binário do PDF.

    Returns:
        str: id do arquivo gravado no GridFS.

    Raises:
        DatabaseError: se a gravação falhar.
    """
    banco = get_database()
    try:
        arquivo_id = _gridfs(banco).upload_from_stream(
            filename or "documento.pdf",
            file_bytes,
            metadata={"cpf": cpf, "tipo": tipo, "filename": filename},
        )
    except PyMongoError as exc:
        logger.error("Erro ao gravar PDF no GridFS: %s", exc)
        raise DatabaseError(f"Falha ao gravar o PDF no GridFS: {exc}") from exc

    logger.info(
        "PDF gravado no GridFS (id=%s, cpf=%s, tipo=%s).", arquivo_id, cpf, tipo
    )
    return str(arquivo_id)


def apagar_pdf(arquivo_id: str) -> None:
    """Apaga um arquivo do GridFS (melhor esforço — falhas são apenas logadas).

    Usado na compensação quando a gravação dos metadados falha após o upload.
    """
    try:
        banco = get_database()
        _gridfs(banco).delete(ObjectId(str(arquivo_id)))
        logger.info("Arquivo GridFS %s apagado.", arquivo_id)
    except Exception as exc:  # noqa: BLE001 - compensação não deve propagar erro
        logger.warning("Falha ao apagar arquivo GridFS %s: %s", arquivo_id, exc)


def obter_pdf_documento(documento_id: str) -> Optional[bytes]:
    """Retorna o conteúdo binário do PDF vinculado a um documento comprobatório.

    Args:
        documento_id: id (str) do documento na collection `documento_comprovante`.

    Returns:
        bytes | None: conteúdo do PDF, ou None se o documento/arquivo não existir.

    Raises:
        DatabaseError: se a leitura do GridFS falhar.
    """
    banco = get_database()
    try:
        registro = banco["documento_comprovante"].find_one(
            {"_id": ObjectId(str(documento_id))}
        )
        if not registro or not registro.get("gridfs_file_id"):
            return None
        stream = io.BytesIO()
        _gridfs(banco).download_to_stream(registro["gridfs_file_id"], stream)
        return stream.getvalue()
    except (PyMongoError, InvalidId) as exc:
        logger.error("Erro ao obter PDF do documento %s: %s", documento_id, exc)
        raise DatabaseError(f"Falha ao obter o PDF do documento: {exc}") from exc


def registrar_comparecimento(cpf: str, tipo: int, data: Optional[date] = None) -> bool:
    """Marca o comparecimento como realizado na collection `conv` (upsert).

    Se já existir documento para o CPF+tipo, atualiza ``realizado`` para True;
    caso contrário, cria um novo documento já realizado.

    Args:
        cpf: CPF da pessoa (com ou sem formatação).
        tipo: 0=treinamento, 1=1º turno, 2=2º turno.
        data: data associada ao tipo (usada apenas em caso de criação).

    Returns:
        bool: True se o documento foi atualizado ou criado.
    """
    cpf_norm = sanitize_cpf(cpf)
    if not cpf_norm:
        return False

    banco = get_database()
    try:
        banco["conv"].update_one(
            {"cpf": cpf_norm, "tipo": tipo},
            {
                "$set": {"realizado": True},
                "$setOnInsert": {
                    "cpf": cpf_norm,
                    "tipo": tipo,
                    "data": data,
                    "criado_em": _agora(),
                },
            },
            upsert=True,
        )
    except PyMongoError as exc:
        raise DatabaseError(
            f"Falha ao registrar comparecimento: {exc}"
        ) from exc

    logger.info(
        "Comparecimento registrado como REALIZADO (cpf=%s, tipo=%s).", cpf_norm, tipo
    )
    return True


def insert_conv(
    cpf: Optional[str],
    tipo: int,
    data: Optional[date] = None,
    realizado: bool = False,
    evitar_duplicata: bool = True,
) -> Optional[str]:
    """Insere um documento na collection `conv` (controle de comparecimento).

    Args:
        cpf: CPF da pessoa (será normalizado para 11 dígitos).
        tipo: 0=treinamento, 1=1º turno, 2=2º turno.
        data: data associada ao tipo de convocação.
        realizado: se o comparecimento foi realizado (padrão False).
        evitar_duplicata: se True, não insere caso já exista CPF+tipo.

    Returns:
        str | None: id do documento inserido, ou None se ignorado (duplicata).
    """
    cpf_norm = sanitize_cpf(cpf) if cpf else None

    if evitar_duplicata and cpf_norm and cpf_exists_in_conv(cpf_norm, tipo):
        logger.info(
            "Registro de comparecimento já existente para CPF %s e tipo %s. Inserção ignorada.",
            cpf_norm, tipo,
        )
        return None

    documento = {
        "cpf": cpf_norm,
        "tipo": tipo,
        "data": data,
        "realizado": realizado,
        "criado_em": _agora(),
    }
    banco = get_database()
    try:
        resultado = banco["conv"].insert_one(documento)
    except DuplicateKeyError:
        logger.info(
            "Registro de comparecimento já existente (índice único) para CPF %s e tipo %s.",
            cpf_norm, tipo,
        )
        return None
    except PyMongoError as exc:
        logger.error("Erro ao inserir registro de comparecimento: %s", exc)
        raise DatabaseError(
            f"Falha ao inserir registro de comparecimento: {exc}"
        ) from exc

    novo_id = str(resultado.inserted_id)
    logger.info(
        "Registro de comparecimento inserido (id=%s, tipo=%s, cpf=%s).",
        novo_id, tipo, cpf_norm,
    )
    return novo_id
```

**Notas para o engenheiro:**
- As funções `get_database_url`, `get_connection` e `init_schema` (psycopg2) **deixam de existir**. Nada mais deve referenciá-las após a Task 5 (`ingest_pdfs.py` ainda referencia `init_schema` — corrigido lá; enquanto isso, não execute `ingest_pdfs.py --init-db`).
- `persistence_service.py` NÃO muda de lógica: ele só chama `db.insert_*` / `db.sanitize_cpf` / `db.DatabaseError`, que continuam com as mesmas assinaturas (apenas o tipo de retorno dos ids muda de `int` para `str`, e os consumidores tratam o id como opaco).

- [ ] **Step 4: Atualizar a docstring de `database/__init__.py`**

Conteúdo completo:

```python
"""Pacote de integração com o banco de dados MongoDB."""
```

- [ ] **Step 5: Rodar os testes e confirmar que PASSAM**

Run: `python -m pytest tests/test_database.py -v`
Expected: todos PASSAM (novos e antigos).

Run: `python -m pytest tests/ -v`
Expected: `tests/test_document_storage_service.py` ainda passa (ele desliga `PERSIST_TO_DB` e grava em disco — comportamento antigo, reescrito na Task 3). Se algum teste antigo de `test_document_storage_service.py` falhar por causa da remoção de funções do `db`, **não o corrija agora** — anote e prossiga; a Task 3 o reescreve por completo. (Com o código acima, ele deve continuar passando.)

- [ ] **Step 6: Commit**

```bash
git add database/db.py database/__init__.py tests/test_database.py
git commit -m "feat: reescrever camada de banco com pymongo e GridFS"
```

---

### Task 3: Reescrever o armazenamento de comprovantes (GridFS) — TDD

**Files:**
- Rewrite: `tests/test_document_storage_service.py`
- Modify: `services/document_storage_service.py`
- Modify: `components/comprovantes.py` (textos de UI)

- [ ] **Step 1: Reescrever `tests/test_document_storage_service.py` (conteúdo completo)**

```python
"""Testes do armazenamento dos documentos comprobatórios de participação.

A camada de banco (MongoDB + GridFS) é substituída por dublês via monkeypatch;
nenhum servidor real é necessário.
"""
import io
import itertools
from datetime import date

import pytest
from pypdf import PdfWriter

import database.db as db_mod
from config.settings import settings
from models.authenticity import AuthenticityReport
from services.document_storage_service import (
    extrair_data_evento,
    salvar_documento_comprovante,
)

CPF_TESTE = "11144477735"

TEXTO_EVENTOS = """
esteve à disposição da Justiça Eleitoral para receber instruções necessárias
TREINAMENTO no dia: 28/08/2026, das 8h às 12h.
que se realizarão no dia 04/10/2026 (1º turno) e no dia 25/10/2026
(2º turno, se houver).
"""


@pytest.fixture()
def db_falso(monkeypatch):
    """Dublês para a camada de banco (MongoDB + GridFS) com estado compartilhado."""
    estado = {
        "arquivos": {},       # arquivo_id -> bytes (GridFS)
        "documentos": {},     # (cpf, tipo) -> kwargs do metadado
        "comparecimentos": [],  # [(cpf, tipo)]
        "apagados": [],       # ids removidos do GridFS (compensação)
    }
    contador = itertools.count(1)

    monkeypatch.setattr(settings, "PERSIST_TO_DB", True)

    def fake_documento_exists(cpf, tipo):
        return (cpf, tipo) in estado["documentos"]

    def fake_upload_pdf(cpf, tipo, filename, file_bytes):
        arquivo_id = f"file_{next(contador)}"
        estado["arquivos"][arquivo_id] = file_bytes
        return arquivo_id

    def fake_insert_documento_comprovante(**kwargs):
        chave = (kwargs["cpf"], kwargs["tipo"])
        if chave in estado["documentos"]:
            return None
        documento_id = f"doc_{next(contador)}"
        estado["documentos"][chave] = {"id": documento_id, **kwargs}
        return documento_id

    def fake_registrar_comparecimento(cpf, tipo, data=None):
        estado["comparecimentos"].append((cpf, tipo))
        return True

    def fake_apagar_pdf(arquivo_id):
        estado["apagados"].append(arquivo_id)
        estado["arquivos"].pop(arquivo_id, None)

    monkeypatch.setattr(db_mod, "documento_exists", fake_documento_exists)
    monkeypatch.setattr(db_mod, "upload_pdf", fake_upload_pdf)
    monkeypatch.setattr(db_mod, "insert_documento_comprovante",
                        fake_insert_documento_comprovante)
    monkeypatch.setattr(db_mod, "registrar_comparecimento", fake_registrar_comparecimento)
    monkeypatch.setattr(db_mod, "apagar_pdf", fake_apagar_pdf)
    return estado


def _report_valido() -> AuthenticityReport:
    return AuthenticityReport(
        valido=True,
        codigo_verificador="3443939",
        codigo_crc="BCE2B28E",
        assinatura_eletronica={"signatario": "ISABELA DUARTE MELO", "data": "28/08/2026"},
    )


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Caminho feliz
# ---------------------------------------------------------------------------
def test_salvar_documento_valido_grava_gridfs_e_metadados(db_falso):
    conteudo = _pdf_bytes()
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE,
        tipo=1,
        file_bytes=conteudo,
        filename="comprovante 1º turno.pdf",
        report=_report_valido(),
    )
    assert resumo["sucesso"] is True
    assert resumo["dias"] == 4
    assert resumo["persistido"] is True
    assert resumo["erro"] is None
    assert resumo["gridfs_file_id"] in db_falso["arquivos"]
    assert db_falso["arquivos"][resumo["gridfs_file_id"]] == conteudo
    assert (CPF_TESTE, 1) in db_falso["documentos"]
    assert db_falso["comparecimentos"] == [(CPF_TESTE, 1)]


# ---------------------------------------------------------------------------
# Duplicatas
# ---------------------------------------------------------------------------
def test_segundo_envio_mesmo_tipo_e_recusado_como_duplicata(db_falso):
    primeiro = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=1, file_bytes=_pdf_bytes(),
        filename="a.pdf", report=_report_valido(),
    )
    assert primeiro["sucesso"] is True

    segundo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=1, file_bytes=_pdf_bytes(),
        filename="b.pdf", report=_report_valido(),
    )
    assert segundo["sucesso"] is False
    assert segundo["duplicado"] is True
    assert len(db_falso["arquivos"]) == 1  # nenhum arquivo extra no GridFS


# ---------------------------------------------------------------------------
# Validações de entrada (não tocam o banco)
# ---------------------------------------------------------------------------
def test_documento_invalido_nao_e_armazenado(db_falso):
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=1, file_bytes=_pdf_bytes(),
        filename="falso.pdf", report=AuthenticityReport(valido=False),
    )
    assert resumo["sucesso"] is False
    assert resumo["dias"] == 0
    assert not db_falso["arquivos"]


def test_cpf_invalido_nao_vincula_documento(db_falso):
    resumo = salvar_documento_comprovante(
        cpf_usuario="123", tipo=0, file_bytes=_pdf_bytes(),
        filename="treino.pdf", report=_report_valido(),
    )
    assert resumo["sucesso"] is False
    assert "CPF" in (resumo["erro"] or "")
    assert not db_falso["arquivos"]


def test_tipo_desconhecido_rejeitado(db_falso):
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=7, file_bytes=_pdf_bytes(),
        filename="x.pdf", report=_report_valido(),
    )
    assert resumo["sucesso"] is False
    assert not db_falso["arquivos"]


# ---------------------------------------------------------------------------
# Falhas do banco / GridFS
# ---------------------------------------------------------------------------
def test_mongo_indisponivel_recusa_upload(db_falso, monkeypatch):
    def fake_indisponivel(cpf, tipo):
        raise db_mod.DatabaseError("servidor fora do ar")

    monkeypatch.setattr(db_mod, "documento_exists", fake_indisponivel)
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=1, file_bytes=_pdf_bytes(),
        filename="a.pdf", report=_report_valido(),
    )
    assert resumo["sucesso"] is False
    assert "recusado" in (resumo["erro"] or "")
    assert not db_falso["arquivos"]


def test_falha_nos_metadados_apaga_arquivo_orfao(db_falso, monkeypatch):
    def fake_insert_quebrado(**kwargs):
        raise db_mod.DatabaseError("falha ao inserir metadados")

    monkeypatch.setattr(db_mod, "insert_documento_comprovante", fake_insert_quebrado)
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=1, file_bytes=_pdf_bytes(),
        filename="a.pdf", report=_report_valido(),
    )
    assert resumo["sucesso"] is False
    assert resumo["gridfs_file_id"] is None
    assert len(db_falso["apagados"]) == 1   # arquivo órfão compensado
    assert not db_falso["arquivos"]


def test_persistencia_desativada_recusa_upload(db_falso, monkeypatch):
    monkeypatch.setattr(settings, "PERSIST_TO_DB", False)
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=1, file_bytes=_pdf_bytes(),
        filename="a.pdf", report=_report_valido(),
    )
    assert resumo["sucesso"] is False
    assert "PERSIST_TO_DB" in (resumo["erro"] or "")
    assert not db_falso["arquivos"]


# ---------------------------------------------------------------------------
# Extração de data do evento (inalterado)
# ---------------------------------------------------------------------------
def test_extrair_data_evento_por_tipo():
    report = _report_valido()

    assert extrair_data_evento(TEXTO_EVENTOS, 0, report) == date(2026, 8, 28)
    assert extrair_data_evento(TEXTO_EVENTOS, 1, report) == date(2026, 10, 4)
    assert extrair_data_evento(TEXTO_EVENTOS, 2, report) == date(2026, 10, 25)


def test_extrair_data_evento_ausente():
    assert extrair_data_evento("", 1) is None
    # Treinamento sem data explícita usa a data da assinatura eletrônica
    report = _report_valido()
    assert extrair_data_evento("", 0, report) == date(2026, 8, 28)
```

- [ ] **Step 2: Rodar os testes e confirmar que FALHAM**

Run: `python -m pytest tests/test_document_storage_service.py -v`
Expected: os testes de upload FALHAM contra a implementação antiga (ex.: `KeyError: 'gridfs_file_id'`, `assert 'sucesso' is False` — a implementação antiga grava em disco e retorna outras chaves). Os testes de `extrair_data_evento` passam.

Nota: a execução falhante pode criar arquivos em `storage/documentos/11144477735/` (comportamento antigo). Apague a pasta se aparecer: `Remove-Item -Recurse -Force storage/documentos/11144477735`.

- [ ] **Step 3: Reescrever o armazenamento em `services/document_storage_service.py`**

Substituir **o arquivo inteiro** pelo conteúdo abaixo (as funções `extrair_data_evento` e as regex são mantidas; `_nome_arquivo_seguro` e a gravação em disco são removidas):

```python
"""Serviço de armazenamento dos documentos comprobatórios de participação.

Recebe os PDFs enviados por upload (já validados pelo serviço de
autenticidade), grava os arquivos no **MongoDB (GridFS)** e registra os
metadados na collection ``documento_comprovante``. Também marca o
comparecimento correspondente como realizado na collection ``conv``.

Não há gravação em disco: se o MongoDB estiver indisponível (ou a persistência
estiver desativada), o upload é **recusado** com uma mensagem clara. Se a
gravação dos metadados falhar após o upload do PDF, o arquivo órfão é apagado
do GridFS (compensação).
"""
from __future__ import annotations

import re
import logging
from datetime import date, datetime
from typing import Any, Optional

from config.settings import settings
from models.authenticity import AuthenticityReport
from services.days_service import DIAS_POR_TIPO, LABELS_POR_TIPO

logger = logging.getLogger(__name__)

# Data do evento por tipo, extraída do texto do documento quando possível
RE_DATA_TURNO = {
    1: re.compile(r"(\d{2}/\d{2}/\d{4})\s*\(1[ºo°]?\s*turno", re.IGNORECASE),
    2: re.compile(r"(\d{2}/\d{2}/\d{4})\s*\(2[ºo°]?\s*turno", re.IGNORECASE),
}
RE_DATA_TREINAMENTO = re.compile(
    r"treinamento[\s\S]{0,200}?no\s+dia\s*:?\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE
)


def extrair_data_evento(texto: str, tipo: int, report: AuthenticityReport | None = None) -> Optional[date]:
    """Extrai a data do evento correspondente ao tipo, quando presente no texto.

    Args:
        texto: texto integral extraído do PDF.
        tipo: 0=treinamento, 1=1º turno, 2=2º turno.
        report: relatório de autenticidade (para usar a data da assinatura
            eletrônica como data do treinamento, quando aplicável).

    Returns:
        date | None: data do evento ou None se não identificada.
    """
    candidata: Optional[str] = None

    if tipo == 0:
        match = RE_DATA_TREINAMENTO.search(texto or "")
        if match:
            candidata = match.group(1)
        elif report and report.assinatura_eletronica:
            candidata = report.assinatura_eletronica.get("data")
    elif tipo in RE_DATA_TURNO:
        match = RE_DATA_TURNO[tipo].search(texto or "")
        if match:
            candidata = match.group(1)

    if not candidata:
        return None
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", candidata)
    if not match:
        return None
    try:
        return datetime.strptime("/".join(match.groups()), "%d/%m/%Y").date()
    except ValueError:
        logger.warning("Data de evento inválida ignorada: %r", candidata)
        return None


def salvar_documento_comprovante(
    cpf_usuario: str | None,
    tipo: int,
    file_bytes: bytes,
    filename: str,
    report: AuthenticityReport,
    data_evento: Optional[date] = None,
) -> dict[str, Any]:
    """Armazena um documento comprobatório válido no MongoDB (GridFS + metadados).

    Args:
        cpf_usuario: CPF do usuário autenticado (qualquer formato).
        tipo: 0=treinamento, 1=1º turno, 2=2º turno.
        file_bytes: conteúdo binário do PDF validado.
        filename: nome original do arquivo enviado.
        report: relatório de autenticidade do documento (deve ser válido).
        data_evento: data do evento, quando identificada no documento.

    Returns:
        dict: resumo da operação:
            sucesso, tipo, dias, gridfs_file_id, persistido, duplicado, erro.
    """
    resumo: dict[str, Any] = {
        "sucesso": False,
        "tipo": tipo,
        "dias": 0,
        "gridfs_file_id": None,
        "persistido": False,
        "duplicado": False,
        "erro": None,
    }

    if not isinstance(report, AuthenticityReport) or not report.valido:
        resumo["erro"] = (
            "Documento não foi considerado válido (assinatura e/ou código de "
            "autenticidade ausentes). Os dias não serão contabilizados."
        )
        logger.warning("Armazenamento recusado para %s: documento inválido.", filename)
        return resumo

    if tipo not in DIAS_POR_TIPO:
        resumo["erro"] = f"Tipo de documento desconhecido: {tipo!r}."
        return resumo

    cpf_norm = re.sub(r"\D", "", str(cpf_usuario or ""))
    if len(cpf_norm) != 11:
        resumo["erro"] = "CPF do usuário inválido; não é possível vincular o documento."
        return resumo

    if not settings.PERSIST_TO_DB:
        resumo["erro"] = (
            "Persistência desativada (PERSIST_TO_DB=false): os documentos são "
            "armazenados apenas no MongoDB. Configure MONGO_URI e ative a "
            "persistência para permitir o envio."
        )
        logger.warning(resumo["erro"])
        return resumo

    from database import db

    # 0. Verifica duplicata antes de gravar o PDF; sem banco, upload é recusado
    try:
        if db.documento_exists(cpf_norm, tipo):
            resumo["duplicado"] = True
            resumo["erro"] = (
                f"Já existe um documento comprobatório registrado para "
                f"{LABELS_POR_TIPO[tipo]}. O envio foi ignorado (sem duplicatas)."
            )
            logger.info(resumo["erro"])
            return resumo
    except Exception as exc:  # noqa: BLE001 - sem MongoDB não há onde gravar
        resumo["erro"] = f"MongoDB indisponível; upload recusado: {exc}"
        logger.error(resumo["erro"])
        return resumo

    # 1. Grava o PDF no GridFS
    try:
        arquivo_id = db.upload_pdf(cpf_norm, tipo, filename, file_bytes)
        resumo["gridfs_file_id"] = arquivo_id
        resumo["dias"] = DIAS_POR_TIPO[tipo]
        logger.info("Documento comprobatório gravado no GridFS (id=%s).", arquivo_id)
    except Exception as exc:  # noqa: BLE001
        resumo["erro"] = f"Falha ao gravar o PDF no MongoDB (GridFS): {exc}"
        logger.error(resumo["erro"], exc_info=True)
        return resumo

    # 2. Registra os metadados e marca o comparecimento como realizado.
    #    Em caso de falha, apaga o arquivo recém-gravado (compensação).
    try:
        novo_id = db.insert_documento_comprovante(
            cpf=cpf_norm,
            tipo=tipo,
            nome_arquivo=filename,
            gridfs_file_id=arquivo_id,
            codigo_verificador=report.codigo_verificador,
            codigo_crc=report.codigo_crc,
            url_conferencia=report.url_conferencia,
            assinatura_valida=report.possui_assinatura,
            dias_ganhos=resumo["dias"],
        )
        if novo_id is None:
            # Duplicata detectada pelo índice único após a gravação do PDF
            db.apagar_pdf(arquivo_id)
            resumo["gridfs_file_id"] = None
            resumo["duplicado"] = True
            resumo["erro"] = (
                f"Já existe um documento comprobatório registrado para "
                f"{LABELS_POR_TIPO[tipo]}. O envio foi ignorado (sem duplicatas)."
            )
            logger.info(resumo["erro"])
            return resumo
        resumo["persistido"] = True
        db.registrar_comparecimento(cpf_norm, tipo, data_evento)
    except Exception as exc:  # noqa: BLE001 - falha total: remove o órfão
        db.apagar_pdf(arquivo_id)
        resumo["gridfs_file_id"] = None
        resumo["erro"] = f"PDF gravado, porém falha ao registrar os metadados: {exc}"
        logger.error(resumo["erro"], exc_info=True)
        return resumo

    resumo["sucesso"] = True
    return resumo
```

- [ ] **Step 4: Ajustar os textos de UI em `components/comprovantes.py`**

Edição 1 — substituir o bloco (aprox. linhas 162-166):

```python
    persistido_txt = (
        "Registro gravado no banco de dados."
        if resumo.get("persistido")
        else "Banco de dados indisponível — documento salvo apenas no servidor."
    )
```

por:

```python
    persistido_txt = "Documento gravado no MongoDB (GridFS)."
```

Edição 2 — substituir a linha (aprox. 247):

```python
        origem = "🗄️ banco de dados" if doc.get("persistido") else "💾 servidor (sessão)"
```

por:

```python
        origem = "🗄️ MongoDB (GridFS)" if doc.get("persistido") else "💾 sessão"
```

- [ ] **Step 5: Rodar os testes e confirmar que PASSAM**

Run: `python -m pytest tests/test_document_storage_service.py -v`
Expected: todos PASSAM.

Run: `python -m pytest tests/ -v`
Expected: todos PASSAM.

- [ ] **Step 6: Commit**

```bash
git add services/document_storage_service.py components/comprovantes.py tests/test_document_storage_service.py
git commit -m "feat: armazenar comprovantes no MongoDB GridFS com compensacao de falhas"
```

---

### Task 4: Configuração — `settings.py`, `.env`, `.env.example`

**Files:**
- Modify: `config/settings.py`
- Modify: `.env`
- Modify: `.env.example`

- [ ] **Step 1: Editar `config/settings.py`**

1. **Remover** o bloco do `DOCUMENTS_DIR` (linhas 26-27):

```python
    # Diretório definitivo dos documentos comprobatórios enviados por upload
    DOCUMENTS_DIR: Path = Path(os.getenv("DOCUMENTS_DIR", "storage/documentos"))
```

2. **Substituir** o bloco PostgreSQL (linhas 32-41) por:

```python
    # --- Integração com banco de dados MongoDB ---
    # URI de conexão do MongoDB. O nome do banco vem do path da URI
    # (ex.: mongodb://usuario:senha@host:27017/convocacoes). Sem path, usa "convocacoes".
    MONGO_URI: str | None = os.getenv("MONGO_URI")

    # Ativa a persistência automática dos dados extraídos no banco.
    # Por padrão fica habilitada quando existe uma MONGO_URI configurada.
    PERSIST_TO_DB: bool = os.getenv(
        "PERSIST_TO_DB",
        "true" if os.getenv("MONGO_URI") else "false",
    ).lower() in ("true", "1", "yes")
```

3. **Remover** a última linha do módulo:

```python
settings.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
```

(`settings.STORAGE_DIR.mkdir(...)` permanece.)

- [ ] **Step 2: Editar `.env`**

Substituir o bloco PostgreSQL (comentários DBeaver + `DATABASE_URL`) por:

```dotenv
# --- Integração com banco de dados MongoDB ---
# URI de conexão do MongoDB. O nome do banco vem do path (padrão: convocacoes).
# Docker local: mongodb://localhost:27017/convocacoes
MONGO_URI=mongodb://localhost:27017/convocacoes

# Ativa (true) ou desativa (false) a gravação automática dos dados no banco
PERSIST_TO_DB=true
```

Manter as demais variáveis (`PORT`, `MAX_FILE_SIZE_MB`, `USE_MOCK_EXTRACTION`, `STORAGE_DIR`, Keycloak, futuras integrações) como estão. Se existir linha `DOCUMENTS_DIR=...`, removê-la.

- [ ] **Step 3: Editar `.env.example`**

1. Remover o bloco:

```dotenv
# Diretório definitivo dos documentos comprobatórios enviados por upload
DOCUMENTS_DIR=storage/documentos
```

2. Substituir o bloco PostgreSQL (`DATABASE_URL` + comentários) por:

```dotenv
# --- Integração com banco de dados MongoDB ---
# URI de conexão do MongoDB. O nome do banco vem do path da URI.
# Exemplos:
#   Docker local:  mongodb://localhost:27017/convocacoes
#   Com autenticação: mongodb://usuario:senha@host:27017/convocacoes
MONGO_URI=mongodb://localhost:27017/convocacoes

# Ativa (true) ou desativa (false) a gravação automática dos dados no banco.
# Se não for definida, fica ativa automaticamente quando houver MONGO_URI.
PERSIST_TO_DB=true
```

- [ ] **Step 4: Verificar**

Run: `python -c "from config.settings import settings; print(settings.MONGO_URI, settings.PERSIST_TO_DB); assert not hasattr(settings, 'DOCUMENTS_DIR')"`
Expected: imprime a URI do `.env` e `True`, sem erro.

Run: `python -m pytest tests/ -v`
Expected: todos PASSAM (os testes de storage usam `monkeypatch` em `PERSIST_TO_DB` e não referenciam mais `DOCUMENTS_DIR`).

- [ ] **Step 5: Commit**

```bash
git add config/settings.py .env .env.example
git commit -m "chore: configurar MONGO_URI e remover DOCUMENTS_DIR"
```

---

### Task 5: Atualizar consumidores (textos, `--init-db`, docstrings)

**Files:**
- Modify: `ingest_pdfs.py`
- Modify: `components/results.py:291`
- Modify: `services/processing_service.py` (docstrings/mensagens)
- Modify: `database/persistence_service.py` (docstrings)

- [ ] **Step 1: `ingest_pdfs.py`**

Edições:

1. Docstring do módulo — substituir:

```python
"""Ingestão de PDFs via linha de comando: extrai e grava no PostgreSQL.

Uso:
    # Criar/verificar as tabelas no banco (executa database/schema.sql)
    python ingest_pdfs.py --init-db
```

por:

```python
"""Ingestão de PDFs via linha de comando: extrai e grava no MongoDB.

Uso:
    # Criar/verificar os índices das collections (ensure_indexes)
    python ingest_pdfs.py --init-db
```

e, na mesma docstring, substituir:

```python
Requer a variável de ambiente DATABASE_URL configurada (veja .env.example).
```

por:

```python
Requer a variável de ambiente MONGO_URI configurada (veja .env.example).
```

2. `argparse` — substituir:

```python
        description="Extrai dados de PDFs de convocação e grava no PostgreSQL."
```

por:

```python
        description="Extrai dados de PDFs de convocação e grava no MongoDB."
```

e substituir:

```python
        help="Cria/verifica as tabelas no banco (executa database/schema.sql).",
```

por:

```python
        help="Cria/verifica os índices das collections no MongoDB.",
```

3. Chamada de inicialização — substituir:

```python
    if args.init_db:
        db.init_schema()
        print("Schema criado/verificado com sucesso.")
```

por:

```python
    if args.init_db:
        db.ensure_indexes()
        print("Índices criados/verificados com sucesso.")
```

- [ ] **Step 2: `components/results.py`**

Substituir (linha ~291):

```python
        st.warning("🗄️ Integração com o banco indisponível (psycopg2 não instalado).")
```

por:

```python
        st.warning("🗄️ Integração com o banco indisponível (pymongo não instalado).")
```

- [ ] **Step 3: `services/processing_service.py`**

1. Docstring de `_persistir_no_banco` — substituir:

```python
    """Persiste os dados extraídos no PostgreSQL, se a integração estiver ativa.

    A persistência só ocorre quando:
      - settings.PERSIST_TO_DB está habilitado (DATABASE_URL configurada), e
```

por:

```python
    """Persiste os dados extraídos no MongoDB, se a integração estiver ativa.

    A persistência só ocorre quando:
      - settings.PERSIST_TO_DB está habilitado (MONGO_URI configurada), e
```

2. Comentário da importação tardia — substituir:

```python
        # Importação tardia para não exigir psycopg2 quando a integração está desativada.
```

por:

```python
        # Importação tardia para não exigir pymongo quando a integração está desativada.
```

3. Mensagem do `except ImportError` — substituir:

```python
            "Dependências de banco de dados ausentes (instale psycopg2-binary): %s", exc
```

por:

```python
            "Dependências de banco de dados ausentes (instale pymongo): %s", exc
```

4. Comentário do pipeline (linha ~182) — substituir:

```python
            # 3.1. Persiste automaticamente os dados extraídos no PostgreSQL
```

por:

```python
            # 3.1. Persiste automaticamente os dados extraídos no MongoDB
```

- [ ] **Step 4: `database/persistence_service.py` (somente docstrings)**

1. Docstring do módulo — substituir:

```python
Este módulo faz a ponte entre o resultado da extração (ExtractionResult.data)
e as tabelas do PostgreSQL (`instrumento_convocacao` e `conv`).
```

por:

```python
Este módulo faz a ponte entre o resultado da extração (ExtractionResult.data)
e as collections do MongoDB (`instrumento_convocacao` e `conv`).
```

2. Docstring de `persistir_extracao` — substituir:

```python
    """Persiste os dados extraídos de um PDF nas tabelas do PostgreSQL.

    Para cada tipo de convocação identificado (treinamento, 1º turno, 2º turno),
    cria (quando aplicável) um registro em `instrumento_convocacao` e um registro
    de controle em `conv`.
```

por:

```python
    """Persiste os dados extraídos de um PDF nas collections do MongoDB.

    Para cada tipo de convocação identificado (treinamento, 1º turno, 2º turno),
    cria (quando aplicável) um documento em `instrumento_convocacao` e um
    documento de controle em `conv`.
```

- [ ] **Step 5: Verificar resíduos**

Run: `rg -n "psycopg2|DATABASE_URL|init_schema|DOCUMENTS_DIR|caminho_arquivo" --glob "!docs/**" --glob "!*.md" .`
Expected: **nenhuma ocorrência** no código (apenas em `docs/` e `.md`, tratados na Task 7; `INTEGRACAO_DBEAVER.md`/`RELATORIO_INTEGRACAO.md` são removidos na Task 6).

Run: `python -m pytest tests/ -v`
Expected: todos PASSAM.

- [ ] **Step 6: Commit**

```bash
git add ingest_pdfs.py components/results.py services/processing_service.py database/persistence_service.py
git commit -m "refactor: atualizar consumidores para MongoDB (mensagens e init-db)"
```

---

### Task 6: Infraestrutura — docker-compose, schema.sql, docs obsoletas

**Files:**
- Rewrite: `docker-compose.yml`
- Delete: `database/schema.sql`
- Delete: `INTEGRACAO_DBEAVER.md`
- Delete: `RELATORIO_INTEGRACAO.md`

- [ ] **Step 1: Reescrever `docker-compose.yml` (conteúdo completo)**

O arquivo atual tem caracteres corrompidos de codificação nos comentários; a reescrita resolve isso.

```yaml
version: '3.8'

services:
  # Banco de dados MongoDB
  mongo:
    image: mongo:7
    container_name: mongo_convocacoes
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand('ping')"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: unless-stopped

  # Aplicação PDF Extractor
  pdf-extractor:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: pdf_extractor_app
    ports:
      - "8501:8501"
    environment:
      - PORT=8501
      - MAX_FILE_SIZE_MB=20
      - USE_MOCK_EXTRACTION=false
      - MONGO_URI=mongodb://mongo:27017/convocacoes
      - PERSIST_TO_DB=true
    volumes:
      - ./storage/temp:/app/storage/temp
    depends_on:
      mongo:
        condition: service_healthy
    restart: unless-stopped

volumes:
  mongo_data:
```

- [ ] **Step 2: Remover arquivos obsoletos**

```bash
git rm database/schema.sql INTEGRACAO_DBEAVER.md RELATORIO_INTEGRACAO.md
```

- [ ] **Step 3: Validar o compose (se o Docker estiver disponível)**

Run: `docker compose config --quiet`
Expected: sem saída e exit code 0. (Se o Docker não estiver instalado na máquina, pule este passo — a validação ocorre no primeiro `docker compose up`.)

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: trocar postgres por mongo:7 no docker-compose e remover schema.sql"
```

---

### Task 7: README + verificação final

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Atualizar `README.md`**

1. **Linha 12** — substituir:

```markdown
- **Banco de Dados:** PostgreSQL (via `psycopg2-binary`)
```

por:

```markdown
- **Banco de Dados:** MongoDB (via `pymongo`) — PDFs armazenados no **GridFS**
```

2. **Árvore do projeto (linhas 44-48)** — substituir:

```markdown
├── database/                   # Integração com o banco de dados PostgreSQL
│   ├── __init__.py
│   ├── schema.sql              # DDL das tabelas (instrumento_convocacao e conv)
│   ├── db.py                   # Conexão, inserções e verificação de duplicatas
│   └── persistence_service.py  # Mapeia os dados extraídos para as tabelas
```

por:

```markdown
├── database/                   # Integração com o banco de dados MongoDB
│   ├── __init__.py
│   ├── db.py                   # Conexão, índices, CRUD e GridFS (PDFs)
│   └── persistence_service.py  # Mapeia os dados extraídos para as collections
```

3. **Seção de configuração (linhas 99-107)** — substituir:

````markdown
Edite o arquivo `.env` e informe, principalmente, a URL de conexão do banco:

```dotenv
DATABASE_URL=postgresql://usuario:senha@host:5432/nome_do_banco
PERSIST_TO_DB=true
```

> Se `DATABASE_URL` não for definida, a aplicação continua funcionando normalmente,
> apenas **sem** gravar os dados no banco (`PERSIST_TO_DB` fica desativado por padrão).
````

por:

````markdown
Edite o arquivo `.env` e informe, principalmente, a URI de conexão do banco:

```dotenv
MONGO_URI=mongodb://usuario:senha@host:27017/nome_do_banco
PERSIST_TO_DB=true
```

> Se `MONGO_URI` não for definida, a extração continua funcionando, mas o
> **upload de comprovantes é recusado** — os PDFs são armazenados apenas no
> MongoDB (GridFS), sem gravação em disco.
````

4. **Seção "🗄️ Integração com Banco de Dados PostgreSQL" (linhas 119-186)** — substituir o título, a introdução, as tabelas e o trecho "Criar as tabelas no banco" por:

````markdown
## 🗄️ Integração com Banco de Dados MongoDB

A aplicação grava automaticamente os dados extraídos das cartas convocatórias em um
banco **MongoDB**, em três collections:

### Collections

**`instrumento_convocacao`** — registro de cada instrumento/carta de convocação:

| Campo              | Tipo     | Descrição                                                 |
|--------------------|----------|-----------------------------------------------------------|
| `_id`              | ObjectId | Identificador único                                       |
| `tipo`             | int      | `0` = treinamento (28/08), `1` = 1º turno, `2` = 2º turno |
| `data`             | date     | Data associada ao tipo de convocação                      |
| `responsavel`      | string   | Responsável/assinante do instrumento                      |
| `convocado_cpf`    | string   | CPF do convocado (apenas dígitos)                         |
| `orgao_convocador` | string   | Órgão que emitiu a convocação                             |

**`conv`** — controle de comparecimento por convocação:

| Campo       | Tipo     | Descrição                                              |
|-------------|----------|--------------------------------------------------------|
| `_id`       | ObjectId | Identificador único                                    |
| `cpf`       | string   | CPF da pessoa (apenas dígitos)                         |
| `tipo`      | int      | `0` = treinamento, `1` = 1º turno, `2` = 2º turno      |
| `data`      | date     | Data associada ao tipo                                 |
| `realizado` | bool     | Se o comparecimento foi realizado (padrão `false`)     |

**`documento_comprovante`** — metadados dos PDFs comprobatórios. O arquivo em si
fica no **GridFS** (bucket `documentos`), referenciado pelo campo `gridfs_file_id`.

### Criar os índices no banco

```bash
python ingest_pdfs.py --init-db
```

A operação é **idempotente**: cria índices únicos `(cpf, tipo)` /
`(convocado_cpf, tipo)` e pode ser repetida sem apagar dados.
````

Manter as subseções "Como os dados são gravados" e "Prevenção de duplicatas" como estão (continuam corretas), ajustando apenas, em "Prevenção de duplicatas", o final para mencionar os índices:

```markdown
Antes de inserir, o sistema verifica se já existe registro para o mesmo **CPF + tipo**
em cada collection. Se já existir, a inserção é **ignorada** (não duplica), e isso é
informado nos logs e no resumo de processamento. Índices **únicos** no MongoDB
garantem a integridade mesmo em condições de corrida.
```

5. **Linhas 213-214** — substituir:

```markdown
Os comprovantes válidos são gravados na tabela **`documento_comprovante`** e o
comparecimento correspondente é marcado como **realizado** na tabela `conv`.
```

por:

```markdown
Os comprovantes válidos são gravados no **GridFS** (PDF) e na collection
**`documento_comprovante`** (metadados); o comparecimento correspondente é
marcado como **realizado** na collection `conv`.
```

6. **Seção Docker Compose** — após `docker compose up -d`, acrescentar:

```markdown
O compose sobe o **MongoDB 7** (`mongo_convocacoes`, porta 27017) junto com a aplicação.
Na primeira execução, crie os índices com:

```bash
docker compose exec pdf-extractor python ingest_pdfs.py --init-db
```
```

- [ ] **Step 2: Verificação final — suíte completa**

Run: `python -m pytest tests/ -v`
Expected: todos os testes PASSAM, sem MongoDB real.

- [ ] **Step 3: Verificação final — resíduos de PostgreSQL**

Run: `rg -in "psycopg2|postgres|DATABASE_URL" --glob "!docs/**" .`
Expected: nenhuma ocorrência fora de `docs/`.

- [ ] **Step 4: Verificação final — smoke test da CLI**

Run: `python ingest_pdfs.py --test-conn`
Expected com MongoDB ativo (ex.: `docker compose up -d mongo`): `Conexão com o banco: OK`.
Sem MongoDB: `Conexão com o banco: FALHOU` (exit code 1) — comportamento esperado, sem traceback.

Opcional (com Docker): subir tudo e criar índices:

```bash
docker compose up -d
docker compose exec pdf-extractor python ingest_pdfs.py --init-db
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: atualizar README para MongoDB e GridFS"
```

---

## Critérios de aceite (visão geral)

1. `python -m pytest tests/ -v` passa 100% sem servidor MongoDB.
2. Nenhum código referencia psycopg2/PostgreSQL/`DATABASE_URL`/`DOCUMENTS_DIR`/`schema.sql`.
3. Upload de comprovante grava PDF no GridFS + metadados + comparecimento; falha de metadados apaga o arquivo órfão; Mongo indisponível recusa o upload.
4. `python ingest_pdfs.py --init-db` cria os índices; `--test-conn` faz ping.
5. `docker compose up -d` sobe `mongo:7` + app com `MONGO_URI` correta.
