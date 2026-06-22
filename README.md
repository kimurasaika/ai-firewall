# AI Firewall / DLP Proxy

A corporate transparent HTTPS proxy that intercepts traffic to LLM platforms (ChatGPT, Gemini, Grok, etc.), redacts PII before sending requests, and de-anonymizes LLM responses before returning them to users — without the user needing to change anything on their end.

## Architecture

```
User Browser
    │
    ▼
[mitmproxy Transparent Proxy :8080]
    │  intercepts HTTPS, strips TLS
    ▼
[DLP Orchestrator :8443]  ◄──► [Redis TLS]   (session token mapping)
    │  redact PII → <<EM001>>, <<PH001>>, etc.
    ▼
[LLM Platform]  (ChatGPT / Gemini / Grok)
    │  response with tokens
    ▼
[DLP Orchestrator]  ◄──► [Redis TLS]   (reverse-lookup tokens → originals)
    │  de-anonymize response
    ▼
User Browser  (sees real response, PII never left the network)
```

**Key components:**

| Service | Port | Description |
|---|---|---|
| `proxy` | 8080 | mitmproxy transparent HTTPS proxy |
| `orchestrator` | 8443 | DLP engine — redact / de-anonymize |
| `dashboard_api` | 9443 | Admin REST API (MFA + IP whitelist) |
| `dashboard_ui` | 3001 | React admin dashboard |
| `redis` | 6379 | Session token mapping (TLS + mTLS) |
| `timescaledb` | 5432 | Write-once audit log (90-day retention) |
| `jaeger` | 16686 | Distributed tracing UI |
| `victoriametrics` | 8428 | Metrics (Prometheus-compatible) |
| `grafana` | 3000 | Dashboards |
| `loki` | 3100 | Log aggregation |

**PII token format:** `<<EM001>>` (email), `<<PH001>>` (phone), `<<P001>>` (person), `<<ID001>>` (ID card), `<<AD001>>` (address), `<<ORG001>>` (org)

**De-anonymization:** exact match → fuzzy match (RapidFuzz ≥ 90) → log WARNING → leave token as-is

## Prerequisites

- Docker Desktop (with WSL2 backend on Windows)
- `openssl` CLI (for generating certs)
- Python 3.11+ (for running tests locally)

## Setup

### 1. Clone and configure environment

```bash
git clone https://github.com/kimurasaika/ai-firewall.git
cd ai-firewall
cp .env .env.local   # .env already contains dev defaults
```

Edit `.env` and change all `change-me-*` values:

```env
REDIS_PASSWORD=your-strong-password
TIMESCALEDB_PASSWORD=your-db-password
ADMIN_JWT_SECRET=your-jwt-secret-min-32-chars
ADMIN_TOTP_SECRET=          # generate with: python -c "import pyotp; print(pyotp.random_base32())"
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=        # generate with: python -c "from passlib.context import CryptContext; print(CryptContext(['bcrypt']).hash('yourpassword'))"
```

### 2. Generate TLS / mTLS certificates

```bash
mkdir -p certs/mtls certs/redis

# CA
openssl req -x509 -newkey rsa:4096 -keyout certs/ca.key -out certs/ca.crt \
  -days 3650 -nodes -subj "/CN=DLP-CA"

# Per-service mTLS certs (repeat for each service)
for svc in orchestrator proxy dashboard_api deanonymizer text_worker ocr_worker file_worker domain_updater; do
  openssl req -newkey rsa:2048 -keyout certs/mtls/${svc}.key -out /tmp/${svc}.csr \
    -nodes -subj "/CN=${svc}"
  openssl x509 -req -in /tmp/${svc}.csr -CA certs/ca.crt -CAkey certs/ca.key \
    -CAcreateserial -out certs/mtls/${svc}.crt -days 3650
done

# Redis client cert
openssl req -newkey rsa:2048 -keyout certs/redis/client.key -out /tmp/redis-client.csr \
  -nodes -subj "/CN=redis-client"
openssl x509 -req -in /tmp/redis-client.csr -CA certs/ca.crt -CAkey certs/ca.key \
  -CAcreateserial -out certs/redis/client.crt -days 3650

# Redis server cert
openssl req -newkey rsa:2048 -keyout certs/redis/redis.key -out /tmp/redis.csr \
  -nodes -subj "/CN=redis"
openssl x509 -req -in /tmp/redis.csr -CA certs/ca.crt -CAkey certs/ca.key \
  -CAcreateserial -out certs/redis/redis.crt -days 3650
```

### 3. Start all services

```bash
docker compose up -d
```

Wait ~30 seconds for all services to initialise, then check health:

```bash
docker compose ps
```

All services should show `(healthy)`.

## How to Use

### Check health

```bash
# From host / WSL
curl -k https://localhost:8443/health
# Expected: {"status":"ok","redis":"ok","database":"ok"}
```

### Redact PII

