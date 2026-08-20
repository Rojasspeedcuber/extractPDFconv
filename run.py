"""Script de inicialização adaptativo para execução do Streamlit."""
import sys
import os
import subprocess

def main():
    port = os.getenv("PORT", "3000")
    for arg in sys.argv[1:]:
        if arg.startswith("--port="):
            port = arg.split("=")[1]

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        f"--server.port={port}",
        "--server.address=0.0.0.0",
        "--server.headless=true",
        "--server.enableCORS=false",
        "--server.enableXsrfProtection=false",
        "--browser.gatherUsageStats=false"
    ]
    sys.exit(subprocess.call(cmd))

if __name__ == "__main__":
    main()
