import base64
import hashlib
import hmac
import secrets
import struct
import time

from cryptography.fernet import Fernet

from app.core.config import settings


def _mfa_cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)

def get_password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000)
    return f"pbkdf2_sha256$600000${salt}${digest.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt, expected = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds))
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def encrypt_mfa_secret(secret: str) -> str:
    return _mfa_cipher().encrypt(secret.encode()).decode()


def decrypt_mfa_secret(encrypted: str) -> str:
    return _mfa_cipher().decrypt(encrypted.encode()).decode()


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def verify_totp(secret: str, code: str, timestamp: int | None = None) -> bool:
    if len(code) != 6 or not code.isdecimal():
        return False
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    current = int((timestamp if timestamp is not None else time.time()) // 30)
    for offset in (-1, 0, 1):
        digest = hmac.new(key, struct.pack(">Q", current + offset), hashlib.sha1).digest()
        index = digest[-1] & 0x0F
        value = (struct.unpack(">I", digest[index:index + 4])[0] & 0x7FFFFFFF) % 1_000_000
        if hmac.compare_digest(f"{value:06d}", code):
            return True
    return False
