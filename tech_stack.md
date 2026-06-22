# Tech Stack — AI Firewall / DLP

## Layer Breakdown

| Layer | Technology | Version | หน้าที่ |
|---|---|---|---|
| Load Balancer | HAProxy | 2.8 | กระจาย traffic + health check |
| Proxy | mitmproxy | 10.x | SSL inspection, intercept HTTPS |
| Orchestrator | FastAPI | 0.111 | รับงานจาก proxy แจกให้ worker |
| Text Redaction | microsoft/presidio-analyzer | 2.x | Detect + redact PII ใน plain text |
| Thai NER | pythainlp | 5.x | NER ภาษาไทย |
| File Parser | pdfplumber | 0.11 | อ่าน PDF |
| File Re-pack | reportlab | 4.x | สร้าง PDF กลับ |
| DOCX | python-docx | 1.x | อ่านและเขียน DOCX |
| OCR | easyocr | 1.7 | Extract text จาก image |
| Image Processing | Pillow | 10.x | Overlay/redact bounding box |
| Fuzzy Match | rapidfuzz | 3.x | De-anonymize token ที่ LLM แก้ไข |
| Mapping Store | Redis | 7.x | Session mapping (TTL 1hr) + TLS |
| Audit DB | TimescaleDB | 2.x (PostgreSQL 16 extension) | Write-once audit log + auto-expire 90 วัน |
| Admin API | FastAPI | 0.111 | Backend dashboard + MFA |
| Admin UI | React + Tailwind | 18.x / 3.x | Dashboard |
| Domain Updater | APScheduler | 3.x | Cron job update LLM whitelist |
| Secret Manager | HashiCorp Vault | 1.x | Secrets ใน production |
| mTLS | Python ssl | built-in | Internal service communication |
| **Logging** | **Loki** | **3.x** | **Centralized logs ทุก service** |
| **Metrics** | **VictoriaMetrics** | **1.x** | **แทน Prometheus — เบากว่า 3-7x** |
| **Tracing** | **OpenTelemetry + Jaeger** | **1.x** | **Distributed tracing** |
| **Dashboard** | **Grafana** | **10.x** | **Unified view: logs+metrics+traces** |
| Container | Docker + Compose | 25.x | Deploy ทุก service |
| MDM | Jamf / Microsoft Intune | - | CA cert + mobile policy |

> ⚠️ version จริงทั้งหมดอยู่ใน `config/versions.yaml` — แก้ที่นั่นที่เดียว ห้ามแก้ requirements.txt ตรงๆ

## Environment

| Environment | Secrets | Deploy |
|---|---|---|
| dev | .env | docker-compose.yml |
| staging | .env.staging | docker-compose.staging.yml |
| production | HashiCorp Vault | docker-compose.production.yml |

## Infrastructure

```
OS:             Ubuntu 22.04 LTS
Container:      Docker 25.x
CA Cert:        Self-signed corporate CA (deploy ผ่าน MDM)
Secret Store:   HashiCorp Vault (production) / .env (dev only)
Audit DB:       TimescaleDB (PostgreSQL extension — DevOps ใช้ SQL ปกติได้เลย)
TLS:            mTLS ระหว่าง services, TLS สำหรับ Redis
Observability:  Loki + VictoriaMetrics + Jaeger → Grafana
```
