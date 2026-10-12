"""
Permanent admin passwords for the web admin panel.

Every admin from the list (web/admins.json / ADMIN_USERNAMES) gets a permanent
password stored as a PBKDF2-HMAC-SHA256 hash in web/admin_passwords.json:

    {
      "tehnokrat": {
        "kdf": "pbkdf2_sha256", "iterations": 240000,
        "salt_hex": "...", "hash_hex": "..."
      }
    }

The plaintext password is NEVER stored — it is generated once, shown to the
operator exactly one time (CLI or the one-time banner on the dashboard) and
then only its hash lives on disk.

Hashing uses only the standard library (hashlib.pbkdf2_hmac), so the site has
no extra dependency (no passlib/argon2 needed).

File permissions: 0o600 where the platform allows it. Add
web/admin_passwords.json to .gitignore — it is a secret file.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import string

# Password alphabet avoids characters that get mangled when read over SSH,
# typed into a chat, or printed by a terminal (no 0/O, 1/l/I, no punctuation).
_ALPHABET = "".join(c for c in (string.ascii_letters + string.digits)
                    if c not in "O0oIl1")

DEFAULT_ITERATIONS = 240_000
_KDF = "pbkdf2_sha256"


def generate_password(length: int = 16) -> str:
    """Cryptographically random, login-friendly permanent password."""
    length = max(8, int(length))
    while True:
        pwd = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        # keep it usable: needs both letters and digits
        if any(c.isalpha() for c in pwd) and any(c.isdigit() for c in pwd):
            return pwd


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS,
                  salt: bytes | None = None) -> dict:
    """Return a JSON-serialisable password-hash record."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 salt, iterations)
    return {
        "kdf": _KDF,
        "iterations": int(iterations),
        "salt_hex": salt.hex(),
        "hash_hex": digest.hex(),
    }


def verify_password(password: str, record: dict | None) -> bool:
    """Constant-time verification of `password` against a stored record."""
    if not record or not password:
        return False
    try:
        salt = bytes.fromhex(str(record["salt_hex"]))
        expected = bytes.fromhex(str(record["hash_hex"]))
        iterations = int(record.get("iterations") or DEFAULT_ITERATIONS)
    except (KeyError, TypeError, ValueError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 salt, iterations)
    return hmac.compare_digest(digest, expected)


class AdminPasswordStore:
    """Tiny JSON-backed store: username -> password-hash record."""

    def __init__(self, path: str):
        self.path = path

    # ---------- low level ----------

    def _read(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k).lstrip("@").lower(): v
                for k, v in data.items() if isinstance(v, dict)}

    def _write(self, data: dict) -> None:
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    # ---------- public API ----------

    def usernames_with_password(self) -> set[str]:
        return set(self._read())

    def has_password(self, username: str | None) -> bool:
        if not username:
            return False
        return username.lstrip("@").lower() in self._read()

    def get_record(self, username: str) -> dict | None:
        return self._read().get(username.lstrip("@").lower())

    def verify(self, username: str | None, password: str | None) -> bool:
        if not username or not password:
            return False
        return verify_password(password, self.get_record(username))

    def set_password(self, username: str, password: str) -> dict:
        key = username.lstrip("@").lower()
        record = hash_password(password)
        data = self._read()
        data[key] = record
        self._write(data)
        return record

    def generate_for(self, username: str, length: int = 16) -> str:
        """Create and store a new permanent password; return the plaintext ONCE."""
        key = username.lstrip("@").lower()
        password = generate_password(length)
        self.set_password(key, password)
        return password

    def rotate(self, username: str, length: int = 16) -> str:
        """Same as generate_for(), kept separate for readability at call sites."""
        return self.generate_for(username, length=length)

    def remove(self, username: str) -> bool:
        key = username.lstrip("@").lower()
        data = self._read()
        if key not in data:
            return False
        del data[key]
        self._write(data)
        return True

    def sync_with(self, usernames) -> tuple[list[str], list[str]]:
        """Ensure every admin in `usernames` has a password.

        Returns (generated_usernames, missing_usernames) where
        `missing_usernames` are admins that had a password but are no longer
        in the admin list (their hashes are dropped).
        """
        wanted = {str(u).lstrip("@").lower() for u in usernames if str(u).strip()}
        data = self._read()
        removed = sorted(set(data) - wanted)
        for key in removed:
            data.pop(key, None)
        added = sorted(wanted - set(data))
        if added or removed:
            self._write(data)
        return added, removed


password_store = AdminPasswordStore(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "admin_passwords.json"))
