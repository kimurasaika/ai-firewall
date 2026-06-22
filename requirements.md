# Requirements — AI Firewall / DLP

## Functional Requirements

### Core
1. Intercept HTTPS traffic ที่ไปหา LLM platforms (ChatGPT, Gemini, Grok ฯลฯ)
2. Detect และ redact PII ใน text, PDF, DOCX, และ image ที่อัพโหลด
3. เก็บ session-based mapping ใน Redis (TTL 1 ชั่วโมง)
4. De-anonymize response ที่กลับมาจาก LLM (exact → fuzzy threshold 90 → log)
5. Re-pack file กลับหลัง de-anonymize (DOCX, PDF, image)
6. รองรับภาษาไทย + อังกฤษ
7. HA: proxy 2 nodes + load balancer พร้อม health check endpoint
8. Fail Safe: DLP crash → block เฉพาะ LLM domains, internet ปกติยังใช้ได้
9. Graceful shutdown: flush mapping และปิด connection ก่อน container stop
10. Admin Dashboard: redaction stats, whitelist management, audit log
11. LLM domain whitelist auto-update ด้วย cron job
12. MDM integration สำหรับ CA cert deployment และ mobile policy
13. Alert admin ทันทีเมื่อ DLP crash (email / Slack)

### Rate Limiting & Resource Protection
14. Rate limiting per user/session
15. Request size limit — ป้องกัน OOM crash

### Observability
16. Centralized logging ทุก service → Loki
17. Metrics (latency, error rate, queue length, redaction rate) → VictoriaMetrics
18. Distributed tracing → OpenTelemetry + Jaeger
19. Unified dashboard → Grafana (Loki + VictoriaMetrics + Jaeger)

### Config Management
20. Config แยกตาม role ผู้แก้ไข — Frontend, DevOps, Admin, ML/Dev
21. API keys และ endpoints แยกไฟล์ให้ Frontend แก้ได้โดยไม่ต้องแตะ source code
22. API versioning รองรับ breaking change

### Backup & Recovery
23. TimescaleDB audit log backup อัตโนมัติ
24. Redis recovery procedure เมื่อ crash กลางคัน
25. Restore procedure เป็นลายลักษณ์อักษร

### Documentation
26. Runbook/Playbook — บอกว่าถ้า X พัง ทำ Y สำหรับทุก service

## Non-Functional Requirements

| ด้าน | Requirement |
|---|---|
| Scale | 1,000 concurrent users |
| Latency | เพิ่ม delay ไม่เกิน 200ms ต่อ request |
| Availability | 99.9% uptime |
| Auditability | Log ทุก redaction event พร้อม timestamp + session_id |
| Data Retention | Redis TTL 1hr, Audit log เก็บ 90 วัน |

## Security Requirements

| ช่องโหว่ | Requirement |
|---|---|
| Redis traffic ถูก sniff | TLS in transit + password auth + bind localhost only |
| Internal API ถูก intercept | mTLS ระหว่าง service ทุกตัว |
| Audit log ถูกแก้ | Write-once log + hash chain (tamper evident) |
| Redis ถูก dump | Encrypt at rest + Redis ACL + external KMS |
| Admin Dashboard ถูกเจาะ | MFA + rate limiting + IP whitelist |
| Secrets ถูกอ่าน | Vault ใน production, .env ใน dev เท่านั้น |
| Docker socket exposed | ปิด Docker API ไม่ให้ expose ออก network |
| Mapping ค้างใน memory | Clear mapping ทันทีหลัง de-anonymize |
| CA cert ถูก compromise | CA cert rotation policy + MDM force update |

## Environment
- **dev** — .env, local Docker Compose
- **staging** — .env.staging, ทดสอบก่อน production
- **production** — Vault, full HA, mTLS ครบ

## PII Entity Types

| Entity | Token Format |
|---|---|
| ชื่อ-นามสกุล | `<<P001>>` |
| เบอร์โทร | `<<PH001>>` |
| อีเมล | `<<EM001>>` |
| เลขบัตรประชาชน | `<<ID001>>` |
| ที่อยู่ | `<<AD001>>` |
| ชื่อบริษัท/โปรเจกต์ | `<<ORG001>>` |
| PII ในรูปภาพ | OCR แล้ว overlay สีดำทับ bounding box |

## Out of Scope (v1)
- Mobile hotspot / VPN ส่วนตัว
- LLM on-premise
- Real-time de-anonymization สำหรับ streaming response
- CI/CD pipeline (GitHub Actions) — v2
