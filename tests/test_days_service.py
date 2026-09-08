"""Testes do cálculo dos dias ganhos por participação nas eleições."""
from services.days_service import (
    DIAS_MAXIMOS,
    DIAS_POR_TIPO,
    MULTIPLICADOR_DIAS,
    TIPO_PRIMEIRO_TURNO,
    TIPO_SEGUNDO_TURNO,
    TIPO_TREINAMENTO,
    calcular_dias_ganhos,
)


def test_regra_dias_por_tipo():
    """Itens: Treinamento=1, 1º turno=4, 2º turno=4; máximo = soma x2 = 18."""
    assert DIAS_POR_TIPO[TIPO_TREINAMENTO] == 1
    assert DIAS_POR_TIPO[TIPO_PRIMEIRO_TURNO] == 4
    assert DIAS_POR_TIPO[TIPO_SEGUNDO_TURNO] == 4
    assert MULTIPLICADOR_DIAS == 2
    assert DIAS_MAXIMOS == 18


def test_nenhum_documento_zero_dias():
    """Sem upload de comprovantes, nenhum dia é contabilizado (0 x 2 = 0)."""
    resultado = calcular_dias_ganhos([])
    assert resultado["total"] == 0
    assert all(not item["comprovado"] for item in resultado["itens"])


def test_apenas_treinamento():
    """Somente o treinamento comprovado: 1 dia x 2 = 2."""
    resultado = calcular_dias_ganhos([TIPO_TREINAMENTO])
    assert resultado["total"] == 2


def test_treinamento_e_primeiro_turno():
    """Treinamento + 1º turno = (1 + 4) x 2 = 10 dias."""
    resultado = calcular_dias_ganhos([TIPO_TREINAMENTO, TIPO_PRIMEIRO_TURNO])
    assert resultado["total"] == 10


def test_todos_os_documentos_total_maximo():
    """Com os três comprovantes válidos, o total é o máximo ((1+4+4) x2 = 18)."""
    resultado = calcular_dias_ganhos(
        [TIPO_TREINAMENTO, TIPO_PRIMEIRO_TURNO, TIPO_SEGUNDO_TURNO]
    )
    assert resultado["total"] == DIAS_MAXIMOS == 18
    assert all(item["comprovado"] for item in resultado["itens"])


def test_tipo_desconhecido_ignorado():
    """Tipos fora do domínio não alteram o cálculo (1 x 2 = 2)."""
    resultado = calcular_dias_ganhos([TIPO_TREINAMENTO, 9, -1])
    assert resultado["total"] == 2


def test_itens_detalham_por_tipo():
    """Os itens detalham dias individuais (sem dobrar) e status por tipo."""
    resultado = calcular_dias_ganhos([TIPO_SEGUNDO_TURNO])
    por_tipo = {item["tipo"]: item for item in resultado["itens"]}
    assert por_tipo[TIPO_SEGUNDO_TURNO]["dias"] == 4
    assert por_tipo[TIPO_SEGUNDO_TURNO]["comprovado"] is True
    assert por_tipo[TIPO_TREINAMENTO]["dias"] == 0
    assert por_tipo[TIPO_TREINAMENTO]["comprovado"] is False
    # A soma é dobrada apenas no total, não nos itens individuais.
    assert resultado["total"] == 8
