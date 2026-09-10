import base64
import hashlib
import hmac
import secrets


class PasswordHasher:
    algorithm = "pbkdf2_sha256"
    iterations = 310_000

    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, self.iterations)
        return "$".join((self.algorithm, str(self.iterations), base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode()))

    def verify(self, password: str, encoded: str) -> bool:
        try:
            algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
            if algorithm != self.algorithm:
                return False
            salt = base64.urlsafe_b64decode(salt_text.encode())
            expected = base64.urlsafe_b64decode(digest_text.encode())
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
            return hmac.compare_digest(actual, expected)
        except (TypeError, ValueError):
            return False