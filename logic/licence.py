"""Activation: turning an expired evaluation copy into a paid one, in place.

The whole point is that nothing is lost. Activation writes one setting. It does
not touch the database, does not reset anything, and does not ask the customer
to re-enter a single number - his books carry on exactly where they were on the
day the trial ran out.

How it works from the two sides:

  The customer    sees his device code on the expiry screen, sends it by
                  WhatsApp, gets a key back, pastes it in the box on that same
                  screen, and carries on. He never reinstalls anything.

  The seller      runs the key generator (packaging/make_key.py, or the
                  "توليد مفتاح تفعيل" GitHub Actions workflow) with that device
                  code and the PRIVATE signing key, and sends back the key it
                  prints.

A key is bound to one device code, so a key that leaks unlocks that one machine
and nothing else.

P1-4: this used to be a single shared HMAC secret, baked into the shipped
executable, that both signed keys and verified them - anyone who extracted it
from the .exe could mint a valid key for ANY device, not just their own. Now an
Ed25519 keypair: the PRIVATE key never leaves the seller's side (it lives only
in packaging/make_key.py's caller, typically a GitHub Actions secret used only
by the key-generator workflow); the shipped app carries only the PUBLIC key,
which can verify a signature but cannot produce a new one. Extracting the
public key from the executable, same as before, only lets someone confirm a
licence is genuine - it does not let them forge one.

The real signature is 64 bytes, and there is no way to make an asymmetric
signature shorter without weakening it - "do not invent custom cryptography"
applies as much to shrinking a signature as to writing a new one. The
resulting key is a single long code rather than the old short one; it is still
meant to be copy-pasted through WhatsApp, never retyped by hand.

Honest about what this is: the app has to be able to check a key while
offline, so it carries the public key needed to do that. That is not a
weakness particular to this design - it is true of every offline licence
scheme, asymmetric or not. The difference this change makes is specifically
that whatever the app carries can no longer mint new keys.
"""

import re
import os
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from logic.trial import _read_marker, _write_marker

# A published keypair used only for local development and the test suite -
# safe to commit because it is explicitly not the pair any real customer's
# copy is built with. The matching private key is published too, right next
# to it, as tests/test_app.py's _DEV_PRIVATE_KEY_HEX - so whoever holds it
# can only forge licences that verify against THIS public key; a real build
# swaps in a different public key entirely (see _load_public_key_hex), and
# using_development_key() below exists specifically to refuse shipping a
# build that forgot to.
DEV_PUBLIC_KEY_HEX = "da4b822c4ac06d99315f5a088f0106b0ccfef443b52246ed184e0448db734516"


def _load_public_key_hex():
    """The real public key is written into logic/_licence_key.py at build
    time from a value held in the repository's Actions secrets, never in the
    source. Baking in only the PUBLIC half is the whole point of this scheme
    (see packaging/make_key.py for where the private half actually lives) -
    there is nothing wrong with this value leaking, which is exactly why it
    is fine to fall back to an environment variable or the published dev key
    when no build-time file is present.
    """
    try:
        from logic import _licence_key      # written by the build, git-ignored
        value = getattr(_licence_key, "PUBLIC_KEY_HEX", "").strip()
        if value:
            return value
    except ImportError:
        pass
    return os.environ.get("RESTAURANT_ERP_PUBLIC_KEY", DEV_PUBLIC_KEY_HEX)


PUBLIC_KEY_HEX = _load_public_key_hex()


def using_development_key():
    """True when no real public key was baked in. The build checks this and
    stops: shipping with the dev key means a licence signed with the
    published dev private key - available to anyone who reads this file's
    history - would be accepted as genuine."""
    return PUBLIC_KEY_HEX == DEV_PUBLIC_KEY_HEX


_DEVICE_KEY = "device_code"
_LICENCE_KEY = "licence_key"

# I, O, 0 and 1 are left out. These codes get read off a screen and typed into a
# phone, and every one of those pairs gets confused doing it.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# An Ed25519 signature is exactly 64 bytes. 103 base-33 "digits" is the
# smallest number that can hold every possible 64-byte value without losing
# any of it (33**103 > 256**64) - fewer would silently truncate some
# signatures, which would make some genuine keys unverifiable rather than
# making anything more compact in a way that matters.
_SIGNATURE_BYTES = 64
_SIGNATURE_CHARS = 103


def _encode(digest, length):
    number = int.from_bytes(digest, "big")
    out = []
    for _ in range(length):
        number, index = divmod(number, len(_ALPHABET))
        out.append(_ALPHABET[index])
    return "".join(out)


def _decode(text, byte_length):
    """Reverse of _encode(): that function peels off characters least-
    significant-first via repeated divmod, so rebuilding the original value
    walks the string in reverse and multiplies up one base-33 digit at a
    time. Raises ValueError on any character outside _ALPHABET, exactly
    like the int()/float() built-ins callers already expect to catch."""
    number = 0
    for ch in reversed(text):
        number = number * len(_ALPHABET) + _ALPHABET.index(ch)
    return number.to_bytes(byte_length, "big")


def _group(text, size=4):
    return "-".join(text[i:i + size] for i in range(0, len(text), size))


def device_code(db=None):
    """A short, stable identifier for this installation.

    Deliberately not a hardware fingerprint. Fingerprints look rigorous and then
    change when someone swaps a network card or docks a laptop, at which point a
    paying customer's program locks him out and it is the seller's evening that
    gets ruined. This is a random value generated once and kept in the same two
    places the trial state lives, so it survives everything short of wiping both.
    """
    marker = _read_marker()
    existing = marker.get("device")
    if not existing and db is not None:
        existing = db.get_setting(_DEVICE_KEY)

    if not existing:
        existing = _encode(uuid.uuid4().bytes, 8)

    marker["device"] = existing
    _write_marker(marker)
    if db is not None and db.get_setting(_DEVICE_KEY) != existing:
        db.set_setting(_DEVICE_KEY, existing)
    return existing


def normalise_key(text):
    """Accepts the key however it comes back - lower case, spaces, no dashes,
    pasted out of WhatsApp with stray characters around it."""
    return re.sub(r"[^A-Za-z0-9]", "", str(text or "")).upper()


def is_valid(code, key, public_key_hex=None):
    """Verifies a signature against the device code, using only the public
    key - nothing here can produce a new valid key, only check one someone
    else (packaging/make_key.py, holding the private key) already produced."""
    cleaned = normalise_key(key)
    if len(cleaned) != _SIGNATURE_CHARS:
        return False
    try:
        signature = _decode(cleaned, _SIGNATURE_BYTES)
        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(public_key_hex or PUBLIC_KEY_HEX))
        public_key.verify(signature, code.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError):
        # ValueError covers a malformed key (bad characters already handled
        # by the length check, but also a public_key_hex that is not valid
        # hex or not 32 bytes) as well as InvalidSignature's own cousin
        # exceptions some backends raise for a garbled signature.
        return False


def is_activated(db):
    stored = db.get_setting(_LICENCE_KEY) or _read_marker().get("licence")
    if not stored:
        return False
    return is_valid(device_code(db), stored)


def activate(db, key):
    """Returns True if the key fits this device. Stores it in both places so
    that restoring an old backup does not deactivate a paid copy."""
    code = device_code(db)
    if not is_valid(code, key):
        return False
    cleaned = normalise_key(key)
    db.set_setting(_LICENCE_KEY, cleaned)
    marker = _read_marker()
    marker["licence"] = cleaned
    _write_marker(marker)
    return True
