"""Read-only production checks. Never prints Compose environment values or keys."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.production.yml"]


class PreflightError(Exception):
    pass


def openssl(arguments, *, executable="openssl"):
    result = subprocess.run([executable, *arguments], capture_output=True, timeout=20)
    if result.returncode:
        raise PreflightError("OpenSSL verification failed: " + arguments[0])
    return result.stdout


def validate_tls(directory, ca_file, *, executable="openssl"):
    directory, ca_file = Path(directory), Path(ca_file)
    certificate, private_key = directory / "origin.pem", directory / "origin.key"
    for file in (certificate, private_key, ca_file):
        if not file.is_file() or file.stat().st_size == 0:
            raise PreflightError(f"Missing or empty TLS file: {file}")
    try:
        openssl(["x509", "-in", str(certificate), "-noout", "-checkend", "86400"], executable=executable)
    except PreflightError:
        raise PreflightError("Origin certificate is invalid or expires within 24 hours") from None
    for hostname in ("gnkalgo.com", "www.gnkalgo.com", "app.gnkalgo.com"):
        try:
            openssl(["verify", "-purpose", "sslserver", "-CAfile", str(ca_file), "-untrusted", str(certificate), "-verify_hostname", hostname, str(certificate)], executable=executable)
        except PreflightError:
            raise PreflightError(f"Certificate trust, validity or hostname check failed for {hostname}") from None
    certificate_public = openssl(["x509", "-in", str(certificate), "-noout", "-pubkey"], executable=executable)
    key_public = openssl(["pkey", "-in", str(private_key), "-passin", "pass:", "-pubout"], executable=executable)
    if hashlib.sha256(certificate_public).digest() != hashlib.sha256(key_public).digest():
        raise PreflightError("origin.key does not match origin.pem")


def validate_environment(environment):
    if environment.get("ENVIRONMENT") != "production":
        raise PreflightError("Set ENVIRONMENT=production in the server .env")
    if str(environment.get("COOKIE_SECURE", "")).lower() != "true":
        raise PreflightError("Set COOKIE_SECURE=true in the server .env")
    secret = environment.get("SECRET_KEY", "")
    password = environment.get("POSTGRES_PASSWORD", "")
    if len(secret) < 40 or secret.startswith(("REPLACE", "development")):
        raise PreflightError("Set a random production SECRET_KEY of at least 40 characters")
    if not password or password.startswith("REPLACE"):
        raise PreflightError("Set POSTGRES_PASSWORD; keep an existing database password unchanged")
    origins = {s.strip() for s in environment.get("ALLOWED_ORIGINS", "").split(",")}
    if origins != {"https://gnkalgo.com", "https://www.gnkalgo.com"}:
        raise PreflightError("ALLOWED_ORIGINS must contain https://gnkalgo.com and https://www.gnkalgo.com")


def ca_path(environment, tls_directory):
    explicit = os.environ.get("ORIGIN_CA_FILE") or environment.get("ORIGIN_CA_FILE") or environment.get("TLS_CA_FILE")
    if explicit:
        return Path(explicit)
    cloudflare_ca = Path(tls_directory) / "cloudflare-origin-ca.pem"
    return cloudflare_ca if cloudflare_ca.is_file() else Path("/etc/ssl/certs/ca-certificates.crt")


def main():
    if not shutil.which("openssl") or not shutil.which("docker"):
        raise PreflightError("Install Docker Compose and OpenSSL on the Ubuntu host first")
    result = subprocess.run([*COMPOSE, "config", "--format", "json"], cwd=ROOT, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise PreflightError("Compose configuration could not be resolved; check the server .env")
    config = json.loads(result.stdout)
    validate_environment(config["services"]["api"]["environment"])
    mounts = config["services"]["nginx"]["volumes"]
    tls = next((m["source"] for m in mounts if m.get("target") == "/etc/nginx/tls" and m.get("type") == "bind"), None)
    if not tls:
        raise PreflightError("Production Nginx needs a TLS_DIR bind mount")
    ca_file = ca_path(config["services"]["api"]["environment"], tls)
    validate_tls(tls, ca_file)
    if "--print-ca" in sys.argv:
        print(ca_file.resolve())
        return
    print("Production preflight passed: environment, certificate expiry, all three hostnames, CA trust and matching private key.")


if __name__ == "__main__":
    try:
        main()
    except (PreflightError, OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        print(f"Preflight stopped: {exc}", file=sys.stderr)
        sys.exit(1)
