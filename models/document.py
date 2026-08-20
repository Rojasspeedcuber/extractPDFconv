"""Modelo de dados para informações do documento."""
from dataclasses import dataclass, field
from typing import Any

@dataclass
class DocumentInfo:
    """Informações e metadados básicos de um arquivo PDF carregado."""
    filename: str
    size_bytes: int
    size_formatted: str
    content_type: str = "application/pdf"
    page_count: int = 0
    title: str | None = None
    author: str | None = None
    creator: str | None = None
    producer: str | None = None
    creation_date: str | None = None
    is_valid: bool = False
    validation_message: str = ""
    temp_file_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
