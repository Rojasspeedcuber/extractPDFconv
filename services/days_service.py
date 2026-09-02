"""Serviço de cálculo dos dias ganhos por participação nas eleições.

Regra de negócio:
    - Treinamento  = 1 dia
    - 1º Turno     = 4 dias
    - 2º Turno     = 4 dias (soma multiplicada por 2: 2 dias x 2)

Cada parcela somente é contabilizada quando o documento comprobatório
correspondente foi enviado (upload) e considerado VÁLIDO pela verificação de
autenticidade (assinatura + código de autenticidade). Sem upload de um
determinado comprovante, os dias respectivos não são contabilizados.
"""
from __future__ import annotations

from typing import Any, Iterable

TIPO_TREINAMENTO = 0
TIPO_PRIMEIRO_TURNO = 1
TIPO_SEGUNDO_TURNO = 2

# Dias ganhos por tipo de participação comprovada
DIAS_POR_TIPO: dict[int, int] = {
    TIPO_TREINAMENTO: 1,
    TIPO_PRIMEIRO_TURNO: 4,
    TIPO_SEGUNDO_TURNO: 4,
}

LABELS_POR_TIPO: dict[int, str] = {
    TIPO_TREINAMENTO: "Treinamento",
    TIPO_PRIMEIRO_TURNO: "1º Turno",
    TIPO_SEGUNDO_TURNO: "2º Turno",
}

# Total máximo possível: 1 (treinamento) + 4 (1º turno) + 4 (2º turno) = 9 dias
DIAS_MAXIMOS = sum(DIAS_POR_TIPO.values())


def calcular_dias_ganhos(tipos_comprovados: Iterable[int]) -> dict[str, Any]:
    """Calcula os dias ganhos com base nos tipos de participação comprovada.

    Args:
        tipos_comprovados: coleção de tipos (0=treinamento, 1=1º turno,
            2=2º turno) cujos documentos foram enviados e validados.
            Tipos desconhecidos são ignorados.

    Returns:
        dict: {
            "itens": [{"tipo", "label", "dias", "comprovado"}, ...],
            "total": int,   # soma dos dias efetivamente ganhos
            "maximo": int,  # total máximo possível (9)
        }
    """
    comprovados = {t for t in (tipos_comprovados or []) if t in DIAS_POR_TIPO}

    itens: list[dict[str, Any]] = []
    total = 0
    for tipo in sorted(DIAS_POR_TIPO):
        comprovado = tipo in comprovados
        dias = DIAS_POR_TIPO[tipo] if comprovado else 0
        total += dias
        itens.append(
            {
                "tipo": tipo,
                "label": LABELS_POR_TIPO[tipo],
                "dias": dias,
                "comprovado": comprovado,
            }
        )

    return {"itens": itens, "total": total, "maximo": DIAS_MAXIMOS}
