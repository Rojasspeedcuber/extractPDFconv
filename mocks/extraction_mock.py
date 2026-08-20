"""Mock de extração de informações para testes da interface."""
from models.extraction import ExtractionResult

def get_mock_extraction_result() -> ExtractionResult:
    """Retorna dados simulados para validação da interface sem processamento real."""
    mock_data = {
        "campo_exemplo_1": "Valor exemplo 1",
        "campo_exemplo_2": "Valor exemplo 2",
        "campo_exemplo_3": "Valor exemplo 3",
        "numero_processo": "0015243-28.2026.6.17.8008",
        "status_documento": "Ativo",
        "total_registros": 42,
        "itens_demonstracao": [
            "Item Exemplo A",
            "Item Exemplo B",
            "Item Exemplo C"
        ],
        "metadados_adicionais": {
            "origem": "Sistema Mock",
            "ambiente": "Desenvolvimento",
            "versao_schema": "1.0"
        }
    }
    
    return ExtractionResult(
        status="completed",
        document_type="Exemplo (Modo Mock)",
        summary="Extração simulada executada com sucesso através do mock de desenvolvimento.",
        extracted_fields_count=len(mock_data),
        data=mock_data,
        processing_time_seconds=0.15
    )
