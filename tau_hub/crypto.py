"""Symmetric encryption helpers for protecting secrets at rest.

``TauHub`` stores provider API keys in whatever database backend you choose.
Without encryption, anyone with read access to that database can read the raw
keys. This module provides :class:`SecretBox`, a small wrapper around
`Fernet <https://cryptography.io/en/latest/fernet/>`_ (AES-128-CBC + HMAC-SHA256,
authenticated encryption) that TauHub uses to encrypt API keys before writing
them and decrypt them when reading.

How it works
------------
- You pass a ``secret_key`` (any passphrase) to :class:`~tau_hub.TauHub` at
  construction time, or set the ``TAU_HUB_SECRET_KEY`` environment variable.
- The passphrase is stretched into a 32-byte Fernet key with PBKDF2-HMAC-SHA256
  (600,000 iterations, fixed versioned salt) so every service that shares the
  same passphrase derives the same key.
- Encrypted values are stored with the ``enc::v1::`` prefix so plaintext legacy
  values remain readable and encrypted values are easy to recognise.

A passphrase that is already a valid 44-character urlsafe-base64 Fernet key
(e.g. produced by :meth:`SecretBox.generate_key`) is used directly, skipping
the KDF.
"""

from __future__ import annotations

import base64
import binascii

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_CRYPTO_AVAILABLE = True


#: Prefix marking a value as encrypted by this module (version 1 format).
ENCRYPTED_PREFIX = "enc::v1::"

# Fixed, versioned salt: every service sharing the same passphrase must derive
# the same Fernet key, so the salt cannot be random per-installation. Bump the
# version suffix (and the ENCRYPTED_PREFIX) if the KDF parameters ever change.
_KDF_SALT = b"tau_hub::secretbox::v1"
_KDF_ITERATIONS = 600_000


class SecretBoxError(RuntimeError):
    """Base class for all encryption-related errors raised by tau_hub."""


class MissingSecretKeyError(SecretBoxError):
    """Raised when an encrypted value is read but no secret key was configured."""


class DecryptionError(SecretBoxError):
    """Raised when decryption fails (wrong secret key or corrupted data)."""


def is_encrypted(value: object) -> bool:
    """Return ``True`` if *value* looks like a tau_hub-encrypted string.

    Parameters
    ----------
    value:
        Any value read from a store. Only strings carrying the
        :data:`ENCRYPTED_PREFIX` are considered encrypted.
    """
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


class SecretBox:
    """Encrypts and decrypts short secrets (API keys) with a shared passphrase.

    Parameters
    ----------
    secret_key:
        A non-empty passphrase shared by every service that reads or writes
        the same hub database. May also be a raw urlsafe-base64 Fernet key
        (44 characters), in which case it is used as-is.

    Raises
    ------
    SecretBoxError
        If the optional ``cryptography`` dependency is not installed.
    ValueError
        If ``secret_key`` is empty.
    """

    def __init__(self, secret_key: str) -> None:
        self._fernet = Fernet(self._derive_key(secret_key))

    # ------------------------------------------------------------------ #
    # Key handling
    # ------------------------------------------------------------------ #

    @staticmethod
    def _derive_key(secret_key: str) -> bytes:
        """Turn an arbitrary passphrase into a valid 32-byte Fernet key.

        If the passphrase already *is* a valid Fernet key (urlsafe base64 that
        decodes to exactly 32 bytes), it is used directly. Otherwise it is
        stretched with PBKDF2-HMAC-SHA256.
        """
        try:
            raw = base64.urlsafe_b64decode(secret_key.encode("ascii"))
            if len(raw) == 32:
                return secret_key.encode("ascii")
        except (binascii.Error, UnicodeEncodeError, ValueError):
            pass
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_KDF_SALT,
            iterations=_KDF_ITERATIONS,
        )
        return base64.urlsafe_b64encode(kdf.derive(secret_key.encode("utf-8")))

    @staticmethod
    def generate_key() -> str:
        """Generate a fresh random Fernet key, suitable as a ``secret_key``.

        Returns
        -------
        str
            A 44-character urlsafe-base64 key. Store it somewhere safe (e.g. a
            secrets manager) and share it with every service using the hub.
        """
        if not _CRYPTO_AVAILABLE:
            raise SecretBoxError(
                "The 'cryptography' package is required to generate keys."
            )
        return Fernet.generate_key().decode("ascii")

    def encrypt(self, plaintext: str) -> str:
        """Encrypt *plaintext* and return a prefixed, storable token.

        Parameters
        ----------
        plaintext:
            The secret to protect (e.g. an API key). Empty strings are
            returned unchanged so "no key" stays recognisably empty.
        """
        if plaintext == "":
            return plaintext
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return ENCRYPTED_PREFIX + token.decode("ascii")

    def decrypt(self, value: str) -> str:
        """Decrypt a value previously produced by :meth:`encrypt`.

        Plaintext (non-prefixed) values are returned unchanged, which keeps
        databases written by older tau_hub versions readable.

        Raises
        ------
        DecryptionError
            If the value carries the encrypted prefix but cannot be decrypted
            (wrong secret key, or the stored data was corrupted).
        """
        if not is_encrypted(value):
            return value
        token = value[len(ENCRYPTED_PREFIX) :]
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise DecryptionError(
                "Failed to decrypt a stored secret. The secret_key passed to "
                "TauHub does not match the key used when the value was stored."
            ) from exc
