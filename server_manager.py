"""
server_manager.py — Encrypted SSH credential store for HTopWin.

Credentials are stored as Fernet-encrypted JSON, with a key derived
from a master password via PBKDF2HMAC(SHA256, 600 000 iterations).

Files:
    ~/.htopwin/servers.salt  — 16-byte random salt (plain binary)
    ~/.htopwin/servers.enc   — Fernet-encrypted JSON blob
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# ── Storage paths ──────────────────────────────────────────────────────────────
STORE_DIR = Path.home() / ".htopwin"
STORE_PATH = STORE_DIR / "servers.enc"
SALT_PATH  = STORE_DIR / "servers.salt"


def _get_or_create_salt() -> bytes:
    """Return the on-disk salt, creating a fresh one if it does not exist."""
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    if SALT_PATH.exists():
        return SALT_PATH.read_bytes()
    salt = os.urandom(16)
    SALT_PATH.write_bytes(salt)
    return salt


def _derive_key(master_password: str, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from *master_password* and *salt*."""
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    import base64

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    raw_key = kdf.derive(master_password.encode("utf-8"))
    return base64.urlsafe_b64encode(raw_key)


# ── Public class ───────────────────────────────────────────────────────────────

class ServerStore:
    """
    Encrypted store for SSH server credentials.

    Parameters
    ----------
    master_password:
        The password used to derive the encryption key.  If the store file
        already exists and the password is wrong, ``ValueError`` is raised on
        construction.
    """

    def __init__(self, master_password: str) -> None:
        from cryptography.fernet import Fernet, InvalidToken

        salt = _get_or_create_salt()
        key  = _derive_key(master_password, salt)
        self._fernet = Fernet(key)
        self._servers: list[dict] = []

        if STORE_PATH.exists():
            ciphertext = STORE_PATH.read_bytes()
            try:
                plaintext = self._fernet.decrypt(ciphertext)
            except InvalidToken:
                raise ValueError("Wrong master password or corrupted store.")
            self._servers = json.loads(plaintext.decode("utf-8"))

    # ── Read ──────────────────────────────────────────────────────────────────

    def list_servers(self) -> list[dict]:
        """Return a shallow copy of all server dicts."""
        return list(self._servers)

    def get_server(self, name: str) -> dict | None:
        """Return the server dict whose ``name`` matches, or ``None``."""
        for s in self._servers:
            if s.get("name") == name:
                return s
        return None

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_server(self, server: dict) -> None:
        """
        Append *server* to the store and persist it.

        Raises
        ------
        ValueError
            If a server with the same name already exists.
        """
        name = server.get("name", "")
        if not name:
            raise ValueError("Server must have a non-empty 'name'.")
        if self.get_server(name) is not None:
            raise ValueError(f"A server named '{name}' already exists.")
        # Normalise port
        server.setdefault("port", 22)
        try:
            server["port"] = int(server["port"])
        except (TypeError, ValueError):
            server["port"] = 22
        self._servers.append(server)
        self.save()

    def update_server(self, name: str, server: dict) -> None:
        """Replace the entry whose name is *name* with *server* and persist."""
        for i, s in enumerate(self._servers):
            if s.get("name") == name:
                # Normalise port
                try:
                    server["port"] = int(server.get("port", 22))
                except (TypeError, ValueError):
                    server["port"] = 22
                self._servers[i] = server
                self.save()
                return
        raise ValueError(f"No server named '{name}' found.")

    def remove_server(self, name: str) -> None:
        """Delete the server with *name* from the store and persist."""
        before = len(self._servers)
        self._servers = [s for s in self._servers if s.get("name") != name]
        if len(self._servers) == before:
            raise ValueError(f"No server named '{name}' found.")
        self.save()

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self) -> None:
        """Encrypt the current server list and write it to disk."""
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        plaintext  = json.dumps(self._servers, indent=2).encode("utf-8")
        ciphertext = self._fernet.encrypt(plaintext)
        STORE_PATH.write_bytes(ciphertext)
