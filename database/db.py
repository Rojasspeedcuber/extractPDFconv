"""Módulo de acesso ao banco de dados PostgreSQL para o projeto extractPDFconv.

Responsável por:
  - Abrir conexão com o PostgreSQL a partir da variável de ambiente DATABASE_URL.
  - Inserir registros nas tabelas `instrumento_convocacao` e `conv`.
  - Verificar a existência de um CPF antes de inserir (evitando duplicatas).

Todas as mensagens de log estão em português para facilitar o acompanhamento.
"""
from __future__ import annotations

import os
import re
import logging
from contextlib import contextmanager
from datetime import date
from typing import Any, Iterator, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env (se existir)
load_dotenv()

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Erro genérico relacionado a operações de banco de dados."""


def get_database_url() -> str:
    """Retorna a URL de conexão do PostgreSQL a partir do ambiente.

    Returns:
        str: valor de DATABASE_URL.

    Raises:
        DatabaseError: se a variável de ambiente não estiver configurada.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise DatabaseError(
            "A variável de ambiente DATABASE_URL não está definida. "
            "Configure-a no arquivo .env (veja o .env.example)."
        )
    return url


@contextmanager
def get_connection() -> Iterator["psycopg2.extensions.connection"]:
    """Gerenciador de contexto que abre e fecha uma conexão com o PostgreSQL.

    Faz commit automático em caso de sucesso e rollback em caso de erro.

    Yields:
        psycopg2.extensions.connection: conexão ativa com o banco.
    """
    conn = None
    try:
        conn = psycopg2.connect(get_database_url())
        logger.info("Conexão com o PostgreSQL estabelecida com sucesso.")
        yield conn
        conn.commit()
    except psycopg2.Error as exc:
        if conn is not None:
            conn.rollback()
        logger.error("Erro na operação com o banco de dados: %s", exc)
        raise DatabaseError(f"Falha na operação com o banco de dados: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()
            logger.info("Conexão com o PostgreSQL encerrada.")


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


def test_connection() -> bool:
    """Testa a conexão com o banco executando um SELECT simples.

    Returns:
        bool: True se a conexão foi bem sucedida.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        logger.info("Teste de conexão com o banco concluído com sucesso.")
        return True
    except DatabaseError:
        return False


def init_schema(schema_path: Optional[str] = None) -> None:
    """Executa o script de schema (schema.sql) para criar as tabelas.

    Args:
        schema_path: caminho do arquivo SQL. Se None, usa database/schema.sql.
    """
    if schema_path is None:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    with open(schema_path, "r", encoding="utf-8") as fh:
        sql = fh.read()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    logger.info("Schema do banco de dados criado/verificado com sucesso.")


# ---------------------------------------------------------------------------
# Verificações de existência (evita duplicatas)
# ---------------------------------------------------------------------------
def cpf_exists_in_conv(cpf: str, tipo: Optional[int] = None) -> bool:
    """Verifica se já existe um registro na tabela `conv` para o CPF informado.

    Args:
        cpf: CPF (com ou sem formatação).
        tipo: se informado, restringe a verificação ao tipo de convocação.

    Returns:
        bool: True se já existir registro correspondente.
    """
    cpf_norm = sanitize_cpf(cpf)
    if not cpf_norm:
        return False

    query = "SELECT 1 FROM conv WHERE cpf = %s"
    params: list[Any] = [cpf_norm]
    if tipo is not None:
        query += " AND tipo = %s"
        params.append(tipo)
    query += " LIMIT 1;"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone() is not None


def cpf_exists_in_instrumento(cpf: str, tipo: Optional[int] = None) -> bool:
    """Verifica se já existe um registro em `instrumento_convocacao` para o CPF.

    Args:
        cpf: CPF (com ou sem formatação).
        tipo: se informado, restringe a verificação ao tipo de convocação.

    Returns:
        bool: True se já existir registro correspondente.
    """
    cpf_norm = sanitize_cpf(cpf)
    if not cpf_norm:
        return False

    query = "SELECT 1 FROM instrumento_convocacao WHERE convocado_cpf = %s"
    params: list[Any] = [cpf_norm]
    if tipo is not None:
        query += " AND tipo = %s"
        params.append(tipo)
    query += " LIMIT 1;"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone() is not None


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
) -> Optional[int]:
    """Insere um registro na tabela `instrumento_convocacao`.

    Args:
        tipo: 0=treinamento, 1=1º turno, 2=2º turno.
        data: data associada à convocação.
        responsavel: responsável/assinante do instrumento.
        convocado_cpf: CPF do convocado (será normalizado para 11 dígitos).
        orgao_convocador: órgão emissor da convocação.
        evitar_duplicata: se True, não insere caso já exista CPF+tipo.

    Returns:
        int | None: id do registro inserido, ou None se ignorado.
    """
    cpf_norm = sanitize_cpf(convocado_cpf) if convocado_cpf else None

    if evitar_duplicata and cpf_norm and cpf_exists_in_instrumento(cpf_norm, tipo):
        logger.info(
            "Instrumento de convocação já existente para CPF %s e tipo %s. Inserção ignorada.",
            cpf_norm, tipo,
        )
        return None

    query = """
        INSERT INTO instrumento_convocacao
            (tipo, data, responsavel, convocado_cpf, orgao_convocador)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (tipo, data, responsavel, cpf_norm, orgao_convocador))
            novo_id = cur.fetchone()[0]
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
        dict: {"instrumentos": [...], "conv": [...]} com uma lista de dicts por linha.
    """
    cpf_limpo = sanitize_cpf(cpf)
    if not cpf_limpo:
        return {"instrumentos": [], "conv": []}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, tipo, data, responsavel, orgao_convocador, criado_em "
                "FROM instrumento_convocacao WHERE convocado_cpf = %s ORDER BY tipo",
                (cpf_limpo,),
            )
            instrumentos = cur.fetchall()
            cur.execute(
                "SELECT id, cpf, tipo, data, realizado, criado_em "
                "FROM conv WHERE cpf = %s ORDER BY tipo",
                (cpf_limpo,),
            )
            conv = cur.fetchall()

    return {
        "instrumentos": [
            dict(zip(
                ["id", "tipo", "data", "responsavel", "orgao_convocador", "criado_em"], r
            ))
            for r in instrumentos
        ],
        "conv": [
            dict(zip(["id", "cpf", "tipo", "data", "realizado", "criado_em"], r))
            for r in conv
        ],
    }


def insert_conv(
    cpf: Optional[str],
    tipo: int,
    data: Optional[date] = None,
    realizado: bool = False,
    evitar_duplicata: bool = True,
) -> Optional[int]:
    """Insere um registro na tabela `conv` (controle de comparecimento).

    Args:
        cpf: CPF da pessoa (será normalizado para 11 dígitos).
        tipo: 0=treinamento, 1=1º turno, 2=2º turno.
        data: data associada ao tipo de convocação.
        realizado: se o comparecimento foi realizado (padrão False).
        evitar_duplicata: se True, não insere caso já exista CPF+tipo.

    Returns:
        int | None: id do registro inserido, ou None se ignorado.
    """
    cpf_norm = sanitize_cpf(cpf) if cpf else None

    if evitar_duplicata and cpf_norm and cpf_exists_in_conv(cpf_norm, tipo):
        logger.info(
            "Registro de comparecimento já existente para CPF %s e tipo %s. Inserção ignorada.",
            cpf_norm, tipo,
        )
        return None

    query = """
        INSERT INTO conv (cpf, tipo, data, realizado)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (cpf_norm, tipo, data, realizado))
            novo_id = cur.fetchone()[0]
    logger.info(
        "Registro de comparecimento inserido (id=%s, tipo=%s, cpf=%s).",
        novo_id, tipo, cpf_norm,
    )
    return novo_id
