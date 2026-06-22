# TimescaleDB Audit Log — Restore Procedure

## When to use this
- TimescaleDB container data volume is lost or corrupted
- Migrating audit log to a new server
- DR failover

---

## Prerequisites
- Access to backup files (local `/backups/timescaledb/` or S3)
- `psql` or `pg_restore` installed
- `DATABASE_URL` environment variable set
- TimescaleDB extension already installed on target PostgreSQL instance

---

## Step 1 — Identify the backup to restore

```bash
# List available backups
ls -lth /backups/timescaledb/audit_log_*.sql.gz | head -20

# Or from S3
aws s3 ls s3://${S3_BUCKET}/dlp-audit-backups/ --human-readable | sort -k1,2 | tail -20
```

Choose the most recent backup before the incident, or the specific point-in-time required.

---

## Step 2 — Download from S3 (if needed)

```bash
aws s3 cp s3://${S3_BUCKET}/dlp-audit-backups/audit_log_YYYYMMDD_HHMMSS.sql.gz /tmp/restore.sql.gz
```

---

## Step 3 — Verify backup integrity

```bash
gunzip -t /tmp/restore.sql.gz && echo "OK"
```

---

## Step 4 — Stop all services that write to audit_log

```bash
docker compose stop orchestrator
```

---

## Step 5 — Re-create the table (if the table is missing)

```bash
psql "${DATABASE_URL}" <<'SQL'
CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id  TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    user_agent  TEXT,
    source_ip   TEXT,
    entity_type TEXT,
    token       TEXT,
    content_type TEXT,
    details     JSONB,
    prev_hash   TEXT NOT NULL,
    row_hash    TEXT NOT NULL
);
SELECT create_hypertable('audit_log', 'created_at', if_not_exists => TRUE);
SELECT add_retention_policy('audit_log', INTERVAL '90 days', if_not_exists => TRUE);
SQL
```

---

## Step 6 — Restore data

```bash
gunzip -c /tmp/restore.sql.gz | psql "${DATABASE_URL}"
```

---

## Step 7 — Verify row count and hash chain

```bash
psql "${DATABASE_URL}" -c "SELECT COUNT(*) FROM audit_log;"

# Verify hash chain via API (after restarting orchestrator)
curl -sk -H "Authorization: Bearer <token>" https://localhost:9443/v1/audit/verify-chain
# Expected: {"chain_valid": true}
```

---

## Step 8 — Restart services

```bash
docker compose start orchestrator
docker compose ps
```

---

## Post-restore checklist

- [ ] Row count matches expected count from before the incident
- [ ] Hash chain reports `chain_valid: true`
- [ ] New audit events are being written (check Grafana / Loki)
- [ ] Alert admin team that restore is complete
- [ ] Document the incident in the incident log

---

## Notes
- The audit log is append-only — restoring replaces data up to the backup point. Events between the backup and the incident are lost.
- If the hash chain is broken after restore, investigate whether the data was tampered with before the incident.
