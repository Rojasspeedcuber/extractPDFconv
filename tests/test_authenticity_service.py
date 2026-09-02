"""Testes do serviço de verificação de autenticidade (assinatura + códigos)."""
import os

import pytest

from services.authenticity_service import (
    analisar_texto,
    conferir_crc,
    extrair_assinatura_textual,
    extrair_codigos_autenticidade,
    verify_pdf_authenticity,
)

# Texto no padrão dos documentos SEI da Justiça Eleitoral (TRE-PE)
TEXTO_SEI_VALIDO = """
TRIBUNAL REGIONAL ELEITORAL DE PERNAMBUCO
DECLARAÇÃO Nº 3508 / 2026 - TRE-PE/PRES/DG/ZE008
De ordem da Exma. Juíza Eleitoral da 8ª Zona, declaro que CLEODON INACIO DOS
SANTOS FILHO esteve à disposição da Justiça Eleitoral nesta data.
Recife, na data da assinatura eletrônica.
Documento assinado eletronicamente por ISABELA DUARTE MELO, Técnico(a)
Judiciário(a), em 28/08/2026, às 10:23, conforme art. 1º, § 2º, III, "b",
da Lei 11.419/2006.
A autenticidade do documento pode ser conferida no site
http://sei.tre-pe.jus.br/sei/controlador_externo.php?
acao=documento_conferir&id_orgao_acesso_externo=0 informando o código
verificador 3443939 e o código CRC BCE2B28E.
"""

TEXTO_SEM_ASSINATURA = """
DECLARAÇÃO Nº 1 / 2026
informando o código verificador 1234567 e o código CRC ABCD1234.
"""

TEXTO_SEM_CODIGOS = """
Documento assinado eletronicamente por MARIA SILVA, Analista, em 01/01/2026,
às 09:00, conforme art. 1º, § 2º, III, "b", da Lei 11.419/2006.
"""

PDF_EXEMPLO = os.path.join(
    os.path.dirname(__file__), "..", "Cleodon Inácio dos Santos Filho.pdf"
)


def test_extrai_assinatura_textual_padrao_sei():
    assinatura = extrair_assinatura_textual(TEXTO_SEI_VALIDO)
    assert assinatura is not None
    assert assinatura["signatario"] == "ISABELA DUARTE MELO"
    assert assinatura["data"] == "28/08/2026"
    assert assinatura["hora"] == "10:23"
    assert "11.419/2006" in (assinatura["fundamento"] or "")


def test_extrai_codigos_de_autenticidade():
    codigos = extrair_codigos_autenticidade(TEXTO_SEI_VALIDO)
    assert codigos["codigo_verificador"] == "3443939"
    assert codigos["codigo_crc"] == "BCE2B28E"
    assert "controlador_externo" in (codigos["url_conferencia"] or "")
    # A URL deve ser reconstruída mesmo com quebra de linha no meio
    assert " " not in codigos["url_conferencia"]


def test_documento_valido_com_assinatura_e_codigos():
    report = analisar_texto(TEXTO_SEI_VALIDO)
    assert report.valido is True
    assert report.possui_assinatura is True
    assert report.possui_codigos is True


def test_documento_invalido_sem_assinatura():
    """Sem assinatura identificada, o documento não é válido."""
    report = analisar_texto(TEXTO_SEM_ASSINATURA)
    assert report.valido is False
    assert report.possui_codigos is True


def test_documento_invalido_sem_codigos():
    """Sem os códigos de autenticidade, o documento não é válido."""
    report = analisar_texto(TEXTO_SEM_CODIGOS)
    assert report.valido is False
    assert report.possui_assinatura is True


def test_documento_vazio_invalido():
    report = analisar_texto("")
    assert report.valido is False


def test_conferir_crc_best_effort():
    """O CRC é conferido quando coincide com alguma normalização do texto."""
    import zlib

    texto = "conteudo de teste para crc"
    crc = format(zlib.crc32(texto.encode("utf-8")) & 0xFFFFFFFF, "08X")
    assert conferir_crc(texto, crc) is True
    assert conferir_crc(texto, "00000000") is False


def test_conferir_crc_formato_invalido():
    assert conferir_crc("qualquer texto", "NAOHEX") is False
    assert conferir_crc("qualquer texto", "") is False


def test_to_dict_serializavel():
    report = analisar_texto(TEXTO_SEI_VALIDO)
    dados = report.to_dict()
    assert dados["valido"] is True
    assert dados["codigo_verificador"] == "3443939"
    assert isinstance(dados["detalhes"], list)


@pytest.mark.skipif(
    not os.path.exists(PDF_EXEMPLO), reason="PDF de exemplo não encontrado no projeto"
)
def test_verificacao_completa_do_pdf_de_exemplo():
    """Fluxo completo sobre a declaração real do TRE-PE incluída no projeto."""
    with open(PDF_EXEMPLO, "rb") as fh:
        conteudo = fh.read()

    report = verify_pdf_authenticity(conteudo, "Cleodon Inácio dos Santos Filho.pdf")

    assert report.valido is True
    assert report.possui_assinatura is True
    assert report.codigo_verificador == "3443939"
    assert report.codigo_crc == "BCE2B28E"
    assert report.assinatura_eletronica is not None
    assert report.assinatura_eletronica["signatario"] == "ISABELA DUARTE MELO"


def test_verificacao_bytes_invalidos():
    report = verify_pdf_authenticity(b"isto nao e um pdf", "lixo.pdf")
    assert report.valido is False
