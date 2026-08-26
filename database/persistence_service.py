"""Serviço de persistência: mapeia os dados extraídos dos PDFs para o banco.

Este módulo faz a ponte entre o resultado da extração (ExtractionResult.data)
e as tabelas do PostgreSQL (`instrumento_convocacao` e `conv`).

Convenção do campo "tipo":
    0 = Treinamento (28/08)
    1 = 1º Turno
    2 = 2º Turno
"""
from __future__ import annotations

import re
import logging
from datetime import date, datetime
from typing import Any, Optional

from database import db

logger = logging.getLogger(__name__)

# Mapeamento de tipo -> chave dentro de "datas_identificadas"
TIPO_TREINAMENTO = 0
TIPO_PRIMEIRO_TURNO = 1
TIPO_SEGUNDO_TURNO = 2


def _parse_data_br(valor: Optional[str]) -> Optional[date]:
    """Converte uma data no formato brasileiro (DD/MM/AAAA) em objeto date.

    Args:
        valor: string de data, ex.: '28/08/2026'.

    Returns:
        date | None: data convertida ou None se não for possível interpretar.
    """
    if not valor:
        return None
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(valor))
    if not match:
        return None
    dia, mes, ano = match.groups()
    try:
        return datetime.strptime(f"{dia}/{mes}/{ano}", "%d/%m/%Y").date()
    except ValueError:
        logger.warning("Data inválida ignorada: %r", valor)
        return None


def _primeiro_cpf(data: dict[str, Any]) -> Optional[str]:
    """Obtém o primeiro CPF detectado nos dados extraídos.

    Args:
        data: dicionário de dados extraídos do PDF.

    Returns:
        str | None: CPF (com máscara) ou None se nenhum encontrado.
    """
    cpfs = data.get("cpfs_detectados")
    if isinstance(cpfs, list) and cpfs:
        return cpfs[0]
    return None


def _extrair_datas_por_tipo(data: dict[str, Any]) -> dict[int, Optional[date]]:
    """Extrai as datas associadas a cada tipo de convocação.

    Args:
        data: dicionário de dados extraídos do PDF.

    Returns:
        dict[int, date | None]: mapeamento tipo -> data.
    """
    datas_info = data.get("datas_identificadas") or {}
    resultado: dict[int, Optional[date]] = {}
    data_treino: Optional[date] = None

    if isinstance(datas_info, dict):
        # Treinamento (tipo 0)
        treino = datas_info.get("treinamento") or {}
        if isinstance(treino, dict):
            data_treino = _parse_data_br(treino.get("data"))
            resultado[TIPO_TREINAMENTO] = data_treino

        # 1º Turno (tipo 1) — evita reutilizar a data do treinamento quando a
        # lista de datas do turno vier "poluída" com a data do treinamento.
        p_turno = datas_info.get("primeiro_turno") or {}
        if isinstance(p_turno, dict):
            datas_1t = [_parse_data_br(d) for d in (p_turno.get("datas") or [])]
            datas_1t = [d for d in datas_1t if d is not None]
            candidatas = [d for d in datas_1t if d != data_treino] or datas_1t
            resultado[TIPO_PRIMEIRO_TURNO] = candidatas[0] if candidatas else None

        # 2º Turno (tipo 2)
        s_turno = datas_info.get("segundo_turno") or {}
        if isinstance(s_turno, dict):
            datas_2t = [_parse_data_br(d) for d in (s_turno.get("datas") or [])]
            datas_2t = [d for d in datas_2t if d is not None and d != data_treino]
            resultado[TIPO_SEGUNDO_TURNO] = datas_2t[0] if datas_2t else None

    return resultado


