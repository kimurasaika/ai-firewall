# Prompt สำหรับ Claude Code

อ่านไฟล์เหล่านี้ก่อนทุกครั้ง:
- architecture.md
- requirements.md
- tech_stack.md
- project_structure.md

---

## งานที่ต้องทำ

สร้าง AI Firewall / DLP system ตาม architecture และ requirements ที่กำหนด

## กฎการเขียนโค้ด

1. แยกไฟล์ตาม project_structure.md ทุกครั้ง ห้าม hardcode ใน file เดียว
2. secrets ทั้งหมดอยู่ใน .env (dev) หรือ Vault (production) เท่านั้น
3. version ทั้งหมดอยู่ใน config/versions.yaml เท่านั้น ห้ามฝังใน source code
4. config ทั้งหมดอยู่ใน config/ แยกตาม role ผู้แก้ไข
5. ทุก module ต้องมี error handling และ logging
6. ใช้ type hints ทุกฟังก์ชัน
7. Internal service ทุกตัวต้องใช้ mTLS
8. Redis ต้องใช้ TLS + password + bind localhost only
9. Clear mapping จาก memory ทันทีหลัง de-anonymize เสร็จ
10. ทุก service ต้อง instrument OpenTelemetry + ส่ง logs ไป Loki

## ลำดับการทำ

1. config/versions.yaml
2. config/ ไฟล์ที่เหลือ (รวม api/ และ domains/)
3. .env.example
4. src/security/secret_manager.py
5. src/security/mtls.py
6. src/observability/ (metrics.py, tracer.py, log_shipper.py)
7. src/mapping_store/redis_store.py
8. src/audit/logger.py
9. src/workers/text_worker.py
10. src/workers/file_worker.py
11. src/workers/ocr_worker.py
12. src/orchestrator/
13. src/proxy/
14. src/deanonymizer/
15. src/domain_updater/
16. src/dashboard/
17. backup/timescaledb_backup.sh
18. backup/restore_procedure.md
19. runbook.md
20. docker-compose.yml (dev/staging/production)
21. tests/

## Token Format

| Entity | Token |
|---|---|
| ชื่อ-นามสกุล | `<<P001>>` |
| เบอร์โทร | `<<PH001>>` |
| อีเมล | `<<EM001>>` |
| เลขบัตรประชาชน | `<<ID001>>` |
| ที่อยู่ | `<<AD001>>` |
| ชื่อบริษัท/โปรเจกต์ | `<<ORG001>>` |

## De-anonymization Logic

```
1. Exact match → replace
2. ไม่เจอ → Fuzzy match rapidfuzz (threshold=90)
3. ไม่เจอ → log WARNING พร้อม session_id + token
4. Clear mapping จาก memory หลัง de-anonymize เสร็จ
```

## Fail Safe Logic

```
DLP crash → block เฉพาะ LLM domains → internet ปกติใช้ได้
→ alert admin ทันที (email + Slack)
```

## Security ที่ต้องมีทุก service

```
- mTLS ระหว่าง services ทุกตัว
- Redis: requirepass + TLS + bind 127.0.0.1
- Audit log: write-once + hash chain (SHA-256)
- Admin Dashboard: MFA + rate limit + IP whitelist
- Docker: ปิด socket ไม่ให้ expose
- Secrets: Vault (prod) / .env (dev)
```

## Observability ที่ต้องมีทุก service

```
- OpenTelemetry trace ทุก request
- ส่ง metrics → VictoriaMetrics (latency, error rate, queue length)
- ส่ง logs → Loki พร้อม structured JSON format
- Grafana dashboard ครอบคลุม logs + metrics + traces
```

## Out of Scope (v1) — ไม่ต้องทำ

- CI/CD pipeline (GitHub Actions)
- Mobile hotspot / VPN bypass
- LLM on-premise
- Streaming response de-anonymization
