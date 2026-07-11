"""Tests for tau_hub.crypto — run with: python -m unittest discover -s tests"""

import unittest

from tau_hub.crypto import (
    ENCRYPTED_PREFIX,
    DecryptionError,
    SecretBox,
    is_encrypted,
)


class SecretBoxTests(unittest.TestCase):
    def test_roundtrip(self):
        box = SecretBox("passphrase-123")
        token = box.encrypt("sk-super-secret")
        self.assertTrue(token.startswith(ENCRYPTED_PREFIX))
        self.assertNotIn("sk-super-secret", token)
        self.assertEqual(box.decrypt(token), "sk-super-secret")

    def test_same_passphrase_shares_key_across_instances(self):
        token = SecretBox("shared").encrypt("value")
        self.assertEqual(SecretBox("shared").decrypt(token), "value")

    def test_wrong_key_raises(self):
        token = SecretBox("right-key").encrypt("value")
        with self.assertRaises(DecryptionError):
            SecretBox("wrong-key").decrypt(token)

    def test_plaintext_passthrough(self):
        box = SecretBox("k")
        self.assertEqual(box.decrypt("legacy-plaintext-key"), "legacy-plaintext-key")

    def test_empty_string_stays_empty(self):
        box = SecretBox("k")
        self.assertEqual(box.encrypt(""), "")

    def test_empty_secret_key_rejected(self):
        with self.assertRaises(ValueError):
            SecretBox("")

    def test_generated_fernet_key_used_directly(self):
        key = SecretBox.generate_key()
        box = SecretBox(key)
        self.assertEqual(box.decrypt(box.encrypt("v")), "v")

    def test_is_encrypted(self):
        self.assertFalse(is_encrypted("plain"))
        self.assertFalse(is_encrypted(None))
        self.assertTrue(is_encrypted(ENCRYPTED_PREFIX + "abc"))


if __name__ == "__main__":
    unittest.main()
