"""Testes para o serviço de extração de dados e extrator de convocação eleitoral."""
import io
import pytest
from pypdf import PdfWriter
from config.settings import settings
from mocks.extraction_mock import get_mock_extraction_result
from services.extraction_service import (
    ExtractionService,
    ElectionSummonsExtractor,
    GenericDocumentExtractor,
    _extract_cpfs,
    _cpf_digitos_validos,
)
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


def test_election_summons_full_name_variations():
    """Valida a extração de nomes compostos e completos em diversos formatos de convocação."""
    extractor = ElectionSummonsExtractor()

    # Caso 1: Nome com quebra de linha e preposições (ex: MARIA DA CONCEIÇÃO SILVA)
    text_maria = """
    TRIBUNAL REGIONAL ELEITORAL DE PERNAMBUCO
    CARTA CONVOCATÓRIA
    A Juíza da 8ª Zona Eleitoral convoca o(a) Sr(a).
    MARIA
    DA CONCEIÇÃO SILVA para atuar, nas ELEIÇÕES GERAIS 2026, como
    ADMINISTRADOR(A) DE PRÉDIO, no Local de Votação PARÓQUIA DE SANTO ANTONIO ÁGUA FRIA/ARRUDA, situado na RUA CORONEL SEVERINO, 120, onde deverá comparecer...
    """
    res1 = extractor.extract(text_maria, [text_maria], {})
    assert res1["nome_convocado"] == "MARIA DA CONCEIÇÃO SILVA"
    assert res1["local_votacao"] == "PARÓQUIA DE SANTO ANTONIO ÁGUA FRIA/ARRUDA"
    assert "RUA CORONEL SEVERINO" in res1["endereco_local_votacao"]

    # Caso 2: Nome após Sr(a) com vírgula e inscrição eleitoral
    text_carlos = """
    TRIBUNAL REGIONAL ELEITORAL
    CONVOCAÇÃO ELEITORAL
    O Juiz Eleitoral convoca o(a) Sr(a). CARLOS EDUARDO DE ALBUQUERQUE JÚNIOR, inscrição eleitoral nº 123456789, para atuar como PRESIDENTE DE MESA...
    """
    res2 = extractor.extract(text_carlos, [text_carlos], {})
    assert res2["nome_convocado"] == "CARLOS EDUARDO DE ALBUQUERQUE JÚNIOR"

    # Caso 3: Nome após "Eleitor(a)"
    text_ana = """
    TRIBUNAL REGIONAL ELEITORAL
    CARTA CONVOCATÓRIA
    convoca o(a) eleitor(a) ANA PAULA DOS SANTOS FERREIRA para prestar serviços eleitorais...
    """
    res3 = extractor.extract(text_ana, [text_ana], {})
    assert res3["nome_convocado"] == "ANA PAULA DOS SANTOS FERREIRA"

def test_generic_document_extractor():
    """Testa extração de datas e dados gerais em outros PDFs."""
    text = "Relatório Financeiro emitido em 15/03/2026 para contato@empresa.com com valor de R$ 1.500,00."
    extractor = GenericDocumentExtractor()
    assert extractor.can_handle(text, {}) is True
    
    data = extractor.extract(text, [text], {})
    assert "15/03/2026" in data["datas_identificadas"]
    assert "contato@empresa.com" in data["emails_detectados"]



def test_extract_cpfs_com_mascara():
    """CPF com máscara deve ser detectado e normalizado no formato padrão."""
    texto = "Convoca o(a) Sr(a). Maria Santos, CPF: 111.444.777-35, para atuar."
    assert _extract_cpfs(texto) == ["111.444.777-35"]


def test_extract_cpfs_sem_mascara_rotulado():
    """CPF sem máscara, precedido de rótulo 'CPF', deve ser detectado."""
    texto = "Nome: Joao. CPF 11144477735 Zona 123."
    assert _extract_cpfs(texto) == ["111.444.777-35"]


def test_extract_cpfs_ignora_numeros_invalidos():
    """Sequências de 11 dígitos que não são CPF válido devem ser ignoradas."""
    texto = "Protocolo 12345678901 e processo 00000000000 sem CPF."
    assert _extract_cpfs(texto) == []


def test_cpf_digitos_validos():
    """Validação de dígitos verificadores do CPF."""
    assert _cpf_digitos_validos("11144477735") is True
    assert _cpf_digitos_validos("12345678900") is False
    assert _cpf_digitos_validos("00000000000") is False


def test_election_extractor_detecta_cpf_e_responsavel():
    """Carta convocatória deve popular cpfs_detectados e responsavel."""
    texto = (
        "TRIBUNAL REGIONAL ELEITORAL DE PERNAMBUCO\n"
        "CARTA CONVOCATORIA\n"
        "A Justica Eleitoral convoca o(a) Sr(a). Maria Santos da Silva,\n"
        "CPF: 111.444.777-35, para atuar nas ELEICOES 2026 como Mesaria.\n"
        "Responsavel: Dr. Joao Silva - Juiz Eleitoral.\n"
    )
    extractor = ElectionSummonsExtractor()
    assert extractor.can_handle(texto, {}) is True
    data = extractor.extract(texto, [texto], {})
    assert data["cpfs_detectados"] == ["111.444.777-35"]
    assert data["cpf_convocado"] == "111.444.777-35"
    assert data["responsavel"] == "Dr. Joao Silva - Juiz Eleitoral"
