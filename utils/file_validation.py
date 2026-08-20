"""Utilitário de validação de arquivos PDF."""
import io
import logging
from typing import Tuple, BinaryIO
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from config.settings import settings

logger = logging.getLogger(__name__)

def format_file_size(size_in_bytes: int) -> str:
    """Formata o tamanho em bytes para representação legível (KB, MB, GB)."""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_in_bytes / (1024 * 1024 * 1024):.2f} GB"

def validate_pdf(file_obj: BinaryIO | bytes | io.BytesIO, filename: str | None = None, max_size_mb: int | None = None) -> Tuple[bool, str, int]:
    """
    Valida se um arquivo recebido é um PDF legítimo, não vazio e dentro do tamanho permitido.
    
    Retorna:
        Tuple[bool, str, int]: (é_valido, mensagem_de_status_ou_erro, tamanho_em_bytes)
    """
    max_mb = max_size_mb if max_size_mb is not None else settings.MAX_FILE_SIZE_MB
    max_bytes = max_mb * 1024 * 1024
    
    # 1. Validação do nome e extensão
    if filename:
        if not filename.lower().endswith(".pdf"):
            logger.warning(f"Validação falhou: extensão inválida para o arquivo {filename}")
            return False, "Este arquivo não é um PDF.", 0
            
    # 2. Obtenção do stream de bytes
    if isinstance(file_obj, bytes):
        stream = io.BytesIO(file_obj)
        size_bytes = len(file_obj)
    elif hasattr(file_obj, "getbuffer"):
        buffer = file_obj.getbuffer()
        size_bytes = buffer.nbytes
        stream = io.BytesIO(buffer)
    elif hasattr(file_obj, "read"):
        current_pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
        content = file_obj.read()
        if hasattr(file_obj, "seek"):
            file_obj.seek(current_pos)
        size_bytes = len(content)
        stream = io.BytesIO(content)
    else:
        logger.error("Tipo de objeto de arquivo inválido para validação")
        return False, "Não foi possível ler o arquivo.", 0

    # 3. Validação de arquivo vazio
    if size_bytes == 0:
        logger.warning("Validação falhou: arquivo vazio")
        return False, "O arquivo está vazio.", 0

    # 4. Validação do tamanho
    if size_bytes > max_bytes:
        logger.warning(f"Validação falhou: tamanho {size_bytes} excede o limite de {max_bytes} ({max_mb} MB)")
        return False, f"O arquivo excede o limite de {max_mb} MB.", size_bytes

    # 5. Validação da assinatura mágica de PDF (%PDF)
    stream.seek(0)
    header = stream.read(5)
    stream.seek(0)
    
    if not header.startswith(b"%PDF-") and not header.startswith(b"%PDF"):
        logger.warning(f"Validação falhou: assinatura do cabeçalho inválida: {header!r}")
        return False, "Este arquivo não é um PDF.", size_bytes

    # 6. Validação de legibilidade com pypdf
    try:
        reader = PdfReader(stream)
        # Tenta ler o número de páginas para verificar integridade
        _ = len(reader.pages)
    except (PdfReadError, Exception) as exc:
        logger.error(f"Erro ao ler estrutura do PDF: {exc}")
        return False, "Não foi possível ler o PDF.", size_bytes

    logger.info(f"PDF validado com sucesso ({size_bytes} bytes).")
    return True, "PDF validado com sucesso.", size_bytes
