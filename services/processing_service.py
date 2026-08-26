"""Serviço orquestrador do fluxo completo de upload, validação e extração."""
import logging
import io
from pathlib import Path
from typing import BinaryIO, Callable
from models.document import DocumentInfo
from models.extraction import ExtractionResult
from services.pdf_service import PDFService
from services.extraction_service import extract_information
from config.settings import settings

logger = logging.getLogger(__name__)


def _persistir_no_banco(
    extraction_result: ExtractionResult,
    cpf_usuario: str | None = None,
) -> None:
    """Persiste os dados extraídos no PostgreSQL, se a integração estiver ativa.

    A persistência só ocorre quando:
      - settings.PERSIST_TO_DB está habilitado (DATABASE_URL configurada), e
      - a extração foi concluída com sucesso e possui dados.

    Args:
        extraction_result: resultado da extração.
        cpf_usuario: CPF do usuário autenticado (usado como fallback quando o
            PDF não contém um CPF detectável).

    Erros de banco são registrados em log e NÃO interrompem o fluxo do app.
    """
    if not settings.PERSIST_TO_DB:
        logger.info("Persistência no banco desativada (PERSIST_TO_DB=false). Etapa ignorada.")
        return

    if extraction_result.status != "completed" or not extraction_result.data:
        logger.info("Extração sem dados válidos; nada a persistir no banco.")
        return

    try:
        # Importação tardia para não exigir psycopg2 quando a integração está desativada.
        from database.persistence_service import persistir_extracao

        resumo = persistir_extracao(extraction_result.data, cpf_usuario=cpf_usuario)
        if resumo.get("sucesso"):
            logger.info(
                "Dados persistidos no banco: %s instrumento(s), %s registro(s) de comparecimento.",
                len(resumo.get("instrumentos_inseridos", [])),
                len(resumo.get("conv_inseridos", [])),
            )
        else:
            logger.warning(
                "Persistência no banco não concluída: %s",
                resumo.get("erro", "motivo desconhecido"),
            )
        # Anexa o resumo ao resultado para eventual exibição na interface.
        if isinstance(extraction_result.data, dict):
            extraction_result.data["_persistencia_banco"] = resumo
    except ImportError as exc:
        logger.error(
            "Dependências de banco de dados ausentes (instale psycopg2-binary): %s", exc
        )
    except Exception as exc:  # noqa: BLE001 - falha de banco não deve quebrar o app
        logger.error("Erro inesperado ao persistir dados no banco: %s", exc, exc_info=True)

class ProcessingService:
    """Orquestra o ciclo de vida completo do processamento de um documento PDF."""

    @staticmethod
    def process_document(
        file_obj: BinaryIO | bytes | io.BytesIO,
        filename: str,
        progress_callback: Callable[[str, float], None] | None = None,
        cpf_usuario: str | None = None
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

            # 3.1. Persiste automaticamente os dados extraídos no PostgreSQL
            update_progress("Salvando dados no banco de dados...", 0.90)
            _persistir_no_banco(extraction_result, cpf_usuario=cpf_usuario)

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
