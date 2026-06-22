"""SSL inspection helpers — loads CA cert/key for mitmproxy MITM."""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def get_ca_cert_path() -> str:
    path = os.environ.get("MITMPROXY_CA_CERT", "/app/certs/ca.crt")
    if not Path(path).exists():
        raise FileNotFoundError(f"CA cert not found: {path}")
    return path


def get_ca_key_path() -> str:
    path = os.environ.get("MITMPROXY_CA_KEY", "/app/certs/ca.key")
    if not Path(path).exists():
        raise FileNotFoundError(f"CA key not found: {path}")
    return path


def load_llm_domains() -> set[str]:
    """Load LLM domains from config/domains/llm_whitelist.yaml."""
    import yaml
    config_path = Path("config/domains/llm_whitelist.yaml")
    if not config_path.exists():
        logger.warning("LLM whitelist not found at %s", config_path)
        return set()
    with config_path.open() as f:
        data = yaml.safe_load(f)
    domains = {
        entry["domain"]
        for entry in data.get("domains", [])
        if entry.get("active", False)
    }
    logger.info("Loaded %d LLM domains from whitelist", len(domains))
    return domains
