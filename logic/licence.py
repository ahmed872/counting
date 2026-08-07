"""Activation: turning an expired evaluation copy into a paid one, in place.

The whole point is that nothing is lost. Activation writes one setting. It does
not touch the database, does not reset anything, and does not ask the customer
to re-enter a single number - his books carry on exactly where they were on the
day the trial ran out.

How it works from the two sides:

  The customer    sees his device code on the expiry screen, sends it by
                  WhatsApp, gets a key back, pastes it in the box on that same
                  screen, and carries on. He never reinstalls anything.

  The seller      runs the key generator with that device code and the shared
                  secret, and sends back the key it prints.

A key is bound to one device code, so a key that leaks unlocks that one machine
and nothing else.

Honest about what this is: the app has to be able to check a key while offline,
so it carries what it needs to do that. Someone determined enough to open the
executable can extract it. This stops a customer from using the program without
paying; it does not stop a cracker, and no offline desktop program can. The
secret is at least kept out of the source: it is supplied at build time.
"""

import hashlib
import hmac
import os
import re
import uuid

from logic.trial import _read_marker, _write_marker

DEV_SECRET = "development-secret-not-for-release"


def _load_secret():
    """The real secret is written into logic/_secret.py at build time from a
    value held in the repository's Actions secrets, never in the source.

    An env var alone would not do: it is read on the machine the program runs
    on, and the customer's machine has no such variable - every build would
    quietly fall back to the placeholder, and the placeholder is published in
    this file for anyone to read. The build refuses to run without the real one.
    """
    try:
        from logic import _secret          # written by the build, git-ignored
        value = getattr(_secret, "SECRET", "").strip()
        if value:
            return value
    except ImportError:
        pass
    return os.environ.get("RESTAURANT_ERP_SECRET", DEV_SECRET)


SECRET = _load_secret()


def using_development_secret():
    """True when no real secret was baked in. The build checks this and stops:
    shipping with the placeholder means anyone reading this file can mint keys."""
    return SECRET == DEV_SECRET

_DEVICE_KEY = "device_code"
_LICENCE_KEY = "licence_key"

# I, O, 0 and 1 are left out. These codes get read off a screen and typed into a
# phone, and every one of those pairs gets confused doing it.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _encode(digest, length):
    number = int.from_bytes(digest, "big")
    out = []
    for _ in range(length):
        number, index = divmod(number, len(_ALPHABET))
        out.append(_ALPHABET[index])
    return "".join(out)


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


def key_for_device(code, secret=None):
    """The one valid key for this device code. Used by both sides: the
    generator prints it, the app compares against it."""
    digest = hmac.new(
        (secret or SECRET).encode("utf-8"),
        f"RESTAURANT-ERP-v1:{code}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _group(_encode(digest, 16))


def is_valid(code, key, secret=None):
    expected = normalise_key(key_for_device(code, secret))
    supplied = normalise_key(key)
    if not supplied:
        return False
    # Constant time, so the check cannot be probed a character at a time.
    return hmac.compare_digest(expected, supplied)


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
