"""Modelo de dados para o relatório de verificação de autenticidade de PDFs."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuthenticityReport:
    """Resultado da verificação de assinatura e código de autenticidade do documento.

    Atributos:
        valido: True quando o documento possui assinatura (digital ou eletrônica
            textual) E códigos de autenticidade em formato válido.
        possui_assinatura_digital: True quando há campo de assinatura digital
            embutido no PDF (padrão PAdES/PKCS#7) ou estrutura /ByteRange.
        assinatura_eletronica: dados da assinatura eletrônica textual
            (padrão SEI: "Documento assinado eletronicamente por ..."), se houver.
        codigo_verificador: código verificador extraído do documento (ex.: SEI).
        codigo_crc: código CRC extraído do documento (ex.: SEI).
        crc_conferido: True quando o CRC confere com o conteúdo do texto
            (verificação best-effort; o CRC oficial do SEI é calculado sobre o
            conteúdo interno do sistema).
        url_conferencia: URL oficial para conferência online da autenticidade.
        detalhes: mensagens humanas descrevendo cada verificação realizada.
    """
    valido: bool = False
    possui_assinatura_digital: bool = False
    assinatura_eletronica: dict[str, Any] | None = None
    codigo_verificador: str | None = None
    codigo_crc: str | None = None
    crc_conferido: bool = False
    url_conferencia: str | None = None
    detalhes: list[str] = field(default_factory=list)

    @property
    def possui_assinatura(self) -> bool:
        """True quando qualquer forma de assinatura foi identificada."""
        return self.possui_assinatura_digital or bool(self.assinatura_eletronica)

    @property
    def possui_codigos(self) -> bool:
        """True quando ambos os códigos de autenticidade foram identificados."""
        return bool(self.codigo_verificador and self.codigo_crc)

    def to_dict(self) -> dict[str, Any]:
        """Representação serializável (JSON) do relatório."""
        return {
            "valido": self.valido,
            "possui_assinatura_digital": self.possui_assinatura_digital,
            "assinatura_eletronica": self.assinatura_eletronica,
            "codigo_verificador": self.codigo_verificador,
            "codigo_crc": self.codigo_crc,
            "crc_conferido": self.crc_conferido,
            "url_conferencia": self.url_conferencia,
            "detalhes": list(self.detalhes),
        }
