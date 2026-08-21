"""Testes da camada de banco de dados (sem necessidade de PostgreSQL ativo).

As funções que acessam o banco são substituídas por dublês (monkeypatch),
permitindo validar a lógica de mapeamento/normalização isoladamente.
"""
from datetime import date

from database import db
from database import persistence_service as ps


# ---------------------------------------------------------------------------
# Normalização de CPF
# ---------------------------------------------------------------------------
def test_sanitize_cpf_valido():
    assert db.sanitize_cpf("123.456.789-00") == "12345678900"
    assert db.sanitize_cpf("12345678900") == "12345678900"


def test_sanitize_cpf_invalido():
    assert db.sanitize_cpf("123") is None
    assert db.sanitize_cpf("") is None
    assert db.sanitize_cpf(None) is None


# ---------------------------------------------------------------------------
# Conversão de datas no formato brasileiro
# ---------------------------------------------------------------------------
def test_parse_data_br():
    assert ps._parse_data_br("28/08/2026") == date(2026, 8, 28)
    assert ps._parse_data_br("dia 04/10/2026 (domingo)") == date(2026, 10, 4)
    assert ps._parse_data_br(None) is None
    assert ps._parse_data_br("sem data") is None


# ---------------------------------------------------------------------------
# Extração de datas por tipo
# ---------------------------------------------------------------------------
def test_extrair_datas_por_tipo():
    data = {
        "datas_identificadas": {
            "treinamento": {"data": "28/08/2026"},
            "primeiro_turno": {"datas": ["04/10/2026", "05/10/2026"]},
            "segundo_turno": {"datas": ["25/10/2026"]},
        }
    }
    resultado = ps._extrair_datas_por_tipo(data)
    assert resultado[ps.TIPO_TREINAMENTO] == date(2026, 8, 28)
    assert resultado[ps.TIPO_PRIMEIRO_TURNO] == date(2026, 10, 4)
    assert resultado[ps.TIPO_SEGUNDO_TURNO] == date(2026, 10, 25)


# ---------------------------------------------------------------------------
# Persistência (com dublês para as inserções)
# ---------------------------------------------------------------------------
def test_persistir_extracao_insere_todos_os_tipos(monkeypatch):
    chamadas_instr = []
    chamadas_conv = []

    def fake_insert_instrumento(**kwargs):
        chamadas_instr.append(kwargs)
        return len(chamadas_instr)

    def fake_insert_conv(**kwargs):
        chamadas_conv.append(kwargs)
        return len(chamadas_conv)

    monkeypatch.setattr(db, "insert_instrumento_convocacao", fake_insert_instrumento)
    monkeypatch.setattr(db, "insert_conv", fake_insert_conv)

    data = {
        "cpfs_detectados": ["111.222.333-44"],
        "orgao_emissor": "TRE-SP",
        "nome_convocado": "Fulano de Tal",
        "datas_identificadas": {
            "treinamento": {"data": "28/08/2026"},
            "primeiro_turno": {"datas": ["04/10/2026"]},
            "segundo_turno": {"datas": ["25/10/2026"]},
        },
    }
    resumo = ps.persistir_extracao(data)

    assert resumo["sucesso"] is True
    assert resumo["cpf"] == "11122233344"
    assert len(resumo["instrumentos_inseridos"]) == 3
    assert len(resumo["conv_inseridos"]) == 3
    # CPF normalizado deve ter sido repassado
    assert chamadas_instr[0]["convocado_cpf"] == "11122233344"
    assert chamadas_conv[0]["cpf"] == "11122233344"


def test_persistir_extracao_sem_cpf():
    resumo = ps.persistir_extracao({"orgao_emissor": "TRE-SP"})
    assert resumo["sucesso"] is False
    assert "CPF" in (resumo["erro"] or "")
