"""Admin Dashboard API — FastAPI + MFA + IP whitelist + rate limiting."""
import ipaddress
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pyotp
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from passlib.context import CryptContext
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.dashboard.api.audit import router as audit_router
from src.dashboard.api.stats import router as stats_router
from src.dashboard.api.whitelist import router as whitelist_router
from src.observability.log_shipper import configure_logging
from src.observability.tracer import setup_tracer
from src.security.secret_manager import get_secret

configure_logging("dashboard_api", os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
setup_tracer("dashboard_api")

# ── Rate limiting ────────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="AI Firewall Admin Dashboard", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

FastAPIInstrumentor.instrument_app(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Auth setup ───────────────────────────────────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_IP_WHITELIST_RAW = os.environ.get(
    "ADMIN_IP_WHITELIST",
    "127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
).split(",")
_IP_WHITELIST = [ipaddress.ip_network(ip.strip(), strict=False) for ip in _IP_WHITELIST_RAW]


# ── IP whitelist middleware ───────────────────────────────────────────────────────
@app.middleware("http")
async def ip_whitelist_middleware(request: Request, call_next: Any) -> Any:
    if request.url.path in ("/health", "/docs", "/openapi.json"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "0.0.0.0"
    try:
        addr = ipaddress.ip_address(client_ip)
        allowed = any(addr in net for net in _IP_WHITELIST)
    except ValueError:
        allowed = False

    if not allowed:
        logger.warning("Dashboard: blocked request from IP=%s", client_ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP not whitelisted")

    return await call_next(request)


# ── Auth models ───────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class MFARequest(BaseModel):
    temp_token: str
    totp_code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _create_jwt(data: dict[str, Any], expire_minutes: int = 60) -> str:
    secret = get_secret("admin_jwt_secret")
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    return jwt.encode(payload, secret, algorithm="HS256")


def _decode_jwt(token: str) -> dict[str, Any]:
    secret = get_secret("admin_jwt_secret")
    return jwt.decode(token, secret, algorithms=["HS256"])


async def require_auth(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    try:
        payload = _decode_jwt(token)
        if payload.get("stage") != "authenticated":
            raise JWTError("Not fully authenticated")
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── Auth endpoints ────────────────────────────────────────────────────────────────
@app.post("/v1/auth/login", response_model=dict)
@limiter.limit("30/minute")
async def login(request: Request, form: LoginRequest) -> dict:
    # In production: look up user from DB and verify bcrypt hash
    # Dev stub: single admin user from env
    admin_user = os.environ.get("ADMIN_USERNAME", "admin")
    admin_pass_hash = os.environ.get("ADMIN_PASSWORD_HASH", "")

    if form.username != admin_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if admin_pass_hash and not pwd_context.verify(form.password, admin_pass_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Issue temp token for MFA step
    temp_token = _create_jwt({"sub": form.username, "stage": "pre_mfa"}, expire_minutes=5)
    return {"temp_token": temp_token, "mfa_required": True}


@app.post("/v1/auth/mfa", response_model=TokenResponse)
@limiter.limit("10/minute")
async def verify_mfa(request: Request, mfa: MFARequest) -> TokenResponse:
    try:
        payload = _decode_jwt(mfa.temp_token)
        if payload.get("stage") != "pre_mfa":
            raise JWTError("Invalid stage")
        username = payload["sub"]
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid temp token") from exc

    totp_secret = os.environ.get("ADMIN_TOTP_SECRET", "")
    if not totp_secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="MFA not configured")

    totp = pyotp.TOTP(totp_secret)
    if not totp.verify(mfa.totp_code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    access_token = _create_jwt(
        {"sub": username, "stage": "authenticated"},
        expire_minutes=int(os.environ.get("ADMIN_JWT_EXPIRE_MINUTES", "60")),
    )
    logger.info("Admin login successful: user=%s", username)
    return TokenResponse(access_token=access_token)


# ── Protected routes ──────────────────────────────────────────────────────────────
app.include_router(stats_router, dependencies=[Depends(require_auth)])
app.include_router(whitelist_router, dependencies=[Depends(require_auth)])
app.include_router(audit_router, dependencies=[Depends(require_auth)])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "src.dashboard.api.main:app",
        host=os.environ.get("DASHBOARD_HOST", "0.0.0.0"),
        port=int(os.environ.get("DASHBOARD_PORT", "9443")),
        ssl_keyfile="/app/certs/mtls/dashboard_api.key",
        ssl_certfile="/app/certs/mtls/dashboard_api.crt",
        ssl_ca_certs="/app/certs/ca.crt",
        ssl_cert_reqs=2,
    )
