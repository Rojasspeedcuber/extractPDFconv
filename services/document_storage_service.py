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