```bash
curl -k -X POST https://localhost:8443/v1/redact \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Hi, my name is John Smith, email john@acme.com, phone 0812345678",
    "content_type": "text/plain",
    "user_id": "alice"
  }'
```

Response:

```json
{
  "redacted_content": "Hi, my name is <<P001>>, email <<EM001>>, phone <<PH001>>",
  "session_id": "abc123...",
  "entities_found": 3,
  "is_base64": false
}
```

### De-anonymize LLM response

```bash
curl -k -X POST https://localhost:8443/v1/deanonymize \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Hello <<P001>>, I sent a reply to <<EM001>>.",
    "session_id": "abc123...",
    "user_id": "alice"
  }'
```

### Admin Dashboard API

```bash
# 1. Login (get temp token)
curl -k -X POST https://localhost:9443/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"yourpassword"}'

# 2. Verify TOTP (get access token)
curl -k -X POST https://localhost:9443/v1/auth/mfa \
  -H "Content-Type: application/json" \
  -d '{"temp_token":"<temp_token>","totp_code":"123456"}'

# 3. List whitelisted LLM domains
curl -k -H "Authorization: Bearer <access_token>" \
  https://localhost:9443/v1/whitelist

# 4. View audit log
curl -k -H "Authorization: Bearer <access_token>" \
  https://localhost:9443/v1/audit?limit=20
```

### Admin UI

Open `http://localhost:3001` in your browser.

### Observability

| Tool | URL |
|---|---|
| Jaeger (traces) | http://localhost:16686 |
| Grafana | http://localhost:3000 (admin / from `.env`) |
| VictoriaMetrics | http://localhost:8428 |

## How to Test

### Unit tests

```bash
pip install -r dockerfiles/requirements/orchestrator.txt
pytest tests/ -v
```

### Integration tests (requires running stack)

```bash
pytest tests/integration/ -v
```

### Smoke test

```bash
python scripts/smoke_test.py
```

### Manual end-to-end test

```bash
# Redact → store mapping → de-anonymize in one shot
SESSION=$(curl -sk -X POST https://localhost:8443/v1/redact \
  -H "Content-Type: application/json" \
  -d '{"content":"email: test@example.com","content_type":"text/plain","user_id":"test"}' \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['session_id'])")

curl -sk -X POST https://localhost:8443/v1/deanonymize \
  -H "Content-Type: application/json" \
  -d "{\"content\":\"reply to <<EM001>>\",\"session_id\":\"$SESSION\",\"user_id\":\"test\"}"
```

### Test from WSL to Docker (Windows)

```bash
# 172.27.144.1 is the Windows host IP as seen from WSL2
curl -k -X POST https://172.27.144.1:8443/v1/redact \
  -H "Content-Type: application/json" \
  -d '{"content":"test@example.com","content_type":"text/plain","user_id":"me"}'
```

## Environment Comparison

| Feature | Dev (`docker-compose.yml`) | Staging | Production |
|---|---|---|---|
| Secrets | `.env` file | `.env.staging` | HashiCorp Vault |
| mTLS client cert required | No (CERT_NONE) | Yes | Yes |
| TLS cert verification | Skip (self-signed) | Full | Full |
| Audit retention | 90 days | 90 days | 90 days |
| Workers | 2 | 4 | 8+ |

## Project Structure

```
ai-firewall/
├── src/
│   ├── orchestrator/     # FastAPI DLP engine
│   ├── proxy/            # mitmproxy transparent proxy
│   ├── workers/          # text_worker, ocr_worker, file_worker
│   ├── deanonymizer/     # reverse-lookup + fuzzy match
│   ├── audit/            # write-once hash-chain audit logger
│   ├── mapping_store/    # Redis session store
│   ├── dashboard/
│   │   ├── api/          # FastAPI admin API
│   │   └── ui/           # React + Tailwind admin UI
│   ├── observability/    # OTel tracing, metrics, log shipper
│   └── security/         # mTLS, secret manager
├── config/               # YAML configs (domains, policy, etc.)
├── dockerfiles/          # Per-service Dockerfiles + requirements
├── tests/                # Unit + integration tests
├── scripts/              # smoke_test.py
├── backup/               # TimescaleDB backup scripts
├── certs/                # TLS/mTLS certs (git-ignored)
├── docker-compose.yml          # Dev
├── docker-compose.staging.yml  # Staging
└── docker-compose.production.yml # Production
```

## Security Notes

- `certs/` is git-ignored — generate your own certs locally
- `.env` contains dev defaults only — never use in production
- Redis uses mTLS (`--tls-auth-clients yes`) — client cert required
- Audit log is write-once with SHA-256 hash chain — tampering is detectable
- Admin dashboard enforces TOTP MFA + IP whitelist + rate limiting
- All internal service communication uses mTLS
- In production, set `ENVIRONMENT=production` to enforce `ssl.CERT_REQUIRED` on all connections

## License

MIT
