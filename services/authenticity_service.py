"""Serviço de verificação de autenticidade de documentos PDF.

Verifica a validade do documento por meio de:
  1. **Assinatura** — campo de assinatura digital embutido no PDF
     (PAdES/PKCS#7, estrutura ``/ByteRange``) ou assinatura eletrônica textual
     no padrão SEI ("Documento assinado eletronicamente por ..., conforme
     art. 1º, § 2º, III, 'b', da Lei 11.419/2006").
  2. **Código de autenticidade** — código verificador e código CRC presentes
     no rodapé do documento (padrão SEI da Justiça Eleitoral), com validação
     de formato e conferência best-effort do CRC sobre o texto extraído.

Somente documentos considerados válidos seguem para o cálculo dos dias ganhos.
"""
import io
import re
import zlib
import logging

from pypdf import PdfReader

from models.authenticity import AuthenticityReport

logger = logging.getLogger(__name__)

# Código verificador SEI: rótulo seguido de 5 a 12 dígitos
RE_CODIGO_VERIFICADOR = re.compile(
    r"c[oó]digo\s+verificador\s*[:\-]?\s*(\d{5,12})", re.IGNORECASE
)

# Código CRC SEI: 8 caracteres hexadecimais
RE_CODIGO_CRC = re.compile(r"c[oó]digo\s*CRC\s*[:\-]?\s*([0-9A-Fa-f]{8})", re.IGNORECASE)

# Assinatura eletrônica textual padrão SEI
RE_ASSINATURA = re.compile(
    r"assinad[oa]\s+eletronicamente\s+por\s+"
    r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç\s\.]{2,80}?)\s*,\s*"
    r"([^,\n]{3,80}?)\s*,\s*em\s+(\d{2}/\d{2}/\d{4})"
    r"(?:\s*,\s*[àa]s\s+([\d:]{4,5}))?"
    r"(?:\s*,\s*conforme\s+(.+?Lei\s+11\.?419\s*/?\s*2006))?",
    re.IGNORECASE,
)

# URL oficial de conferência externa do SEI (pode conter quebras no meio)
RE_URL_CONFERENCIA = re.compile(
    r"(https?://\S*controlador_externo\S*(?:\s+\S+=\S+)*)", re.IGNORECASE
)

# Fundamento legal da assinatura eletrônica no serviço público
RE_LEI_11419 = re.compile(r"Lei\s+11\.?419\s*/?\s*2006", re.IGNORECASE)


def _normalizar(texto: str) -> str:
    """Colapsa quebras de linha e espaços múltiplos em espaços simples."""
    return re.sub(r"\s+", " ", texto or "").strip()


def extrair_assinatura_textual(texto: str) -> dict | None:
    """Extrai a assinatura eletrônica textual (padrão SEI) do documento.

    Args:
        texto: texto integral do PDF (já extraído).

    Returns:
        dict | None: {"signatario", "cargo", "data", "hora", "fundamento"}
        ou None quando nenhuma assinatura textual for identificada.
    """
    norm = _normalizar(texto)
    match = RE_ASSINATURA.search(norm)
    if not match:
        return None

    fundamento = _normalizar(match.group(5)) if match.group(5) else None
    assinatura = {
        "signatario": _normalizar(match.group(1)).strip(" ,."),
        "cargo": _normalizar(match.group(2)).strip(" ,."),
        "data": match.group(3),
        "hora": match.group(4) or "",
        "fundamento": fundamento,
    }

    # Reforça a detecção com a citação da Lei 11.419/2006, quando presente
    if not assinatura["fundamento"] and RE_LEI_11419.search(norm):
        assinatura["fundamento"] = "art. 1º, § 2º, III, 'b', da Lei 11.419/2006"

    return assinatura


def extrair_codigos_autenticidade(texto: str) -> dict:
    """Extrai os códigos de autenticidade (verificador e CRC) do documento.

    Args:
        texto: texto integral do PDF (já extraído).

    Returns:
        dict: {"codigo_verificador", "codigo_crc", "url_conferencia"} —
        valores None quando não identificados.
    """
    norm = _normalizar(texto)

    verificador = RE_CODIGO_VERIFICADOR.search(norm)
    crc = RE_CODIGO_CRC.search(norm)
    url = RE_URL_CONFERENCIA.search(norm)

    url_conferencia = re.sub(r"\s+", "", url.group(1)) if url else None

    return {
        "codigo_verificador": verificador.group(1) if verificador else None,
        "codigo_crc": crc.group(1).upper() if crc else None,
        "url_conferencia": url_conferencia,
    }


def conferir_crc(texto: str, codigo_crc: str) -> bool:
    """Conferência best-effort do CRC sobre o texto extraído do PDF.

    O CRC oficial do SEI é calculado sobre o conteúdo interno armazenado no
    sistema; portanto, a conferência local pode não coincidir mesmo para
    documentos autênticos. A validação principal permanece sendo o formato
    dos códigos e a presença da assinatura.

    Args:
        texto: texto integral do PDF.
        codigo_crc: código CRC hexadecimal (8 caracteres).

    Returns:
        bool: True se alguma normalização do texto produzir o CRC informado.
    """
    if not codigo_crc:
        return False
    try:
        alvo = int(codigo_crc, 16)
    except ValueError:
        return False

    variantes = {
        texto,
        re.sub(r"\s", "", texto or ""),
        _normalizar(texto),
    }
    for variante in variantes:
        for encoding in ("utf-8", "latin-1"):
            try:
                if zlib.crc32(variante.encode(encoding)) & 0xFFFFFFFF == alvo:
                    return True
            except Exception:  # noqa: BLE001 - nunca deve interromper a verificação
                continue
    return False


