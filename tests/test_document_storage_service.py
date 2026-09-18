"""Testes do armazenamento dos documentos comprobatórios de participação.

A camada de banco (MongoDB + GridFS) é substituída por dublês via monkeypatch;
nenhum servidor real é necessário.
"""
import io
import itertools
from datetime import date

import pytest
from pypdf import PdfWriter

import database.db as db_mod
from config.settings import settings
from models.authenticity import AuthenticityReport
from services.document_storage_service import (
    extrair_data_evento,
    salvar_documento_comprovante,
)

CPF_TESTE = "11144477735"

TEXTO_EVENTOS = """
esteve à disposição da Justiça Eleitoral para receber instruções necessárias
TREINAMENTO no dia: 28/08/2026, das 8h às 12h.
que se realizarão no dia 04/10/2026 (1º turno) e no dia 25/10/2026
(2º turno, se houver).
"""


@pytest.fixture()
def db_falso(monkeypatch):
    """Dublês para a camada de banco (MongoDB + GridFS) com estado compartilhado."""
    estado = {
        "arquivos": {},       # arquivo_id -> bytes (GridFS)
        "documentos": {},     # (cpf, tipo) -> kwargs do metadado
        "comparecimentos": [],  # [(cpf, tipo)]
        "apagados": [],       # ids removidos do GridFS (compensação)
    }
    contador = itertools.count(1)

    monkeypatch.setattr(settings, "PERSIST_TO_DB", True)

    def fake_documento_exists(cpf, tipo):
        return (cpf, tipo) in estado["documentos"]

    def fake_upload_pdf(cpf, tipo, filename, file_bytes):
        arquivo_id = f"file_{next(contador)}"
        estado["arquivos"][arquivo_id] = file_bytes
        return arquivo_id

    def fake_insert_documento_comprovante(**kwargs):
        chave = (kwargs["cpf"], kwargs["tipo"])
        if chave in estado["documentos"]:
            return None
        documento_id = f"doc_{next(contador)}"
        estado["documentos"][chave] = {"id": documento_id, **kwargs}
        return documento_id

    def fake_registrar_comparecimento(cpf, tipo, data=None):
        estado["comparecimentos"].append((cpf, tipo))
        return True

    def fake_apagar_pdf(arquivo_id):
        estado["apagados"].append(arquivo_id)
        estado["arquivos"].pop(arquivo_id, None)

    monkeypatch.setattr(db_mod, "documento_exists", fake_documento_exists)
    monkeypatch.setattr(db_mod, "upload_pdf", fake_upload_pdf)
    monkeypatch.setattr(db_mod, "insert_documento_comprovante",
                        fake_insert_documento_comprovante)
    monkeypatch.setattr(db_mod, "registrar_comparecimento", fake_registrar_comparecimento)
    monkeypatch.setattr(db_mod, "apagar_pdf", fake_apagar_pdf)
    return estado


def _report_valido() -> AuthenticityReport:
    return AuthenticityReport(
        valido=True,
        codigo_verificador="3443939",
        codigo_crc="BCE2B28E",
        assinatura_eletronica={"signatario": "ISABELA DUARTE MELO", "data": "28/08/2026"},
    )


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Caminho feliz
# ---------------------------------------------------------------------------
def test_salvar_documento_valido_grava_gridfs_e_metadados(db_falso):
    conteudo = _pdf_bytes()
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE,
        tipo=1,
        file_bytes=conteudo,
        filename="comprovante 1º turno.pdf",
        report=_report_valido(),
    )
    assert resumo["sucesso"] is True
    assert resumo["dias"] == 4
    assert resumo["persistido"] is True
    assert resumo["erro"] is None
    assert resumo["gridfs_file_id"] in db_falso["arquivos"]
    assert db_falso["arquivos"][resumo["gridfs_file_id"]] == conteudo
    assert (CPF_TESTE, 1) in db_falso["documentos"]
    assert db_falso["comparecimentos"] == [(CPF_TESTE, 1)]


