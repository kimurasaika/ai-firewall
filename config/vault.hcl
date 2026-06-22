# HashiCorp Vault server configuration (production)
# DevOps manages this file

ui = true

storage "file" {
  path = "/vault/data"
}

listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_cert_file = "/vault/certs/mtls/vault.crt"
  tls_key_file  = "/vault/certs/mtls/vault.key"
  tls_client_ca_file = "/vault/certs/ca.crt"
}

api_addr     = "https://vault:8200"
cluster_addr = "https://vault:8201"

log_level = "warn"
log_format = "json"

# Disable memory locking in Docker (requires IPC_LOCK cap)
disable_mlock = false
