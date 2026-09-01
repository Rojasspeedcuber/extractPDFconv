"""Testes do serviço de processamento (inclusão do CPF do usuário nos detectados)."""
import io

from pypdf import PdfWriter

from models.extraction import ExtractionResult
from services.processing_service import ProcessingService, _incluir_cpf_do_usuario


CPF_USUARIO = "11144477735"
CPF_USUARIO_FMT = "111.444.777-35"
CPF_PDF = "123.456.789-00"


def _resultado(data: dict) -> ExtractionResult:
    return ExtractionResult(
        status="completed",
        data=data,
        extracted_fields_count=len(data),
    )


def test_cpf_usuario_incluido_quando_pdf_sem_cpf():
    """Sem CPFs no PDF, o CPF informado no login passa a ser o único detectado."""
    res = _resultado({"nome_convocado": "Maria Santos"})
    _incluir_cpf_do_usuario(res, CPF_USUARIO)
    assert res.data["cpfs_detectados"] == [CPF_USUARIO_FMT]
    assert res.data["cpf_convocado"] == CPF_USUARIO_FMT


def test_cpf_usuario_acrescentado_apos_cpfs_do_pdf():
    """CPFs extraídos do PDF mantêm precedência; o do usuário entra ao final."""
    res = _resultado({"cpfs_detectados": [CPF_PDF], "cpf_convocado": CPF_PDF})
    _incluir_cpf_do_usuario(res, CPF_USUARIO)
    assert res.data["cpfs_detectados"] == [CPF_PDF, CPF_USUARIO_FMT]
    assert res.data["cpf_convocado"] == CPF_PDF


def test_cpf_usuario_nao_duplicado():
    """Se o CPF do usuário já foi detectado no PDF, a lista não muda."""
    res = _resultado({"cpfs_detectados": [CPF_USUARIO_FMT], "cpf_convocado": CPF_USUARIO_FMT})
    _incluir_cpf_do_usuario(res, CPF_USUARIO_FMT)
    assert res.data["cpfs_detectados"] == [CPF_USUARIO_FMT]


def test_cpf_usuario_invalido_ignorado():
    """CPF do usuário sem 11 dígitos não é incluído."""
    res = _resultado({"nome_convocado": "Maria Santos"})
    _incluir_cpf_do_usuario(res, "123")
    assert "cpfs_detectados" not in res.data


def test_resultado_com_erro_nao_alterado():
    """Resultados com erro não recebem o CPF do usuário."""
    res = ExtractionResult(status="error", error="falha", data={})
    _incluir_cpf_do_usuario(res, CPF_USUARIO)
    assert res.data == {}


def test_pipeline_inclui_cpf_do_usuario(monkeypatch):
    """Fluxo completo: o CPF informado na entrada aparece nos CPFs detectados."""
    from config.settings import settings

    monkeypatch.setattr(settings, "PERSIST_TO_DB", False)
    monkeypatch.setattr(settings, "USE_MOCK_EXTRACTION", True)

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    pdf_bytes = buffer.getvalue()

    doc_info, extraction_res = ProcessingService.process_document(
        pdf_bytes,
        "carta.pdf",
        cpf_usuario=CPF_USUARIO,
    )

    assert doc_info.is_valid
    assert extraction_res.status == "completed"
    assert CPF_USUARIO_FMT in extraction_res.data["cpfs_detectados"]
    assert extraction_res.data["cpf_convocado"] == CPF_USUARIO_FMT