def persistir_extracao(
    data: dict[str, Any],
    cpf_usuario: str | None = None,
) -> dict[str, Any]:
    """Persiste os dados extraídos de um PDF nas tabelas do PostgreSQL.

    Para cada tipo de convocação identificado (treinamento, 1º turno, 2º turno),
    cria (quando aplicável) um registro em `instrumento_convocacao` e um registro
    de controle em `conv`.

    Estratégia de definição do CPF:
        1. Tenta extrair o CPF do próprio PDF (``_primeiro_cpf``).
        2. Se não encontrar, usa ``cpf_usuario`` (CPF informado no login).
        3. Se nenhum estiver disponível, retorna erro.

    Args:
        data: dicionário `ExtractionResult.data` gerado pela extração.
        cpf_usuario: CPF do usuário autenticado, usado como fallback.

    Returns:
        dict: resumo da operação com contadores, ids inseridos e a fonte do CPF.
    """
    resumo: dict[str, Any] = {
        "sucesso": False,
        "cpf": None,
        "cpf_fonte": None,  # "pdf" | "usuario" | None
        "instrumentos_inseridos": [],
        "conv_inseridos": [],
        "ignorados": [],
        "erro": None,
    }

    if not isinstance(data, dict) or not data:
        resumo["erro"] = "Nenhum dado extraído para persistir."
        logger.warning(resumo["erro"])
        return resumo

    # 1. Tenta o CPF extraído do PDF
    cpf_raw = _primeiro_cpf(data)
    cpf_norm = db.sanitize_cpf(cpf_raw) if cpf_raw else None
    if cpf_norm:
        resumo["cpf_fonte"] = "pdf"
        logger.info("CPF extraído do PDF: %s", cpf_norm)
    else:
        # 2. Fallback: CPF fornecido pelo usuário na autenticação
        cpf_norm = db.sanitize_cpf(cpf_usuario) if cpf_usuario else None
        if cpf_norm:
            resumo["cpf_fonte"] = "usuario"
            logger.info("CPF fornecido pelo usuário na autenticação: %s", cpf_norm)

    resumo["cpf"] = cpf_norm

    if not cpf_norm:
        resumo["erro"] = (
            "Nenhum CPF válido foi detectado no documento nem informado no login; "
            "não é possível persistir os registros de convocação."
        )
        logger.warning(resumo["erro"])
        return resumo

    orgao = data.get("orgao_emissor") or data.get("orgao_convocador")
    responsavel = (
        data.get("responsavel")
        or data.get("nome_convocado")  # fallback informativo
    )

    datas_por_tipo = _extrair_datas_por_tipo(data)

    # Garante ao menos um registro (treinamento) mesmo sem datas específicas,
    # desde que exista um CPF válido.
    if not datas_por_tipo:
        datas_por_tipo = {TIPO_TREINAMENTO: None}

    try:
        for tipo, data_evento in sorted(datas_por_tipo.items()):
            # Insere o instrumento de convocação
            instrumento_id = db.insert_instrumento_convocacao(
                tipo=tipo,
                data=data_evento,
                responsavel=responsavel,
                convocado_cpf=cpf_norm,
                orgao_convocador=orgao,
            )
            if instrumento_id is not None:
                resumo["instrumentos_inseridos"].append(
                    {"id": instrumento_id, "tipo": tipo}
                )
            else:
                resumo["ignorados"].append(
                    {"tabela": "instrumento_convocacao", "tipo": tipo, "motivo": "duplicata"}
                )

            # Insere o controle de comparecimento
            conv_id = db.insert_conv(
                cpf=cpf_norm,
                tipo=tipo,
                data=data_evento,
                realizado=False,
            )
            if conv_id is not None:
                resumo["conv_inseridos"].append({"id": conv_id, "tipo": tipo})
            else:
                resumo["ignorados"].append(
                    {"tabela": "conv", "tipo": tipo, "motivo": "duplicata"}
                )

        resumo["sucesso"] = True
        logger.info(
            "Persistência concluída para CPF %s: %s instrumento(s), %s conv, %s ignorado(s).",
            cpf_norm,
            len(resumo["instrumentos_inseridos"]),
            len(resumo["conv_inseridos"]),
            len(resumo["ignorados"]),
        )
    except db.DatabaseError as exc:
        resumo["erro"] = str(exc)
        logger.error("Erro ao persistir extração no banco: %s", exc)

    return resumo
