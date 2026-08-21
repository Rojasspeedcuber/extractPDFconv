"""Ingestão de PDFs via linha de comando: extrai e grava no PostgreSQL.

Uso:
    # Criar/verificar as tabelas no banco (executa database/schema.sql)
    python ingest_pdfs.py --init-db

    # Testar a conexão com o banco
    python ingest_pdfs.py --test-conn

    # Processar um único PDF
    python ingest_pdfs.py caminho/para/convocacao.pdf

    # Processar todos os PDFs de uma pasta
    python ingest_pdfs.py caminho/para/pasta_de_pdfs/

Requer a variável de ambiente DATABASE_URL configurada (veja .env.example).
"""
from __future__ import annotations

import sys
import argparse
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ingest_pdfs")


def _processar_arquivo(pdf_path: Path) -> bool:
    """Extrai os dados de um PDF e grava no banco. Retorna True em caso de sucesso."""
    from services.extraction_service import extract_information
    from database.persistence_service import persistir_extracao

    logger.info("Processando arquivo: %s", pdf_path)
    resultado = extract_information(pdf_path)

    if resultado.status != "completed" or not resultado.data:
        logger.warning("Extração sem dados válidos para %s (status=%s).", pdf_path.name, resultado.status)
        return False

    resumo = persistir_extracao(resultado.data)
    if resumo.get("sucesso"):
        logger.info(
            "OK: %s -> %s instrumento(s), %s comparecimento(s), %s ignorado(s).",
            pdf_path.name,
            len(resumo.get("instrumentos_inseridos", [])),
            len(resumo.get("conv_inseridos", [])),
            len(resumo.get("ignorados", [])),
        )
        return True

    logger.error("Falha ao persistir %s: %s", pdf_path.name, resumo.get("erro"))
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extrai dados de PDFs de convocação e grava no PostgreSQL."
    )
    parser.add_argument(
        "caminho",
        nargs="?",
        help="Caminho de um arquivo PDF ou de uma pasta contendo PDFs.",
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Cria/verifica as tabelas no banco (executa database/schema.sql).",
    )
    parser.add_argument(
        "--test-conn",
        action="store_true",
        help="Testa a conexão com o banco de dados e encerra.",
    )
    args = parser.parse_args()

    from database import db

    if args.test_conn:
        ok = db.test_connection()
        print("Conexão com o banco: OK" if ok else "Conexão com o banco: FALHOU")
        return 0 if ok else 1

    if args.init_db:
        db.init_schema()
        print("Schema criado/verificado com sucesso.")
        if not args.caminho:
            return 0

    if not args.caminho:
        parser.print_help()
        return 1

    alvo = Path(args.caminho)
    if not alvo.exists():
        logger.error("Caminho não encontrado: %s", alvo)
        return 1

    if alvo.is_dir():
        pdfs = sorted(alvo.glob("*.pdf")) + sorted(alvo.glob("*.PDF"))
        if not pdfs:
            logger.warning("Nenhum arquivo PDF encontrado em %s", alvo)
            return 1
        total, sucesso = len(pdfs), 0
        for pdf in pdfs:
            if _processar_arquivo(pdf):
                sucesso += 1
        logger.info("Concluído: %s de %s arquivos processados com sucesso.", sucesso, total)
        return 0 if sucesso > 0 else 1

    # Arquivo único
    ok = _processar_arquivo(alvo)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
