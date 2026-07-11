"""tau_hub — cross-service registry and persistence layer for ``tau_agent``.

Public surface:

- :class:`TauHub` — the registry (providers, agents, tools, skills, configs,
  sessions).
- :class:`HubSessionStorage` — DB-backed drop-in for Tau's JSONL session
  storage.
- :class:`Skill` — typed skill value object.
- :class:`SecretBox` and friends — API-key encryption helpers.
"""

from tau_hub.crypto import (
    DecryptionError,
    MissingSecretKeyError,
    SecretBox,
    SecretBoxError,
    is_encrypted,
)
from tau_hub.models import Skill
from tau_hub.registry import SECRET_KEY_ENV_VAR, TauHub
from tau_hub.sessions import SESSIONS_COLLECTION, HubSessionStorage

__version__ = "0.2.0"

__all__ = [
    "SECRET_KEY_ENV_VAR",
    "SESSIONS_COLLECTION",
    "DecryptionError",
    "HubSessionStorage",
    "MissingSecretKeyError",
    "SecretBox",
    "SecretBoxError",
    "Skill",
    "TauHub",
    "is_encrypted",
]
