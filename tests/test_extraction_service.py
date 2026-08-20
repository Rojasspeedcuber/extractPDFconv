"""Testes para o serviço de extração de dados e extrator de convocação eleitoral."""
import io
import pytest
from pypdf import PdfWriter
from config.settings import settings
from mocks.extraction_mock import get_mock_extraction_result
from services.extraction_service import ExtractionService, ElectionSummonsExtractor, GenericDocumentExtractor
from models.extraction import ExtractionResult

def test_mock_extraction():
    """Testa se o mock retorna uma estrutura de ExtractionResult válida."""
    mock_res = get_mock_extraction_result()
    assert isinstance(mock_res, ExtractionResult)
    assert mock_res.status == "completed"
    assert "campo_exemplo_1" in mock_res.data
    assert mock_res.extracted_fields_count > 0

def test_election_summons_extractor():
    """Testa a extração dos campos de carta convocatória (exemplo do prompt)."""
    sample_text = """
    TRIBUNAL REGIONAL ELEITORAL DE PERNAMBUCO
    CARTA CONVOCATÓRIA
    A Juíza Eleitoral da 8ª Zona, com base no Código Eleitoral, convoca o(a) Sr(a).
    CLEODON INACIO DOS SANTOS FILHO para atuar, nas ELEIÇÕES GERAIS 2026, como
    ADMINISTRADOR(A) DE PRÉDIO, no Local de Votação ESCOLA PROFESSOR ALFREDO
    FREYRE, situado na RUA ZEFERINO AGRA, 193 ARRUDA - RECIFE/PE , onde deverá
    comparecer no horário estabelecido pelo Cartório Eleitoral, nos dias 02/10/2026, 03/10/2026, 04/10/2026
    (domingo, primeiro turno) e 05/10/2026 e, se houver segundo turno, 23/10/2026, 24/10/2026, 25/10/2026
    (domingo, segundo turno) e 26/10/2026.
    Para desempenhar a função para a qual foi convocado(a), deverá participar do
    TREINAMENTO, na modalidade presencial, na ESCOLA TÉCNICA PROFESSOR AGAMENON
    MAGALHÃES - ETEPAM, no endereço AV. JOÃO DE BARROS, 1769 ENCRUZILHADA, no dia:
    28/08/2026, das 8h às 12h.
    Fica o(a) senhor(a) também ciente de que, além das datas supracitadas, será realizada
    uma VISTORIA no local de votação no dia 23/07/2026.
    ... transferência temporária ... no período de 20/07/2026 a 28/08/2026.
    Recife, 25 de junho de 2026
    PATRÍCIA RODRIGUES RAMOS GALVÃO
    Documento assinado eletronicamente por PATRÍCIA RODRIGUES RAMOS GALVÃO em 21/07/2026, às 11:54
    """

    extractor = ElectionSummonsExtractor()
    assert extractor.can_handle(sample_text, {}) is True

    extracted = extractor.extract(sample_text, [sample_text], {})
    
    # Valida nome do convocado
    assert extracted["nome_convocado"] == "CLEODON INACIO DOS SANTOS FILHO"
    # Valida cargo/função
    assert "ADMINISTRADOR(A) DE PRÉDIO" in extracted["funcao_cargo"]
    # Valida local de votação
    assert "ESCOLA PROFESSOR ALFREDO FREYRE" in extracted["local_votacao"]
    # Valida zona
    assert "8ª Zona" in extracted["zona_eleitoral"]
    
    # Valida datas
    datas = extracted["datas_identificadas"]
    assert "primeiro_turno" in datas
    assert "04/10/2026" in datas["primeiro_turno"]["datas"]
    assert "segundo_turno" in datas
    assert "25/10/2026" in datas["segundo_turno"]["datas"]
    assert datas["treinamento"]["data"] == "28/08/2026"
    assert datas["vistoria"]["data"] == "23/07/2026"
    assert datas["transferencia_temporaria"]["inicio"] == "20/07/2026"
    assert "25 de junho de 2026" in datas["data_emissao"]

def test_generic_document_extractor():
    """Testa extração de datas e dados gerais em outros PDFs."""
    text = "Relatório Financeiro emitido em 15/03/2026 para contato@empresa.com com valor de R$ 1.500,00."
    extractor = GenericDocumentExtractor()
    assert extractor.can_handle(text, {}) is True
    
    data = extractor.extract(text, [text], {})
    assert "15/03/2026" in data["datas_identificadas"]
    assert "contato@empresa.com" in data["emails_detectados"]
