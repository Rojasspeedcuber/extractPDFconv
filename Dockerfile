# Imagem oficial Python slim
FROM python:3.12-slim

# Evita que o Python gere arquivos .pyc e força saída stdout/stderr sem buffer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8501

# Define diretório de trabalho
WORKDIR /app

# Instala dependências do sistema necessárias para compilação leve se necessário
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código-fonte da aplicação
COPY . .

# Cria pasta de armazenamento temporário com permissões
RUN mkdir -p storage/temp

# Expõe a porta configurável
EXPOSE 8501

# Healthcheck nativo para EasyPanel / Docker
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:${PORT}/_stcore/health || exit 1

# Comando de inicialização compatível com EasyPanel, Hostinger e Cloud Run
ENTRYPOINT ["sh", "-c", "streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true --server.enableCORS=false --server.enableXsrfProtection=false"]
