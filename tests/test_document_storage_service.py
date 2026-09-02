"""Testes do armazenamento dos documentos comprobatórios de participação."""
import io
from datetime import date

import pytest
from pypdf import PdfWriter

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
def storage_temporario(tmp_path, monkeypatch):
    """Redireciona o armazenamento para um diretório temporário e desliga o banco."""
    monkeypatch.setattr(settings, "DOCUMENTS_DIR", tmp_path)
    monkeypatch.setattr(settings, "PERSIST_TO_DB", False)
    return tmp_path


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


def test_salvar_documento_valido(storage_temporario):
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE,
        tipo=1,
        file_bytes=_pdf_bytes(),
        filename="comprovante 1º turno.pdf",
        report=_report_valido(),
    )
    assert resumo["sucesso"] is True
    assert resumo["dias"] == 4
    assert resumo["erro"] is None
    caminho = storage_temporario / CPF_TESTE
    assert caminho.exists()
    assert len(list(caminho.iterdir())) == 1


def test_documento_invalido_nao_e_armazenado(storage_temporario):
    """Documento sem autenticidade válida não é salvo nem contabilizado."""
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE,
        tipo=1,
        file_bytes=_pdf_bytes(),
        filename="falso.pdf",
        report=AuthenticityReport(valido=False),
    )
    assert resumo["sucesso"] is False
    assert resumo["dias"] == 0
    assert not list(storage_temporario.iterdir())


def test_cpf_invalido_nao_vincula_documento(storage_temporario):
    resumo = salvar_documento_comprovante(
        cpf_usuario="123",
        tipo=0,
        file_bytes=_pdf_bytes(),
        filename="treino.pdf",
        report=_report_valido(),
    )
    assert resumo["sucesso"] is False
    assert "CPF" in (resumo["erro"] or "")


def test_tipo_desconhecido_rejeitado(storage_temporario):
    resumo = salvar_documento_comprovante(
        cpf_usuario=CPF_TESTE,
        tipo=7,
        file_bytes=_pdf_bytes(),
        filename="x.pdf",
        report=_report_valido(),
    )
    assert resumo["sucesso"] is False


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