# ---------------------------------------------------------------------------
# Duplicatas
# ---------------------------------------------------------------------------
def test_segundo_envio_mesmo_tipo_e_recusado_como_duplicata(db_falso):
    primeiro = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=1, file_bytes=_pdf_bytes(),
        filename="a.pdf", report=_report_valido(),
    )
    assert primeiro["sucesso"] is True

    segundo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=1, file_bytes=_pdf_bytes(),
        filename="b.pdf", report=_report_valido(),
    )
    assert segundo["sucesso"] is False
    assert segundo["duplicado"] is True
    assert len(db_falso["arquivos"]) == 1  # nenhum arquivo extra no GridFS


# ---------------------------------------------------------------------------
# Validações de entrada (não tocam o banco)
# ---------------------------------------------------------------------------
def test_documento_invalido_nao_e_armazenado(db_falso):
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=1, file_bytes=_pdf_bytes(),
        filename="falso.pdf", report=AuthenticityReport(valido=False),
    )
    assert resumo["sucesso"] is False
    assert resumo["dias"] == 0
    assert not db_falso["arquivos"]


def test_cpf_invalido_nao_vincula_documento(db_falso):
    resumo = salvar_documento_comprovante(
        cpf_usuario="123", tipo=0, file_bytes=_pdf_bytes(),
        filename="treino.pdf", report=_report_valido(),
    )
    assert resumo["sucesso"] is False
    assert "CPF" in (resumo["erro"] or "")
    assert not db_falso["arquivos"]


def test_tipo_desconhecido_rejeitado(db_falso):
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=7, file_bytes=_pdf_bytes(),
        filename="x.pdf", report=_report_valido(),
    )
    assert resumo["sucesso"] is False
    assert not db_falso["arquivos"]


# ---------------------------------------------------------------------------
# Falhas do banco / GridFS
# ---------------------------------------------------------------------------
def test_mongo_indisponivel_recusa_upload(db_falso, monkeypatch):
    def fake_indisponivel(cpf, tipo):
        raise db_mod.DatabaseError("servidor fora do ar")

    monkeypatch.setattr(db_mod, "documento_exists", fake_indisponivel)
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=1, file_bytes=_pdf_bytes(),
        filename="a.pdf", report=_report_valido(),
    )
    assert resumo["sucesso"] is False
    assert "recusado" in (resumo["erro"] or "")
    assert not db_falso["arquivos"]


def test_falha_nos_metadados_apaga_arquivo_orfao(db_falso, monkeypatch):
    def fake_insert_quebrado(**kwargs):
        raise db_mod.DatabaseError("falha ao inserir metadados")

    monkeypatch.setattr(db_mod, "insert_documento_comprovante", fake_insert_quebrado)
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=1, file_bytes=_pdf_bytes(),
        filename="a.pdf", report=_report_valido(),
    )
    assert resumo["sucesso"] is False
    assert resumo["gridfs_file_id"] is None
    assert len(db_falso["apagados"]) == 1   # arquivo órfão compensado
    assert not db_falso["arquivos"]


def test_persistencia_desativada_recusa_upload(db_falso, monkeypatch):
    monkeypatch.setattr(settings, "PERSIST_TO_DB", False)
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE, tipo=1, file_bytes=_pdf_bytes(),
        filename="a.pdf", report=_report_valido(),
    )
    assert resumo["sucesso"] is False
    assert "PERSIST_TO_DB" in (resumo["erro"] or "")
    assert not db_falso["arquivos"]


# ---------------------------------------------------------------------------
# Extração de data do evento (inalterado)
# ---------------------------------------------------------------------------
def test_extrair_data_evento_por_tipo():
    report = _report_valido()

    assert extrair_data_evento(TEXTO_EVENTOS, 0, report) == date(2026, 8, 28)
    assert extrair_data_evento(TEXTO_EVENTOS, 1, report) == date(2026, 10, 4)
    assert extrair_data_evento(TEXTO_EVENTOS, 2, report) == date(2026, 10, 25)


def test_extrair_data_evento_ausente():
    assert extrair_data_evento("", 1) is None
    # Treinamento sem data explícita usa a data da assinatura eletrônica
    report = _report_valido()
    assert extrair_data_evento("", 0, report) == date(2026, 8, 28)
