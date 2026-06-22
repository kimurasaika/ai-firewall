# AI Firewall / DLP — Runbook

> Format: **IF [symptom] → DO [action]**

---

## 1. DLP Orchestrator Crash

**Symptom:** Grafana shows `dlp_fail_safe_active = 1` OR users see "AI tools unavailable"

**Do:**
1. Check container logs: `docker compose logs orchestrator --tail 100`
2. Check Redis connection: `docker compose exec orchestrator python -c "from src.mapping_store.redis_store import RedisStore; import asyncio; print(asyncio.run(RedisStore().ping()))"`
3. Check database connection: `docker compose exec timescaledb psql -U dlp_user -d dlp_audit -c "SELECT 1;"`
4. If OOM: increase `deploy.resources.limits.memory` in docker-compose.production.yml, restart
5. Restart orchestrator: `docker compose restart orchestrator`
6. Verify health: `curl -sk https://localhost:8443/health`
7. Once healthy, fail-safe deactivates automatically (within 10s)
8. Notify IT team that LLM access is restored

---

## 2. Redis Unavailable

**Symptom:** `dlp_redis_errors_total` spiking in Grafana, sessions failing

**Do:**
1. Check Redis: `docker compose logs redis --tail 50`
2. If Redis restarted mid-session: active sessions are lost (TTL 1hr — users must retry)
3. Restart Redis: `docker compose restart redis`
4. Verify: `docker compose exec redis redis-cli -a "${REDIS_PASSWORD}" --tls ping`
5. Check TLS cert validity: `openssl x509 -in certs/redis/client.crt -noout -dates`
6. Alert admin: sessions lost since last Redis crash

---

## 3. mTLS Certificate Expired

**Symptom:** Internal service calls returning 503, logs show TLS handshake errors

**Do:**
1. Identify which cert expired:
   ```bash
   for svc in orchestrator proxy dashboard_api; do
     echo "$svc:"; openssl x509 -in certs/mtls/${svc}.crt -noout -dates
   done
   ```
2. Re-generate expired cert (signed by corporate CA):
   ```bash
   openssl req -new -key certs/mtls/${SVC}.key -out /tmp/${SVC}.csr -subj "/CN=${SVC}"
   openssl x509 -req -in /tmp/${SVC}.csr -CA certs/ca.crt -CAkey certs/ca.key \
     -CAcreateserial -out certs/mtls/${SVC}.crt -days 365
   ```
3. Restart affected service: `docker compose restart ${SVC}`
4. Schedule recurring cert rotation: alert fires 14 days before expiry

---

## 4. High De-anonymization Miss Rate

**Symptom:** `dlp_deanon_misses_total{match_type="miss"}` > 5% in Grafana, or WARNING logs in Loki

**Possible causes:**
- LLM rephrased the token (e.g., `<<P001>>` → `<P001>` or `P001`)
- Session mapping expired (TTL 1hr) before response arrived
- Fuzzy threshold too strict

**Do:**
1. Check Loki for: `{service="orchestrator"} |= "Deanonymization miss"`
2. If tokens are being altered by LLM: lower fuzzy threshold in `src/deanonymizer/deanonymizer.py` (`_FUZZY_THRESHOLD`)
3. If session expired: check if LLM response took > 1hr (extremely rare; extend TTL in `config/redis.yaml` if needed)
4. Alert user via admin dashboard: their response may contain placeholders

---

## 5. TimescaleDB Audit Log Full / Slow

**Symptom:** Dashboard queries timeout, disk usage > 80%

**Do:**
1. Check disk: `docker compose exec timescaledb df -h /var/lib/postgresql/data`
2. Force compression: `docker compose exec timescaledb psql -U dlp_user -d dlp_audit -c "SELECT compress_chunk(i) FROM show_chunks('audit_log') i;"`
3. Manual purge of old data (retention policy should handle this automatically):
   ```sql
   DELETE FROM audit_log WHERE created_at < NOW() - INTERVAL '90 days';
   ```
4. If disk still full: expand volume or archive to S3 then delete

---

## 6. Proxy SSL Inspection Failing

**Symptom:** Users get SSL errors in browser, Loki shows mitmproxy errors

**Do:**
1. Check proxy logs: `docker compose logs proxy --tail 100`
2. Verify CA cert is deployed to user devices via MDM (Jamf/Intune)
3. Check mitmproxy CA cert: `openssl x509 -in certs/ca.crt -noout -dates`
4. If CA cert expired: rotate CA cert, redeploy via MDM, restart proxy
5. Restart proxy: `docker compose restart proxy`

---

## 7. Admin Dashboard Unreachable

**Symptom:** Admin cannot log in to dashboard

**Do:**
1. Check dashboard API: `docker compose logs dashboard_api --tail 50`
2. Verify IP whitelist: `echo $ADMIN_IP_WHITELIST` — ensure admin's IP is included
3. Check MFA secret: `echo $ADMIN_TOTP_SECRET` — must be non-empty
4. Restart: `docker compose restart dashboard_api`
5. If TOTP secret lost: generate new one and update ADMIN_TOTP_SECRET in Vault/.env, re-scan QR

---

## 8. OOM / Memory Pressure on Workers

**Symptom:** Worker containers killed (exit code 137), large files failing

**Do:**
1. Check limits: `docker stats`
2. OCR Worker uses most memory — for large images: reduce `config/policy.yaml:request_limits.max_image_size_mb`
3. File Worker: reduce `config/policy.yaml:request_limits.max_file_pages`
4. Increase Docker memory limit in docker-compose.production.yml under the affected service
5. Restart workers: `docker compose restart text_worker file_worker ocr_worker`

---

## 9. Domain Updater Not Running

**Symptom:** New LLM domains not blocked, `domain_update` job missing from logs

**Do:**
1. Check logs: `docker compose logs domain_updater --tail 50`
2. Trigger manually: `docker compose exec domain_updater python -c "import asyncio; from src.domain_updater.updater import update_domains; asyncio.run(update_domains())"`
3. Restart: `docker compose restart domain_updater`

---

## 10. Alert Notifications Not Sending

**Symptom:** DLP crash happened but no Slack/email received

**Do:**
1. Check SLACK_WEBHOOK_URL in `.env` / Vault is correct
2. Test Slack webhook: `curl -X POST -H 'Content-type: application/json' --data '{"text":"test"}' $SLACK_WEBHOOK_URL`
3. Check SMTP credentials: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`
4. Check `config/alert.yaml` — `slack.enabled` and `email.enabled` must be `true`
