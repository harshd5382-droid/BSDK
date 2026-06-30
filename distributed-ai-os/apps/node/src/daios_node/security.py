"""Security utilities for Generation 2 (mTLS + API tokens)."""

from __future__ import annotations

import logging
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from daios_protocol.config import NodeConfig, SecurityConfig

logger = logging.getLogger(__name__)


def _certs_dir(config: NodeConfig) -> Path:
    return Path.home() / ".daios" / "certs" / config.node_id


def ensure_dev_certs(config: NodeConfig) -> SecurityConfig:
    """Generate self-signed dev certs if mTLS enabled and none provided."""
    sec = config.security
    if not sec.mtls_enabled:
        return sec
    if sec.ca_cert and sec.node_cert and sec.node_key:
        return sec
    if not sec.auto_generate_certs:
        logger.warning("mTLS enabled but no certs and auto_generate_certs=false")
        return sec
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        logger.warning("cryptography not installed; mTLS disabled")
        return sec

    cert_dir = _certs_dir(config)
    cert_dir.mkdir(parents=True, exist_ok=True)
    ca_path = cert_dir / "ca.pem"
    cert_path = cert_dir / "node.pem"
    key_path = cert_dir / "node.key"

    if cert_path.exists() and key_path.exists():
        return SecurityConfig(
            mtls_enabled=True,
            ca_cert=str(ca_path) if ca_path.exists() else None,
            node_cert=str(cert_path),
            node_key=str(key_path),
            api_token=sec.api_token,
            auto_generate_certs=sec.auto_generate_certs,
        )

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, config.node_id)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    ca_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    logger.info("Generated dev mTLS certs in %s", cert_dir)
    return SecurityConfig(
        mtls_enabled=True,
        ca_cert=str(ca_path),
        node_cert=str(cert_path),
        node_key=str(key_path),
        api_token=sec.api_token,
        auto_generate_certs=sec.auto_generate_certs,
    )


def create_ssl_context(config: NodeConfig) -> ssl.SSLContext | None:
    """Build SSL context for peer HTTP client if mTLS enabled."""
    sec = ensure_dev_certs(config)
    if not sec.mtls_enabled or not sec.node_cert or not sec.node_key:
        return None
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    if sec.ca_cert:
        ctx.load_verify_locations(sec.ca_cert)
    ctx.load_cert_chain(sec.node_cert, sec.node_key)
    return ctx


class ApiTokenMiddleware(BaseHTTPMiddleware):
    """Optional Bearer token auth for /v1/* endpoints."""

    def __init__(self, app, token: str | None) -> None:
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        if not self.token:
            return await call_next(request)
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if auth == f"Bearer {self.token}":
            return await call_next(request)
        raise HTTPException(status_code=401, detail="Invalid or missing API token")
