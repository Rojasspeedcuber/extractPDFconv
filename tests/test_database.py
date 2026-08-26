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
    assert resumo["cpf_fonte"] is None


def test_persistir_extracao_cpf_do_pdf_tem_prioridade(monkeypatch):
    monkeypatch.setattr(db, "insert_instrumento_convocacao", lambda **k: 1)
    monkeypatch.setattr(db, "insert_conv", lambda **k: 1)
    data = {"cpfs_detectados": ["111.444.777-35"], "orgao_emissor": "TRE-PE"}
    resumo = ps.persistir_extracao(data, cpf_usuario="529.982.247-25")
    assert resumo["sucesso"] is True
    assert resumo["cpf"] == "11144477735"
    assert resumo["cpf_fonte"] == "pdf"


def test_persistir_extracao_fallback_cpf_usuario(monkeypatch):
    chamadas = []
    monkeypatch.setattr(db, "insert_instrumento_convocacao", lambda **k: chamadas.append(k) or 1)
    monkeypatch.setattr(db, "insert_conv", lambda **k: 1)
    # PDF sem CPF -> deve usar o CPF do usuário logado
    data = {"orgao_emissor": "TRE-PE", "nome_convocado": "Fulano"}
    resumo = ps.persistir_extracao(data, cpf_usuario="529.982.247-25")
    assert resumo["sucesso"] is True
    assert resumo["cpf"] == "52998224725"
    assert resumo["cpf_fonte"] == "usuario"
    assert chamadas and chamadas[0]["convocado_cpf"] == "52998224725"


def test_auth_cpf_valido():
    from components import auth
    assert auth._cpf_valido("111.444.777-35") == "11144477735"
    assert auth._cpf_valido("111.111.111-11") is None  # dígitos repetidos
    assert auth._cpf_valido("123") is None
    assert auth._cpf_valido(None) is None
    assert auth._formatar_cpf("11144477735") == "111.444.777-35"
