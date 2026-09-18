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
