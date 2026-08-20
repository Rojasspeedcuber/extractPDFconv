"""Serviço para leitura, extração de texto e metadados de arquivos PDF."""
import os
import io
import logging
from pathlib import Path
from typing import BinaryIO, Any
from pypdf import PdfReader
from models.document import DocumentInfo
from utils.file_validation import format_file_size, validate_pdf
from config.settings import settings

logger = logging.getLogger(__name__)

class PDFService:
    """Manipulação e extração de baixo nível de PDFs."""

    @staticmethod
    def inspect_pdf(file_obj: BinaryIO | bytes | io.BytesIO, filename: str) -> DocumentInfo:
        """
        Inspeciona o PDF para obter metadados básicos (páginas, autor, título, etc.) sem extrair todo o texto.
        """
        is_valid, message, size_bytes = validate_pdf(file_obj, filename)
        formatted_size = format_file_size(size_bytes)
        
        doc_info = DocumentInfo(
            filename=filename,
            size_bytes=size_bytes,
            size_formatted=formatted_size,
            is_valid=is_valid,
            validation_message=message
        )
        
        if not is_valid:
            return doc_info

        try:
            if isinstance(file_obj, bytes):
                stream = io.BytesIO(file_obj)
            elif hasattr(file_obj, "getbuffer"):
                stream = io.BytesIO(file_obj.getbuffer())
            else:
                current_pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
                file_obj.seek(0)
                stream = io.BytesIO(file_obj.read())
                if hasattr(file_obj, "seek"):
                    file_obj.seek(current_pos)

            reader = PdfReader(stream)
            doc_info.page_count = len(reader.pages)
            
            # Extrai metadados do cabeçalho do PDF se disponíveis
            raw_meta = reader.metadata or {}
            metadata_dict: dict[str, Any] = {}
            for k, v in raw_meta.items():
                clean_k = str(k).lstrip("/").replace("/", "_")
                metadata_dict[clean_k] = str(v)

            doc_info.metadata = metadata_dict
            doc_info.title = metadata_dict.get("Title")
            doc_info.author = metadata_dict.get("Author")
            doc_info.creator = metadata_dict.get("Creator")
            doc_info.producer = metadata_dict.get("Producer")
            doc_info.creation_date = metadata_dict.get("CreationDate")

        except Exception as exc:
            logger.error(f"Erro ao extrair metadados do PDF {filename}: {exc}")
            doc_info.validation_message = f"Aviso ao ler metadados: {exc}"

        return doc_info

    @staticmethod
    def save_temp_file(file_obj: BinaryIO | bytes, filename: str) -> Path:
        """Salva com segurança o arquivo recebido em diretório temporário isolado."""
        safe_filename = Path(filename).name
        # Evita colisões de nomes usando timestamp ou id simples
        import time
        unique_prefix = int(time.time() * 1000)
        target_path = settings.STORAGE_DIR / f"{unique_prefix}_{safe_filename}"

        if isinstance(file_obj, bytes):
            with open(target_path, "wb") as f:
                f.write(file_obj)
        elif hasattr(file_obj, "getbuffer"):
            with open(target_path, "wb") as f:
                f.write(file_obj.getbuffer())
        else:
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            with open(target_path, "wb") as f:
                f.write(file_obj.read())

        logger.info(f"Arquivo temporário salvo em: {target_path}")
        return target_path

    @staticmethod
    def extract_full_text(pdf_path: str | Path) -> tuple[str, list[str]]:
        """
        Extrai o texto integral de todas as páginas do PDF.
        Retorna:
            tuple[str, list[str]]: (texto_completo, lista_de_textos_por_pagina)
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {pdf_path}")

        reader = PdfReader(str(path))
        pages_text: list[str] = []

        for idx, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
                pages_text.append(text)
            except Exception as e:
                logger.warning(f"Erro ao extrair texto da página {idx+1}: {e}")
                pages_text.append("")

        full_text = "\n\n--- PÁGINA ---\n\n".join(pages_text)
        return full_text, pages_text

    @staticmethod
    def cleanup_temp_file(file_path: str | Path | None) -> None:
        """Remove o arquivo temporário com segurança."""
        if not file_path:
            return
        try:
            p = Path(file_path)
            if p.exists() and p.is_file():
                p.unlink()
                logger.info(f"Arquivo temporário removido: {p}")
        except Exception as exc:
            logger.warning(f"Não foi possível remover arquivo temporário {file_path}: {exc}")
