"""Componente orquestrador do fluxo unificado de página única."""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def passo2_liberado(
    extraction_result: Any,
    persist_to_db: bool,
    cpf_usuario: str | None,
    carta_existe_no_banco: Callable[[str], bool],
) -> bool:
    """Decide se o Passo 2 (comprovantes) está liberado.

    Libera quando a carta convocatória foi processada com sucesso nesta sessão
    (``extraction_result.status == "completed"``) OU quando já existe um
    instrumento de convocação persistido no banco para o CPF do usuário.

    Args:
        extraction_result: resultado da extração da sessão (ou None).
        persist_to_db: flag de integração com o banco (settings.PERSIST_TO_DB).
        cpf_usuario: CPF do usuário autenticado (ou None).
        carta_existe_no_banco: função que recebe o CPF e indica se já existe
            instrumento de convocação no banco. Falhas são ignoradas.

    Returns:
        bool: True se o Passo 2 deve ser liberado.
    """
    if extraction_result is not None and getattr(extraction_result, "status", None) == "completed":
        return True

    if persist_to_db and cpf_usuario:
        try:
            if carta_existe_no_banco(cpf_usuario):
                return True
        except Exception as exc:  # noqa: BLE001 - indisponibilidade do banco não quebra a UI
            logger.warning("Falha ao consultar carta no banco para bloqueio: %s", exc)

    return False
