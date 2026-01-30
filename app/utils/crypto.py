from __future__ import annotations

import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"ARKINV01"
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32
PBKDF2_ITERS = 200_000


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or not passphrase:
        raise ValueError("Passphrase required.")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LEN,
        salt=salt,
        iterations=PBKDF2_ITERS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_bytes(data: bytes, passphrase: str) -> bytes:
    if data is None:
        raise ValueError("Data required.")
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return MAGIC + salt + nonce + ciphertext


def decrypt_bytes(payload: bytes, passphrase: str) -> bytes:
    header_len = len(MAGIC) + SALT_LEN + NONCE_LEN
    if not payload or len(payload) < header_len + 16:
        raise ValueError("Invalid encrypted payload.")
    if payload[: len(MAGIC)] != MAGIC:
        raise ValueError("Invalid file magic.")
    offset = len(MAGIC)
    salt = payload[offset : offset + SALT_LEN]
    offset += SALT_LEN
    nonce = payload[offset : offset + NONCE_LEN]
    ciphertext = payload[offset + NONCE_LEN :]
    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)
