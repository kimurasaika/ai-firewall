"""Text PII redaction worker using Microsoft Presidio + PyThaiNLP."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from opentelemetry import trace
from presidio_analyzer import AnalyzerEngine, EntityRecognizer, Pattern, PatternRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

try:
    from pythainlp.tag import pos_tag
    from pythainlp.tokenize import word_tokenize
    _PYTHAINLP_AVAILABLE = True
except ImportError:
    _PYTHAINLP_AVAILABLE = False

from src.observability.metrics import redactions_total, request_latency, worker_errors_total
from src.observability.tracer import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer("text_worker")

# ── Token counter per entity type ───────────────────────────────────────────────
_PREFIXES: dict[str, str] = {
    "PERSON": "P",
    "PHONE_NUMBER": "PH",
    "EMAIL_ADDRESS": "EM",
    "TH_NATIONAL_ID": "ID",
    "LOCATION": "AD",
    "ORGANIZATION": "ORG",
}

_FORMAT: dict[str, str] = {
    "P": "<<P{:03d}>>",
    "PH": "<<PH{:03d}>>",
    "EM": "<<EM{:03d}>>",
    "ID": "<<ID{:03d}>>",
    "AD": "<<AD{:03d}>>",
    "ORG": "<<ORG{:03d}>>",
}


class ThaiNERRecognizer(EntityRecognizer):
    """Custom Presidio recognizer backed by PyThaiNLP NER."""

    SUPPORTED_ENTITIES = ["PERSON", "LOCATION", "ORGANIZATION"]
    SUPPORTED_LANGUAGES = ["th"]

    def __init__(self) -> None:
        super().__init__(
            supported_entities=self.SUPPORTED_ENTITIES,
            supported_language="th",
            name="ThaiNERRecognizer",
        )

    def load(self) -> None:
        pass

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: NlpArtifacts | None = None,
    ) -> list[RecognizerResult]:
        if not _PYTHAINLP_AVAILABLE:
            return []

        results: list[RecognizerResult] = []
        tokens = word_tokenize(text, engine="newmm")
        tags = pos_tag(tokens, engine="perceptron", corpus="orchid_ud")

        pos = 0
        for token, tag in tags:
            start = text.find(token, pos)
            if start == -1:
                pos += len(token)
                continue
            end = start + len(token)

            entity = None
            if tag in ("PROPN",) and any(
                text[max(0, start - 10) : start].strip().endswith(w)
                for w in ["คุณ", "นาย", "นาง", "นางสาว", "ดร."]
            ):
                entity = "PERSON"
            elif tag == "PROPN":
                entity = "ORGANIZATION"

            if entity and entity in entities:
                results.append(
                    RecognizerResult(
                        entity_type=entity,
                        start=start,
                        end=end,
                        score=0.7,
                    )
                )
            pos = end

        return results


def _build_analyzer() -> AnalyzerEngine:
    """
    Build Presidio AnalyzerEngine supporting both English and Thai.
    Thai regex patterns (phone, ID) don't need a Thai spaCy model — we reuse
    the English model for tokenization and let our custom recognizers do the work.
    """
    import spacy
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    # Detect whichever English spaCy model is installed
    model_name = next(
        (m for m in ("en_core_web_sm", "en_core_web_md", "en_core_web_lg")
         if spacy.util.is_package(m)),
        None,
    )
    if model_name is None:
        logger.warning("No spaCy English model found. Run: python -m spacy download en_core_web_sm")
        return AnalyzerEngine()

    try:
        configuration = {
            "nlp_engine_name": "spacy",
            "models": [
                {"lang_code": "en", "model_name": model_name},
                # Thai NLP uses the English model; regex recognizers don't need NLP
                {"lang_code": "th", "model_name": model_name},
            ],
        }
        provider = NlpEngineProvider(nlp_configuration=configuration)
        nlp_engine = provider.create_engine()
        return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en", "th"])
    except Exception as exc:
        logger.warning("Could not configure multilingual Presidio (%s) — falling back to English only", exc)
        return AnalyzerEngine()


class TextWorker:
    """Redacts PII in plain text and returns token → original mapping."""

    def __init__(self) -> None:
        self._analyzer = _build_analyzer()
        self._register_thai_patterns()
        if _PYTHAINLP_AVAILABLE:
            self._analyzer.registry.add_recognizer(ThaiNERRecognizer())
        self._anonymizer = AnonymizerEngine()
        self._counters: dict[str, int] = {}

    def _register_thai_patterns(self) -> None:
        """Register regex-based recognizers for Thai entities on both en and th."""
        for lang in ("en", "th"):
            # Thai national ID: 13 digits starting with 1-9
            self._analyzer.registry.add_recognizer(PatternRecognizer(
                supported_entity="TH_NATIONAL_ID",
                supported_language=lang,
                patterns=[
                    Pattern("Thai ID (plain)", r"\b[1-9]\d{12}\b", 0.95),
                    Pattern("Thai ID (formatted)", r"\b[1-9]-\d{4}-\d{5}-\d{2}-\d\b", 0.99),
                ],
                context=["บัตรประชาชน", "เลขที่บัตร", "national id", "citizen id", "id card"],
            ))
        self._supported_languages: set[str] = set(
            getattr(self._analyzer, "supported_languages", ["en"])
        )
        logger.info("TextWorker initialized; pythainlp=%s supported_langs=%s",
                    _PYTHAINLP_AVAILABLE, self._supported_languages)

    def _next_token(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return _FORMAT[prefix].format(self._counters[prefix])

    def reset_counters(self) -> None:
        """Reset per-session counters — call at the start of each session."""
        self._counters.clear()

    def redact(self, text: str, language: str = "th") -> tuple[str, dict[str, str]]:
        """
        Redact PII in text.
        Returns (redacted_text, mapping) where mapping = {token: original_value}.
        """
        with tracer.start_as_current_span("text_worker.redact") as span:
            t0 = time.perf_counter()
            span.set_attribute("text.length", len(text))

            lang = language if language in self._supported_languages else "en"
            results = self._analyzer.analyze(
                text=text,
                language=lang,
                entities=list(_PREFIXES.keys()),
            )

            mapping: dict[str, str] = {}
            operators: dict[str, OperatorConfig] = {}

            # Deduplicate by value so the same name always gets the same token
            value_to_token: dict[str, str] = {}

            for r in results:
                original = text[r.start : r.end]
                if original in value_to_token:
                    token = value_to_token[original]
                else:
                    prefix = _PREFIXES.get(r.entity_type, "UNK")
                    token = self._next_token(prefix)
                    value_to_token[original] = token
                    mapping[token] = original

                operators[r.entity_type] = OperatorConfig(
                    "replace", {"new_value": value_to_token[original]}
                )
                redactions_total.labels(entity_type=r.entity_type).inc()

            anonymized = self._anonymizer.anonymize(
                text=text,
                analyzer_results=results,
                operators=operators,
            )
            redacted_text: str = anonymized.text

            latency = time.perf_counter() - t0
            request_latency.labels(service="text_worker", content_type="text").observe(latency)
            span.set_attribute("entities.found", len(results))
            return redacted_text, mapping

    def redact_safe(self, text: str, language: str = "th") -> tuple[str, dict[str, str]]:
        """Wrapper with error handling — returns original text on failure."""
        try:
            return self.redact(text, language)
        except Exception as exc:
            worker_errors_total.labels(worker="text", error_type=type(exc).__name__).inc()
            logger.error("TextWorker.redact failed: %s", exc, exc_info=True)
            return text, {}
