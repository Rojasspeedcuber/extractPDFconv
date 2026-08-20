"""Serviço de extração de informações de documentos PDF com arquitetura extensível."""
import re
import time
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from config.settings import settings
from mocks.extraction_mock import get_mock_extraction_result
from models.extraction import ExtractionResult
from services.pdf_service import PDFService

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Classe base abstrata para todos os extratores de documentos."""

    @abstractmethod
    def can_handle(self, text: str, metadata: dict[str, Any]) -> bool:
        """Determina se este extrator é apropriado para o conteúdo do documento."""
        pass

    @abstractmethod
    def extract(self, text: str, pages_text: list[str], metadata: dict[str, Any]) -> dict[str, Any]:
        """Executa a extração estruturada dos dados."""
        pass


def _clean_text(val: str | None) -> str:
    """Remove quebras de linha excessivas e normaliza múltiplos espaços em branco."""
    if not val:
        return ""
    # Substitui quebras de linha e múltiplos espaços por um espaço simples
    cleaned = re.sub(r"[\r\n\t]+", " ", str(val))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_convocado_name(text: str) -> str:
    """
    Extrai com precisão o nome COMPLETO do convocado em documentos eleitorais,
    suportando quebras de linhas no PDF, preposições (da, de, dos), acentuação e diferentes variações.
    """
    # 1. Tenta padrão com 'convoca o(a) Sr(a)...' ou variações com terminadores semânticos claros
    patterns = [
        # Padrão A: 'convoca o(a) Sr(a). NOME COMPLETO para atuar/trabalhar/exercer...'
        r"convoca(?:ndo)?\s+(?:o\(a\)|o|a)?\s*(?:Sr\(a\)\.?|Senhor\(a\)\.?|Eleitor\(a\)\.?|Cidadão\(ã\)\.?|Sr\.|Sra\.)?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇÀÈÌÒÙÄËÏÖÜa-záéíóúâêôãõçàèìòùäëïöü\s\.\-']+?)(?=\s*,?\s*(?:para\s+atuar|para\s+trabalhar|para\s+exercer|para\s+prestar|para\s+compor|para\s+integrar|para\s+a\s+função|nas\s+ELEIÇÕES|como\s+[A-Z]|inscrição|inscrit[oa]|título|portador|cpf|rg|\bSEI\b|\bTRE\b|\bEleitoral\b|\.\s+Para|\.\s+O\(a\)|,\s*no\s+Local))",
        
        # Padrão B: 'Sr(a). NOME COMPLETO, ... para atuar...'
        r"(?:Sr\(a\)\.?|Senhor\(a\)\.?|Eleitor\(a\)\.?)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇÀÈÌÒÙÄËÏÖÜ][A-ZÁÉÍÓÚÂÊÔÃÕÇÀÈÌÒÙÄËÏÖÜa-záéíóúâêôãõçàèìòùäëïöü\s\.\-']{3,100}?)(?=\s*,?\s*(?:para\s+atuar|para\s+trabalhar|para\s+exercer|nas\s+ELEIÇÕES|como\s+|inscrição|inscrit|título|portador|\.|\n\n))",
        
        # Padrão C: 'Nome / Convocado(a): NOME COMPLETO'
        r"(?:Nome\s+(?:do\s+convocado|do\s+eleitor)?|Convocado\(a\)|Eleitor\(a\))\s*:\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇÀÈÌÒÙÄËÏÖÜa-záéíóúâêôãõçàèìòùäëïöü\s\.\-']+?)(?=\n|$|,|Título|Inscrição|Zona|Local)",
        
        # Padrão D: Fallback genérico capturando texto em maiúsculas após convocação
        r"convoca\s+o\(a\)\s+Sr\(a\)\.?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{4,100})"
    ]

    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            candidate = _clean_text(match.group(1))
            # Remove pontuações residuais no final
            candidate = re.sub(r"[,\.\-:]+$", "", candidate).strip()
            # Ignora se for muito curto ou palavras-chave de cabeçalho
            if len(candidate) >= 3 and not candidate.upper().startswith("TRIBUNAL"):
                return candidate

    return "Nome não detectado"


class ElectionSummonsExtractor(BaseExtractor):
    """Extrator especializado para Cartas Convocatórias da Justiça Eleitoral."""

    def can_handle(self, text: str, metadata: dict[str, Any]) -> bool:
        normalized = text.upper()
        return ("CARTA CONVOCATÓRIA" in normalized or "CONVOCAÇÃO ELEITORAL" in normalized or 
                ("TRIBUNAL REGIONAL ELEITORAL" in normalized and "CONVOCA" in normalized))

    def extract(self, text: str, pages_text: list[str], metadata: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        
        # 1. Órgão emissor
        orgao_match = re.search(r"(TRIBUNAL REGIONAL ELEITORAL[^\n]+)", text, re.IGNORECASE)
        data["orgao_emissor"] = _clean_text(orgao_match.group(1)) if orgao_match else "Tribunal Regional Eleitoral"
        
        # 2. Zona Eleitoral
        zona_match = re.search(r"(\d+ª\s+Zona(?:\s+Eleitoral)?)", text, re.IGNORECASE)
        data["zona_eleitoral"] = _clean_text(zona_match.group(1)) if zona_match else "Não identificada"

        # 3. Nome Completo do Convocado
        data["nome_convocado"] = _extract_convocado_name(text)

        # 4. Eleição / Pleito
        eleicoes_match = re.search(r"(ELEIÇÕES\s+[A-Z0-9\s]+?\d{4})", text, re.IGNORECASE)
        data["eleicao"] = _clean_text(eleicoes_match.group(1)) if eleicoes_match else "Eleições Gerais"

        # 5. Função / Cargo
        funcao_match = re.search(
            r"como\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ\(\)\/\s]{3,60}?)(?:,\s*no\s+Local|\s+no\s+Local|\.\s*no\s+Local)",
            text,
            re.IGNORECASE
        )
        data["funcao_cargo"] = _clean_text(funcao_match.group(1)) if funcao_match else "Mesário / Administrador de Prédio"

        # 6. Local de Votação
        local_match = re.search(
            r"no\s+Local\s+(?:de\s+Votação)?\s*[:\s]\s*([^,\n]+(?:\s+[^,\n]+)*?)(?:,\s*situad[oa]|,\s*localizad[oa]|,\s*no\s+endereço|,\s*endereço|\.\s*onde|\s*,\s*onde|\.|$)",
            text,
            re.IGNORECASE
        )
        if local_match:
            data["local_votacao"] = _clean_text(local_match.group(1))
        else:
            alt_local = re.search(r"no\s+Local\s+de\s+Votação\s+([^,]+?)(?:,\s*situado|,\s*no\s+endereço|\.)", text, re.IGNORECASE)
            data["local_votacao"] = _clean_text(alt_local.group(1)) if alt_local else "Não especificado"

        # 7. Endereço do Local de Votação
        endereco_match = re.search(
            r"(?:situad[oa]\s+na?|localizad[oa]\s+na?|no\s+endereço\s+|endereço\s*[:\s]\s*)([^,\n]+(?:,\s*[^,\n]+)*?)(?=\s*,\s*onde\s+deverá|\s*\n\s*comparecer|\.\s*onde|\.\s*Para|\.|$)",
            text,
            re.IGNORECASE
        )
        data["endereco_local_votacao"] = _clean_text(endereco_match.group(1)) if endereco_match else "Não especificado"

        # 8. Extração detalhada de Datas
        datas_detalhadas: dict[str, Any] = {}

        # 8.1 Primeiro Turno
        primeiro_turno_match = re.search(
            r"nos\s+dias\s+([\d\/\s,e]+?)(?:\(domingo[^\)]*primeiro\s+turno\)[^,\n]*e\s*(\d{2}/\d{2}/\d{4}))",
            text,
            re.IGNORECASE
        )
        if primeiro_turno_match:
            dias_previos = primeiro_turno_match.group(1).strip()
            dia_pos = primeiro_turno_match.group(2).strip() if primeiro_turno_match.group(2) else ""
            datas_detalhadas["primeiro_turno"] = {
                "descricao": "Dias do 1º Turno (preparação, votação e apuração)",
                "datas": [d.strip() for d in re.findall(r"\d{2}/\d{2}/\d{4}", dias_previos + " " + dia_pos)]
            }
        else:
            # Busca geral por datas do 1º turno
            datas_1t = re.findall(r"(\d{2}/\d{2}/\d{4})", text)
            if datas_1t:
                datas_detalhadas["primeiro_turno"] = {"datas": datas_1t[:4]}

        # 8.2 Segundo Turno (se houver)
        segundo_turno_match = re.search(
            r"segundo\s+turno[,\s]+([\d\/\s,e]+?)(?:\(domingo[^\)]*segundo\s+turno\)[^,\n]*e\s*(\d{2}/\d{2}/\d{4}))",
            text,
            re.IGNORECASE
        )
        if segundo_turno_match:
            dias_previos_2t = segundo_turno_match.group(1).strip()
            dia_pos_2t = segundo_turno_match.group(2).strip() if segundo_turno_match.group(2) else ""
            datas_detalhadas["segundo_turno"] = {
                "descricao": "Dias do 2º Turno (se houver)",
                "datas": [d.strip() for d in re.findall(r"\d{2}/\d{2}/\d{4}", dias_previos_2t + " " + dia_pos_2t)]
            }

        # 8.3 Treinamento
        treinamento_match = re.search(
            r"TREINAMENTO[\s\S]*?no\s+dia:?\s*(\d{2}/\d{2}/\d{4})(?:,\s*das\s*([\d\w\sàs]+?))?(?=\.|\n\s*\n|Fica|$)",
            text,
            re.IGNORECASE
        )
        if treinamento_match:
            local_treinamento = re.search(r"TREINAMENTO[\s\S]*?na\s+([^\n,]+)", text, re.IGNORECASE)
            datas_detalhadas["treinamento"] = {
                "data": treinamento_match.group(1),
                "horario": _clean_text(treinamento_match.group(2)) if treinamento_match.group(2) else "Horário a definir",
                "local": _clean_text(local_treinamento.group(1)) if local_treinamento else "Local indicado no documento"
            }

        # 8.4 Vistoria
        vistoria_match = re.search(r"VISTORIA[\s\S]*?no\s+dia\s+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
        if vistoria_match:
            datas_detalhadas["vistoria"] = {
                "data": vistoria_match.group(1),
                "descricao": "Vistoria no local de votação"
            }

        # 8.5 Transferência Temporária
        transf_match = re.search(
            r"transferência\s+temporária[\s\S]*?no\s+período\s+de\s+(\d{2}/\d{2}/\d{4})\s+a\s+(\d{2}/\d{2}/\d{4})",
            text,
            re.IGNORECASE
        )
        if transf_match:
            datas_detalhadas["transferencia_temporaria"] = {
                "inicio": transf_match.group(1),
                "fim": transf_match.group(2),
                "periodo": f"{transf_match.group(1)} a {transf_match.group(2)}"
            }

        # 8.6 Emissão e Assinatura Eletrônica
        emissao_match = re.search(r"([A-Za-z]+,\s+\d{1,2}\s+de\s+[a-zç]+\s+de\s+\d{4})", text, re.IGNORECASE)
        if emissao_match:
            datas_detalhadas["data_emissao"] = _clean_text(emissao_match.group(1))

        assinatura_match = re.search(r"assinado\s+eletronicamente[\s\S]*?em\s+(\d{2}/\d{2}/\d{4})(?:,\s*às\s*([\d:]+))?", text, re.IGNORECASE)
        if assinatura_match:
            datas_detalhadas["assinatura_eletronica"] = {
                "data": assinatura_match.group(1),
                "hora": _clean_text(assinatura_match.group(2)) if assinatura_match.group(2) else ""
            }

        data["datas_identificadas"] = datas_detalhadas

        # 9. Lista consolidada de todas as datas únicas encontradas no documento
        todas_as_datas = sorted(list(set(re.findall(r"\b\d{2}/\d{2}/\d{4}\b", text))))
        data["todas_as_datas_encontradas"] = todas_as_datas

        # 10. Código de autenticidade / Processo SEI
        sei_match = re.search(r"SEI\s+([\d\.\-]+/\s*pg\.\s*\d+|[\d\.\-]+)", text, re.IGNORECASE)
        if sei_match:
            data["numero_sei"] = _clean_text(sei_match.group(1))

        carta_num = re.search(r"Carta\s+(\d+)", text, re.IGNORECASE)
        if carta_num:
            data["numero_carta"] = _clean_text(carta_num.group(1))

        return data


class GenericDocumentExtractor(BaseExtractor):
    """Extrator genérico baseado em padrões para qualquer documento PDF."""

    def can_handle(self, text: str, metadata: dict[str, Any]) -> bool:
        return True  # Fallback padrão

    def extract(self, text: str, pages_text: list[str], metadata: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = {}

        # 1. Título ou primeiras linhas significativas
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        data["primeiras_linhas"] = lines[:5] if lines else []

        # 2. Todas as datas identificadas no formato DD/MM/AAAA
        datas_encontradas = sorted(list(set(re.findall(r"\b\d{2}/\d{2}/\d{4}\b", text))))
        data["datas_identificadas"] = datas_encontradas

        # 3. Padrões de datas por extenso (ex: 25 de junho de 2026)
        datas_extenso = re.findall(r"\b\d{1,2}\s+de\s+[a-zçA-ZÇ]+\s+de\s+\d{4}\b", text)
        if datas_extenso:
            data["datas_por_extenso"] = list(set(datas_extenso))

        # 4. Endereços de e-mail
        emails = list(set(re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)))
        if emails:
            data["emails_detectados"] = emails

        # 5. Padrões de números de processos ou CPF/CNPJ
        processos = list(set(re.findall(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b", text)))
        if processos:
            data["processos_judiciais"] = processos

        cpfs = list(set(re.findall(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", text)))
        if cpfs:
            data["cpfs_detectados"] = cpfs

        # 6. Estatísticas textuais
        data["estatisticas"] = {
            "total_paginas": len(pages_text),
            "total_palavras": len(text.split()),
            "total_caracteres": len(text),
            "possui_datas": len(datas_encontradas) > 0
        }

        return data


class ExtractionService:
    """Gerenciador de estratégias de extração."""

    def __init__(self):
        # Lista de extratores registrados em ordem de prioridade
        self.extractors: list[BaseExtractor] = [
            ElectionSummonsExtractor(),
            GenericDocumentExtractor()
        ]

    def register_extractor(self, extractor: BaseExtractor, priority: int = 0) -> None:
        """Permite plugar dinamicamente novos extratores (OCR, IA, etc)."""
        self.extractors.insert(priority, extractor)

    def extract(self, pdf_path: str | Path) -> ExtractionResult:
        """Executa o pipeline de extração no PDF informado."""
        start_time = time.time()
        
        # Verifica se está configurado para modo Mock
        if settings.USE_MOCK_EXTRACTION:
            logger.info("Executando extração em modo MOCK.")
            result = get_mock_extraction_result()
            result.processing_time_seconds = round(time.time() - start_time, 3)
            return result

        try:
            full_text, pages_text = PDFService.extract_full_text(pdf_path)
            
            if not full_text.strip():
                logger.warning(f"PDF {pdf_path} não contém texto extraível diretamente.")
                return ExtractionResult(
                    status="completed",
                    document_type="Documento Escaneado / Sem Camada de Texto",
                    summary="O arquivo não possui camada de texto digitalizada ou está em branco. (Poderá requerer módulo de OCR)",
                    extracted_fields_count=0,
                    data={"aviso": "Nenhum texto pôde ser extraído diretamente da camada vetorial do PDF."},
                    processing_time_seconds=round(time.time() - start_time, 3)
                )

            # Seleciona o extrator adequado
            selected_extractor: BaseExtractor = self.extractors[-1]  # fallback
            for extractor in self.extractors:
                if extractor.can_handle(full_text, {}):
                    selected_extractor = extractor
                    break

            doc_type = "Carta Convocatória Eleitoral" if isinstance(selected_extractor, ElectionSummonsExtractor) else "Documento Genérico"
            extracted_data = selected_extractor.extract(full_text, pages_text, {})
            
            elapsed = round(time.time() - start_time, 3)
            logger.info(f"Extração concluída com sucesso usando {selected_extractor.__class__.__name__} em {elapsed}s.")

            return ExtractionResult(
                status="completed",
                document_type=doc_type,
                summary=f"Extração concluída com sucesso. {len(extracted_data)} blocos de informações identificados.",
                extracted_fields_count=len(extracted_data),
                data=extracted_data,
                processing_time_seconds=elapsed
            )

        except Exception as exc:
            logger.error(f"Erro durante a extração de {pdf_path}: {exc}", exc_info=True)
            return ExtractionResult(
                status="error",
                error=f"Erro no processamento do documento: {str(exc)}",
                processing_time_seconds=round(time.time() - start_time, 3)
            )


# Instância global do serviço
_extraction_service = ExtractionService()

def extract_information(pdf_path: str | Path) -> ExtractionResult:
    """Função de entrada unificada para extração de informações."""
    return _extraction_service.extract(pdf_path)
