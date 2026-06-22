"""De-anonymizer — replaces tokens in LLM responses with original values.

Logic:
  1. Exact match → replace
  2. Fuzzy match via rapidfuzz (threshold=90) → replace
  3. No match → log WARNING + leave token as-is
  4. Caller must clear session mapping from Redis after this returns.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from rapidfuzz import fuzz, process

from src.observability.metrics import deanon_misses_total
from src.observability.tracer import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer("deanonymizer")

_TOKEN_PATTERN = re.compile(r"<<([A-Z]+\d{3})>>")
_FUZZY_THRESHOLD = 90


class Deanonymizer:
    """Replaces <<TOKENS>> in text with original values from the session mapping."""

    def deanonymize(
        self,
        text: str,
        mapping: dict[str, str],
    ) -> tuple[str, list[str]]:
        """
        Returns (restored_text, missed_tokens).
        missed_tokens: tokens found in text but not in mapping (even after fuzzy).
        """
        with tracer.start_as_current_span("deanonymizer.deanonymize"):
            if not mapping:
                return text, []

            tokens_in_text = _TOKEN_PATTERN.findall(text)
            misses: list[str] = []
            result = text

            for raw_token in set(tokens_in_text):
                formatted = f"<<{raw_token}>>"

                # 1. Exact match
                if formatted in mapping:
                    result = result.replace(formatted, mapping[formatted])
                    deanon_misses_total.labels(match_type="exact").inc()
                    continue

                # 2. Fuzzy match on keys
                keys = list(mapping.keys())
                match = process.extractOne(
                    formatted,
                    keys,
                    scorer=fuzz.ratio,
                    score_cutoff=_FUZZY_THRESHOLD,
                )
                if match:
                    matched_key, score, _ = match
                    logger.debug(
                        "Fuzzy match: token=%s → key=%s score=%d",
                        formatted, matched_key, score,
                    )
                    result = result.replace(formatted, mapping[matched_key])
                    deanon_misses_total.labels(match_type="fuzzy").inc()
                    continue

                # 3. Miss
                misses.append(formatted)
                deanon_misses_total.labels(match_type="miss").inc()
                logger.warning(
                    "Deanonymization miss: token=%s not found in mapping",
                    formatted,
                    extra={"token": formatted},
                )

            return result, misses
