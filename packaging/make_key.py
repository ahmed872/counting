"""Generates the activation key for one customer's machine.

This is the seller's tool. It is never sent to a customer, and it is never
bundled into the customer's build (see packaging/restaurant_erp.spec) - it is
the one place in this whole project the PRIVATE signing key is allowed to
exist at all.

    python packaging/make_key.py ABCD2345

The private key must match the public key the customer's copy was built with,
either in the RESTAURANT_ERP_PRIVATE_KEY environment variable or passed with
--private-key. Get that wrong and the key it prints will look perfectly valid
and will be rejected by the program, so the matching public key is printed
alongside it - compare that against the fingerprint the licence screen in the
customer's own build shows (Settings -> الترخيص) to confirm before sending.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from logic.licence import _encode, _group, _SIGNATURE_CHARS, normalise_key


def main():
    parser = argparse.ArgumentParser(
        description="توليد مفتاح تفعيل لجهاز عميل واحد")
    parser.add_argument("device_code", help="رقم الجهاز كما يظهر في برنامج العميل")
    parser.add_argument(
        "--private-key", default=os.environ.get("RESTAURANT_ERP_PRIVATE_KEY"),
        help="المفتاح الخاص (hex) - نفس المفتاح الذي بُني به المفتاح العام في نسخة العميل")
    args = parser.parse_args()

    if not args.private_key:
        print("[خطأ] لم يتم تحديد المفتاح الخاص.")
        print("مرّره بـ --private-key أو بمتغيّر البيئة RESTAURANT_ERP_PRIVATE_KEY.")
        return 1

    try:
        raw = bytes.fromhex(args.private_key.strip())
        if len(raw) != 32:
            raise ValueError
        private_key = Ed25519PrivateKey.from_private_bytes(raw)
    except ValueError:
        print("[خطأ] المفتاح الخاص غير صالح - يجب أن يكون 64 حرف hex (32 بايت).")
        return 1

    code = normalise_key(args.device_code)
    if len(code) != 8:
        print(f"[خطأ] رقم الجهاز يجب أن يكون 8 خانات، وصلني {len(code)}: {code!r}")
        print("انسخه كما هو من شاشة البرنامج عند العميل.")
        return 1

    signature = private_key.sign(code.encode("utf-8"))
    key = _group(_encode(signature, _SIGNATURE_CHARS), size=6)

    public_hex = private_key.public_key().public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw,
    ).hex()

    print()
    print("=" * 70)
    print(f"  رقم الجهاز       : {code}")
    print(f"  مفتاح التفعيل    : {key}")
    print("=" * 70)
    print(f"  المفتاح العام المطابق (hex) : {public_hex}")
    print("  (يجب أن يطابق القيمة المبنية بها نسخة العميل - راجع الإعدادات -> الترخيص)")
    print()
    print("أرسل سطر «مفتاح التفعيل» فقط للعميل - بالنسخ واللصق، وليس بإعادة الكتابة.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
