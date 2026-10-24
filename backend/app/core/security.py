import hashlib
import hmac
import secrets

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
