"""Serviço orquestrador do fluxo completo de upload, validação e extração."""
import logging
import io
from pathlib import Path
from typing import BinaryIO, Callable
from models.document import DocumentInfo
from models.extraction import ExtractionResult
from services.pdf_service import PDFService
from services.extraction_service import extract_information

logger = logging.getLogger(__name__)

class ProcessingService:
    """Orquestra o ciclo de vida completo do processamento de um documento PDF."""

    @staticmethod
    def process_document(
        file_obj: BinaryIO | bytes | io.BytesIO,
        filename: str,
        progress_callback: Callable[[str, float], None] | None = None
    ) -> tuple[DocumentInfo, ExtractionResult]:
        """
        Executa o pipeline completo:
        1. Validação
        2. Leitura de Metadados
        3. Salvamento Temporário
        4. Extração de Informações
        5. Limpeza de Recursos
        """
        def update_progress(msg: str, val: float):
            if progress_callback:
                progress_callback(msg, val)

        logger.info(f"Iniciando pipeline de processamento para {filename}")
        update_progress("Validando documento PDF...", 0.20)

        # 1. Inspeciona e valida
        doc_info = PDFService.inspect_pdf(file_obj, filename)
        if not doc_info.is_valid:
            logger.warning(f"Validação falhou para {filename}: {doc_info.validation_message}")
            return doc_info, ExtractionResult(
                status="error",
                error=doc_info.validation_message,
                document_type="Inválido"
            )

        temp_path: Path | None = None
        try:
            # 2. Armazena temporariamente
            update_progress("Preparando leitura do arquivo...", 0.45)
            temp_path = PDFService.save_temp_file(file_obj, filename)
            doc_info.temp_file_path = str(temp_path)

            # 3. Extrai informações
            update_progress("Extraindo dados e campos do PDF...", 0.75)
            extraction_result = extract_information(temp_path)

            # 4. Finalização
            update_progress("Finalizando processamento...", 1.0)
            logger.info(f"Processamento concluído para {filename}. Status: {extraction_result.status}")
            return doc_info, extraction_result

        except Exception as exc:
            logger.error(f"Falha inesperada no processamento de {filename}: {exc}", exc_info=True)
            return doc_info, ExtractionResult(
                status="error",
                error=f"Falha inesperada no processamento: {str(exc)}"
            )
        finally:
            # Limpa o arquivo temporário após o processamento para economizar disco
            if temp_path:
                PDFService.cleanup_temp_file(temp_path)
