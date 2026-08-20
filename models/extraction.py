"""Modelo de dados para o resultado da extração."""
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ExtractionResult:
    """Resultado padronizado e tipado da extração de dados do documento."""
    status: str  # "completed", "error", "pending"
    data: dict[str, Any] = field(default_factory=dict)
    summary: str | None = None
    extracted_fields_count: int = 0
    document_type: str = "Documento Geral"
    processing_time_seconds: float = 0.0
    error: str | None = None
