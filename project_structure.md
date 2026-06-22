# Project Structure — AI Firewall / DLP

```
ai-firewall/
│
├── architecture.md
├── requirements.md
├── tech_stack.md
├── project_structure.md
├── runbook.md                        # Playbook ถ้า X พัง ทำ Y
│
├── .env.example                      # Template (dev)
├── .env                              # Dev secrets (ห้าม commit)
├── .env.staging                      # Staging secrets (ห้าม commit)
├── .gitignore
│
├── docker-compose.yml                # Dev
├── docker-compose.staging.yml        # Staging
├── docker-compose.production.yml     # Production
│
├── config/
│   ├── versions.yaml                 # [DevOps] single source of truth ทุก version
│   ├── security.yaml                 # [DevOps] mTLS, KMS, IP whitelist
│   ├── redis.yaml                    # [DevOps] TTL, cluster, TLS
│   ├── proxy.yaml                    # [Network Admin] mitmproxy settings
│   ├── policy.yaml                   # [Network Admin] fail safe, rate limit, request size
│   ├── presidio.yaml                 # [ML/Dev] PII entity rules + custom entities
│   ├── alert.yaml                    # [Admin] email, Slack webhook
│   ├── observability.yaml            # [DevOps] Loki, VictoriaMetrics, Jaeger config
│   ├── domains/
│   │   └── llm_whitelist.yaml        # [Admin] เพิ่ม/ลด LLM domains
│   └── api/
│       ├── keys.yaml                 # [Frontend Dev] API keys ทุกตัว
│       └── endpoints.yaml            # [Frontend Dev] endpoint URLs + versioning
│
├── certs/                            # (ห้าม commit)
│   ├── ca.crt
│   ├── redis/
│   └── mtls/
│
├── backup/
│   ├── timescaledb_backup.sh            # Backup script สำหรับ audit log
│   └── restore_procedure.md          # ขั้นตอน restore ทีละ step
│
├── src/
│   ├── proxy/
│   │   ├── __init__.py
│   │   ├── interceptor.py            # mitmproxy addon
│   │   └── ssl_inspector.py
│   │
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── router.py
│   │   ├── fail_safe.py
│   │   ├── rate_limiter.py
│   │   └── health.py                 # Health check endpoint
│   │
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── text_worker.py
│   │   ├── file_worker.py
│   │   └── ocr_worker.py
│   │
│   ├── deanonymizer/
│   │   ├── __init__.py
│   │   ├── deanonymizer.py
│   │   └── file_repacker.py
│   │
│   ├── mapping_store/
│   │   ├── __init__.py
│   │   └── redis_store.py            # TLS + password + clear after use
│   │
│   ├── audit/
│   │   ├── __init__.py
│   │   └── logger.py                 # Write-once + hash chain → PostgreSQL
│   │
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── metrics.py                # VictoriaMetrics instrumentation
│   │   ├── tracer.py                 # OpenTelemetry + Jaeger setup
│   │   └── log_shipper.py            # ส่ง logs → Loki
│   │
│   ├── domain_updater/
│   │   ├── __init__.py
│   │   └── updater.py
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   ├── mtls.py
│   │   └── secret_manager.py         # Vault (prod) / .env (dev)
│   │
│   └── dashboard/
│       ├── api/
│       │   ├── __init__.py
│       │   ├── main.py               # FastAPI + MFA + IP whitelist
│       │   ├── stats.py
│       │   ├── whitelist.py
│       │   └── audit.py
│       └── ui/
│           ├── package.json
│           └── src/
│               ├── App.jsx
│               ├── pages/
│               │   ├── Dashboard.jsx
│               │   ├── Whitelist.jsx
│               │   └── AuditLog.jsx
│               └── components/
│
└── tests/
    ├── test_text_worker.py
    ├── test_file_worker.py
    ├── test_ocr_worker.py
    ├── test_deanonymizer.py
    ├── test_redis_store.py
    ├── test_rate_limiter.py
    └── test_audit_logger.py
```

## Build Order สำหรับ Claude Code

1. `config/versions.yaml`
2. `config/` ไฟล์ที่เหลือทั้งหมด (รวม api/ และ domains/)
3. `.env.example`
4. `src/security/secret_manager.py`
5. `src/security/mtls.py`
6. `src/observability/` ทุกไฟล์
7. `src/mapping_store/redis_store.py`
8. `src/audit/logger.py`
9. `src/workers/text_worker.py`
10. `src/workers/file_worker.py`
11. `src/workers/ocr_worker.py`
12. `src/orchestrator/`
13. `src/proxy/`
14. `src/deanonymizer/`
15. `src/domain_updater/`
16. `src/dashboard/`
17. `backup/timescaledb_backup.sh`
18. `backup/restore_procedure.md`
19. `runbook.md`
20. `docker-compose.yml` (dev/staging/production)
21. `tests/`
