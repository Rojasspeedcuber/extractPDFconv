"""Configurações centralizadas da aplicação."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env se existir
load_dotenv()

class Settings:
    """Configurações da aplicação."""
    APP_NAME: str = "PDF Extractor"
    APP_VERSION: str = "1.0.0"
    
    # Porta padrão
    PORT: int = int(os.getenv("PORT", "3000"))
    
    # Limite máximo de arquivo em MB (padrão: 20MB)
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "20"))
    
    # Flag para ativar modo mock na extração
    USE_MOCK_EXTRACTION: bool = os.getenv("USE_MOCK_EXTRACTION", "false").lower() in ("true", "1", "yes")
    
    # Diretório temporário de armazenamento
    STORAGE_DIR: Path = Path(os.getenv("STORAGE_DIR", "storage/temp"))
    
    # Variáveis futuras para extensões (OCR / IA / Nuvem)
    GOOGLE_API_KEY: str | None = os.getenv("GOOGLE_API_KEY")

settings = Settings()

# Garante que o diretório de armazenamento exista
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
