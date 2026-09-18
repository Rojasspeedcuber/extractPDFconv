"""Testes da camada de banco de dados (sem necessidade de PostgreSQL ativo).

As funções que acessam o banco são substituídas por dublês (monkeypatch),
permitindo validar a lógica de mapeamento/normalização isoladamente.
"""
from datetime import date

from database import db
from database import persistence_service as ps
from types import SimpleNamespace

from bson import ObjectId
from pymongo.errors import DuplicateKeyError


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


# ---------------------------------------------------------------------------
# Dublês para operações MongoDB (sem servidor real)
# ---------------------------------------------------------------------------
class _FakeCollection:
    def __init__(self):
        self.inseridos = []
        self.erro = None

    def insert_one(self, documento):
        if self.erro is not None:
            raise self.erro
        self.inseridos.append(documento)
        return SimpleNamespace(inserted_id=ObjectId())

    def find_one(self, filtro, projecao=None):
        return None


class _FakeDb:
    def __init__(self):
        self.colecoes = {}

    def __getitem__(self, nome):
        return self.colecoes.setdefault(nome, _FakeCollection())


# ---------------------------------------------------------------------------
# Mapeamento de documentos MongoDB
# ---------------------------------------------------------------------------
def test_mapear_documento_converte_ids():
    oid = ObjectId()
    gridfs_id = ObjectId()
    resultado = db._mapear_documento(
        {"_id": oid, "tipo": 1, "gridfs_file_id": gridfs_id}
    )
    assert resultado["id"] == str(oid)
    assert "_id" not in resultado
    assert resultado["gridfs_file_id"] == str(gridfs_id)


def test_mapear_documento_sem_gridfs():
    oid = ObjectId()
    resultado = db._mapear_documento({"_id": oid, "tipo": 0})
    assert resultado == {"id": str(oid), "tipo": 0}


# ---------------------------------------------------------------------------
# Inserção de documento comprobatório (com dublês)
# ---------------------------------------------------------------------------
def test_insert_documento_comprovante_grava_campos(monkeypatch):
    fake = _FakeDb()
    monkeypatch.setattr(db, "get_database", lambda: fake)
    gridfs_id = ObjectId()

    novo_id = db.insert_documento_comprovante(
        cpf="111.444.777-35",
        tipo=1,
        nome_arquivo="comprovante.pdf",
        gridfs_file_id=str(gridfs_id),
        codigo_verificador="3443939",
        codigo_crc="BCE2B28E",
        url_conferencia="https://example.gov.br/conferencia",
        assinatura_valida=True,
        dias_ganhos=4,
    )

    assert novo_id is not None
    gravado = fake["documento_comprovante"].inseridos[0]
    assert gravado["cpf"] == "11144477735"          # CPF normalizado
    assert gravado["tipo"] == 1
    assert gravado["nome_arquivo"] == "comprovante.pdf"
    assert gravado["gridfs_file_id"] == gridfs_id   # ObjectId, não str
    assert gravado["assinatura_valida"] is True
    assert gravado["dias_ganhos"] == 4
    assert gravado["criado_em"] is not None


def test_insert_documento_comprovante_duplicado_retorna_none(monkeypatch):
    fake = _FakeDb()
    fake["documento_comprovante"].erro = DuplicateKeyError("E11000 duplicate key")
    monkeypatch.setattr(db, "get_database", lambda: fake)

    resultado = db.insert_documento_comprovante(cpf="11144477735", tipo=1)
    assert resultado is None


def test_insert_documento_gridfs_id_invalido_lanca_erro(monkeypatch):
    import pytest

    fake = _FakeDb()
    monkeypatch.setattr(db, "get_database", lambda: fake)
    with pytest.raises(db.DatabaseError):
        db.insert_documento_comprovante(
            cpf="11144477735", tipo=1, gridfs_file_id="nao-e-objectid"
        )


# ---------------------------------------------------------------------------
# Comparecimento (upsert)
# ---------------------------------------------------------------------------
def test_registrar_comparecimento_faz_upsert(monkeypatch):
    fake = _FakeDb()
    atualizacoes = []
    fake["conv"].update_one = lambda filtro, update, upsert=False: atualizacoes.append(
        (filtro, update, upsert)
    )
    monkeypatch.setattr(db, "get_database", lambda: fake)

    assert db.registrar_comparecimento("111.444.777-35", 1) is True
    filtro, update, upsert = atualizacoes[0]
    assert filtro == {"cpf": "11144477735", "tipo": 1}
    assert update["$set"] == {"realizado": True}
    assert update["$setOnInsert"]["cpf"] == "11144477735"
    assert upsert is True


def test_registrar_comparecimento_cpf_invalido(monkeypatch):
    fake = _FakeDb()
    monkeypatch.setattr(db, "get_database", lambda: fake)
    assert db.registrar_comparecimento("123", 1) is False


# ---------------------------------------------------------------------------
# URI ausente
# ---------------------------------------------------------------------------
def test_get_mongo_uri_ausente_lanca_erro(monkeypatch):
    monkeypatch.delenv("MONGO_URI", raising=False)
    import pytest

    with pytest.raises(db.DatabaseError):
        db.get_mongo_uri()
