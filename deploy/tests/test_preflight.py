import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("preflight", Path(__file__).parents[1] / "preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)
OPENSSL = os.environ.get("GNK_TEST_OPENSSL") or shutil.which("openssl")


class EnvironmentTests(unittest.TestCase):
    def environment(self):
        return {"ENVIRONMENT": "production", "COOKIE_SECURE": "true", "SECRET_KEY": "a" * 96, "POSTGRES_PASSWORD": "b" * 64, "ALLOWED_ORIGINS": "https://gnkalgo.com,https://www.gnkalgo.com"}

    def test_valid_environment(self):
        preflight.validate_environment(self.environment())

    def test_reject_insecure_or_placeholder_environment(self):
        for key, value in [("ENVIRONMENT", "development"), ("COOKIE_SECURE", "false"), ("SECRET_KEY", "REPLACE" * 10), ("POSTGRES_PASSWORD", "REPLACE_WITH_RANDOM_HEX"), ("ALLOWED_ORIGINS", "http://gnkalgo.com")]:
            with self.subTest(key=key):
                env = self.environment()
                env[key] = value
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_environment(env)

    def test_missing_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(preflight.PreflightError, "Missing or empty"):
                preflight.validate_tls(directory, Path(directory) / "ca.pem")


@unittest.skipUnless(OPENSSL, "OpenSSL is required for certificate checks")
class CertificateTests(unittest.TestCase):
    def certificate(self, directory, name="gnkalgo.com", stem="origin"):
        directory = Path(directory)
        subprocess.run([OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "7", "-subj", f"/CN={name}", "-addext", f"subjectAltName=DNS:{name},DNS:www.{name}", "-keyout", str(directory / f"{stem}.key"), "-out", str(directory / f"{stem}.pem")], check=True, capture_output=True)

    def test_valid_chain_hostname_and_key(self):
        with tempfile.TemporaryDirectory() as directory:
            self.certificate(directory)
            preflight.validate_tls(directory, Path(directory) / "origin.pem", executable=OPENSSL)

    def test_wrong_hostname(self):
        with tempfile.TemporaryDirectory() as directory:
            self.certificate(directory, name="other.example")
            with self.assertRaisesRegex(preflight.PreflightError, "hostname"):
                preflight.validate_tls(directory, Path(directory) / "origin.pem", executable=OPENSSL)

    def test_mismatched_private_key(self):
        with tempfile.TemporaryDirectory() as directory:
            self.certificate(directory)
            self.certificate(directory, stem="other")
            shutil.copyfile(Path(directory) / "other.key", Path(directory) / "origin.key")
            with self.assertRaisesRegex(preflight.PreflightError, "does not match"):
                preflight.validate_tls(directory, Path(directory) / "origin.pem", executable=OPENSSL)

    def test_untrusted_ca(self):
        with tempfile.TemporaryDirectory() as directory:
            self.certificate(directory)
            self.certificate(directory, stem="other")
            with self.assertRaisesRegex(preflight.PreflightError, "trust"):
                preflight.validate_tls(directory, Path(directory) / "other.pem", executable=OPENSSL)


if __name__ == "__main__":
    unittest.main()
