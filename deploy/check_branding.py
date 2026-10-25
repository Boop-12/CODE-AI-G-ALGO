"""Fail if an existing protected asset is missing or changed. Does not rewrite assets."""
import hashlib
import json
from pathlib import Path


def verify(root: Path) -> list[str]:
    manifest = json.loads((root / "docs/merger/protected-assets.json").read_text(encoding="utf-8"))
    failures = []
    for name, expected in manifest.items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append(name)
    return failures


if __name__ == "__main__":
    failures = verify(Path(__file__).resolve().parents[1])
    if failures:
        raise SystemExit("Protected assets changed: " + ", ".join(failures))
    print("All protected branding assets match their original SHA-256 hashes.")
