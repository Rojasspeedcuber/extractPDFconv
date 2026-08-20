"""Testes unitários para validação de arquivos PDF."""
import io
import pytest
from pypdf import PdfWriter
from utils.file_validation import validate_pdf, format_file_size

def create_dummy_pdf_bytes(text: str = "Hello World") -> bytes:
    """Cria um PDF válido mínimo em memória para testes."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output_stream = io.BytesIO()
    writer.write(output_stream)
    return output_stream.getvalue()

def test_format_file_size():
    """Testa a formatação legível de bytes."""
    assert format_file_size(500) == "500 B"
    assert "KB" in format_file_size(2048)
    assert "MB" in format_file_size(5 * 1024 * 1024)

def test_validate_valid_pdf():
    """Testa a validação de um PDF íntegro."""
    pdf_bytes = create_dummy_pdf_bytes()
    is_valid, msg, size = validate_pdf(pdf_bytes, filename="documento.pdf", max_size_mb=20)
    assert is_valid is True
    assert "sucesso" in msg.lower()
    assert size > 0

def test_validate_non_pdf_extension():
    """Testa rejeição de arquivos que não possuem extensão .pdf."""
    dummy_data = b"Some plain text"
    is_valid, msg, _ = validate_pdf(dummy_data, filename="relatorio.txt")
    assert is_valid is False
    assert msg == "Este arquivo não é um PDF."

def test_validate_empty_file():
    """Testa rejeição de arquivo vazio."""
    empty_bytes = b""
    is_valid, msg, size = validate_pdf(empty_bytes, filename="vazio.pdf")
    assert is_valid is False
    assert msg == "O arquivo está vazio."
    assert size == 0

def test_validate_oversized_file():
    """Testa rejeição de arquivo que excede o limite estipulado."""
    pdf_bytes = create_dummy_pdf_bytes()
    # Força limite de tamanho de 0 MB (ou seja, 1 byte excede)
    is_valid, msg, size = validate_pdf(pdf_bytes, filename="grande.pdf", max_size_mb=0)
    assert is_valid is False
    assert "excede o limite" in msg

def test_validate_corrupted_pdf():
    """Testa arquivo com cabeçalho falso ou corrompido."""
    fake_pdf = b"%PDF-1.4 Fake content that is not a real PDF structure"
    is_valid, msg, _ = validate_pdf(fake_pdf, filename="corrompido.pdf")
    assert is_valid is False
    assert "Não foi possível ler o PDF." in msg or "Este arquivo não é um PDF." in msg