def detectar_assinatura_digital(reader: PdfReader, raw_bytes: bytes | None = None) -> bool:
    """Detecta campo de assinatura digital embutido no PDF (PAdES/PKCS#7).

    Args:
        reader: PdfReader já aberto sobre o documento.
        raw_bytes: bytes originais do PDF (opcional), para heurística
            de estrutura ``/ByteRange`` usada em assinaturas digitais.

    Returns:
        bool: True se houver indício de assinatura digital embutida.
    """
    try:
        fields = reader.get_fields() or {}
    except Exception:  # noqa: BLE001
        fields = {}
    for obj in fields.values():
        try:
            if obj.get("/FT") == "/Sig" or obj.get("/Type") == "/Sig":
                return True
        except Exception:  # noqa: BLE001
            continue

    try:
        for page in reader.pages:
            annots = page.get("/Annots") or []
            for annot in annots:
                try:
                    obj = annot.get_object()
                    if obj.get("/Subtype") == "/Widget" and (
                        obj.get("/FT") == "/Sig" or obj.get("/Type") == "/Sig"
                    ):
                        return True
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        pass

    if raw_bytes and b"/ByteRange" in raw_bytes:
        return True

    return False


def _atualizar_validade(report: AuthenticityReport) -> None:
    """Recalcula o campo ``valido`` e registra as mensagens de detalhe."""
    report.detalhes = []

    if report.possui_assinatura_digital:
        report.detalhes.append("✅ Assinatura digital embutida identificada no PDF.")
    if report.assinatura_eletronica:
        sig = report.assinatura_eletronica
        report.detalhes.append(
            f"✅ Assinatura eletrônica identificada: {sig.get('signatario', '—')} "
            f"({sig.get('cargo', '—')}) em {sig.get('data', '—')}"
            + (f" às {sig['hora']}" if sig.get("hora") else "")
            + "."
        )
    if not report.possui_assinatura:
        report.detalhes.append(
            "❌ Nenhuma assinatura (digital ou eletrônica) foi identificada no documento."
        )

    if report.codigo_verificador:
        report.detalhes.append(f"✅ Código verificador identificado: {report.codigo_verificador}.")
    else:
        report.detalhes.append("❌ Código verificador de autenticidade não encontrado.")

    if report.codigo_crc:
        report.detalhes.append(f"✅ Código CRC identificado: {report.codigo_crc}.")
    else:
        report.detalhes.append("❌ Código CRC de autenticidade não encontrado.")

    if report.possui_codigos:
        if report.crc_conferido:
            report.detalhes.append("✅ CRC conferido com o conteúdo do documento.")
        else:
            report.detalhes.append(
                "ℹ️ CRC com formato válido. A conferência integral pode exigir "
                "consulta ao sistema emissor (SEI)."
            )

    report.valido = report.possui_assinatura and report.possui_codigos

    if report.valido:
        report.detalhes.append("✅ Documento considerado VÁLIDO para fins de comprovação.")
    else:
        report.detalhes.append(
            "❌ Documento INVÁLIDO: os dias correspondentes não serão contabilizados."
        )


def analisar_texto(texto: str) -> AuthenticityReport:
    """Analisa o texto do documento (assinatura textual + códigos).

    Args:
        texto: texto integral extraído do PDF.

    Returns:
        AuthenticityReport: relatório parcial (sem análise de assinatura digital).
    """
    report = AuthenticityReport()
    report.assinatura_eletronica = extrair_assinatura_textual(texto)

    codigos = extrair_codigos_autenticidade(texto)
    report.codigo_verificador = codigos["codigo_verificador"]
    report.codigo_crc = codigos["codigo_crc"]
    report.url_conferencia = codigos["url_conferencia"]

    if report.codigo_crc:
        report.crc_conferido = conferir_crc(texto, report.codigo_crc)

    _atualizar_validade(report)
    return report


def extrair_texto_pdf(file_bytes: bytes) -> str:
    """Extrai o texto integral de um PDF a partir dos seus bytes.

    Args:
        file_bytes: conteúdo binário do PDF.

    Returns:
        str: texto completo (páginas unidas por quebra de linha).
    """
    reader = PdfReader(io.BytesIO(file_bytes))
    paginas: list[str] = []
    for page in reader.pages:
        try:
            paginas.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            paginas.append("")
    return "\n".join(paginas)


def verify_pdf_authenticity(file_bytes: bytes, filename: str = "") -> AuthenticityReport:
    """Verifica a autenticidade completa de um PDF (assinatura + códigos).

    Args:
        file_bytes: conteúdo binário do PDF.
        filename: nome original do arquivo (apenas para logs).

    Returns:
        AuthenticityReport: relatório completo da verificação.
    """
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:  # noqa: BLE001
        logger.error("Falha ao abrir PDF %s para verificação de autenticidade: %s", filename, exc)
        return AuthenticityReport(
            valido=False,
            detalhes=[f"❌ Não foi possível ler o PDF: {exc}"],
        )

    try:
        texto_completo = extrair_texto_pdf(file_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.error("Falha ao extrair texto de %s: %s", filename, exc)
        texto_completo = ""

    report = analisar_texto(texto_completo)
    report.possui_assinatura_digital = detectar_assinatura_digital(reader, file_bytes)
    _atualizar_validade(report)

    logger.info(
        "Verificação de autenticidade de %s concluída: valido=%s (assinatura=%s, códigos=%s).",
        filename, report.valido, report.possui_assinatura, report.possui_codigos,
    )
    return report
