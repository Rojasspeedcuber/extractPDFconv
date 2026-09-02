"""Serviço de armazenamento dos documentos comprobatórios de participação.

Recebe os PDFs enviados por upload (já validados pelo serviço de
autenticidade), grava os arquivos em disco e registra os metadados no banco
de dados (quando a integração PostgreSQL estiver ativa). Também marca o
comparecimento correspondente como realizado na tabela ``conv``.
"""
from __future__ import annotations

import re
import time
import logging
from datetime import date, datetime
from pathlib import Path
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


def _nome_arquivo_seguro(filename: str) -> str:
    """Sanitiza o nome do arquivo removendo caracteres inseguros."""
    base = Path(filename or "documento.pdf").name
    seguro = re.sub(r"[^\w.\- ]+", "_", base).strip() or "documento.pdf"
    return seguro[:120]


def salvar_documento_comprovante(
    cpf_usuario: str | None,
    tipo: int,
    file_bytes: bytes,
    filename: str,
    report: AuthenticityReport,
    data_evento: Optional[date] = None,
) -> dict[str, Any]:
    """Armazena um documento comprobatório válido (arquivo + banco de dados).

    Args:
        cpf_usuario: CPF do usuário autenticado (qualquer formato).
        tipo: 0=treinamento, 1=1º turno, 2=2º turno.
        file_bytes: conteúdo binário do PDF validado.
        filename: nome original do arquivo enviado.
        report: relatório de autenticidade do documento (deve ser válido).
        data_evento: data do evento, quando identificada no documento.

    Returns:
        dict: resumo da operação:
            sucesso, tipo, dias, caminho, persistido, duplicado, erro.
    """
    resumo: dict[str, Any] = {
        "sucesso": False,
        "tipo": tipo,
        "dias": 0,
        "caminho": None,
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

    # Evita duplicidade no banco antes de gravar o arquivo em disco
    if settings.PERSIST_TO_DB:
        try:
            from database import db

            if db.documento_exists(cpf_norm, tipo):
                resumo["duplicado"] = True
                resumo["erro"] = (
                    f"Já existe um documento comprobatório registrado para "
                    f"{LABELS_POR_TIPO[tipo]}. O envio foi ignorado (sem duplicatas)."
                )
                logger.info(resumo["erro"])
                return resumo
        except Exception as exc:  # noqa: BLE001 - indisponibilidade do banco não impede salvar em disco
            logger.warning("Não foi possível verificar duplicatas no banco: %s", exc)

    # 1. Grava o arquivo em storage/documentos/<cpf>/
    try:
        pasta = settings.DOCUMENTS_DIR / cpf_norm
        pasta.mkdir(parents=True, exist_ok=True)
        rotulo = re.sub(r"[^\w]+", "_", LABELS_POR_TIPO[tipo])
        destino = pasta / f"{rotulo}_{int(time.time() * 1000)}_{_nome_arquivo_seguro(filename)}"
        destino.write_bytes(file_bytes)
        resumo["caminho"] = str(destino)
        resumo["dias"] = DIAS_POR_TIPO[tipo]
        logger.info("Documento comprobatório salvo em %s", destino)
    except Exception as exc:  # noqa: BLE001
        resumo["erro"] = f"Falha ao gravar o arquivo em disco: {exc}"
        logger.error(resumo["erro"], exc_info=True)
        return resumo

    # 2. Registra os metadados no banco e marca o comparecimento como realizado
    if settings.PERSIST_TO_DB:
        try:
            from database import db

            novo_id = db.insert_documento_comprovante(
                cpf=cpf_norm,
                tipo=tipo,
                nome_arquivo=filename,
                caminho_arquivo=resumo["caminho"],
                codigo_verificador=report.codigo_verificador,
                codigo_crc=report.codigo_crc,
                url_conferencia=report.url_conferencia,
                assinatura_valida=report.possui_assinatura,
                dias_ganhos=resumo["dias"],
            )
            resumo["persistido"] = novo_id is not None
            db.registrar_comparecimento(cpf_norm, tipo, data_evento)
        except Exception as exc:  # noqa: BLE001 - falha de banco não invalida o arquivo salvo
            resumo["erro"] = f"Arquivo salvo, porém falha ao gravar no banco: {exc}"
            logger.error(resumo["erro"], exc_info=True)

    resumo["sucesso"] = True
    return resumo
