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

    # Diretório definitivo dos documentos comprobatórios enviados por upload
    DOCUMENTS_DIR: Path = Path(os.getenv("DOCUMENTS_DIR", "storage/documentos"))
    
    # Variáveis futuras para extensões (OCR / IA / Nuvem)
    GOOGLE_API_KEY: str | None = os.getenv("GOOGLE_API_KEY")

    # --- Integração com banco de dados PostgreSQL ---
    # URL de conexão do PostgreSQL (ex.: postgresql://user:senha@host:5432/banco)
    DATABASE_URL: str | None = os.getenv("DATABASE_URL")

    # Ativa a persistência automática dos dados extraídos no banco.
    # Por padrão fica habilitada quando existe uma DATABASE_URL configurada.
    PERSIST_TO_DB: bool = os.getenv(
        "PERSIST_TO_DB",
        "true" if os.getenv("DATABASE_URL") else "false",
    ).lower() in ("true", "1", "yes")

    # --- Keycloak (autenticação) ---
    # Quando KEYCLOAK_URL estiver vazio, o sistema usa o modo "CPF direto"
    # (desenvolvimento), aceitando qualquer CPF válido como login.
    KEYCLOAK_URL: str = os.getenv("KEYCLOAK_URL", "")
    KEYCLOAK_REALM: str = os.getenv("KEYCLOAK_REALM", "")
    KEYCLOAK_CLIENT_ID: str = os.getenv("KEYCLOAK_CLIENT_ID", "")

settings = Settings()

# Garante que os diretórios de armazenamento existam
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
