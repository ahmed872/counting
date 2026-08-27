"""Generates the activation key for one customer's machine.

This is the seller's tool. It is never sent to a customer.

    python packaging/make_key.py ABCD2345

Or, for a goodwill trial extension instead of a full permanent key (a
customer still deciding, whose trial ran out mid-negotiation):

    python packaging/make_key.py ABCD2345 --extra-days 10

--extra-days is a cumulative total, not "add 10 more each time" - passing 10
again later is a harmless no-op, and a customer who already had 10 needs
--extra-days 20 (not 10) to get 10 more on top of that.

The secret must match the one the customer's copy was built with, either in the
RESTAURANT_ERP_SECRET environment variable or passed with --secret. Get that
wrong and the key it prints will look perfectly valid and will be rejected by
the program, so the secret is echoed back as a short fingerprint - enough to
tell two secrets apart, not enough to reveal either.
"""

import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logic.licence import extension_key_for_device, key_for_device, normalise_key


def fingerprint(secret):
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]


def main():
    parser = argparse.ArgumentParser(
        description="توليد مفتاح تفعيل، أو كود تمديد تجربة، لجهاز عميل واحد")
    parser.add_argument("device_code", help="رقم الجهاز كما يظهر في برنامج العميل")
    parser.add_argument("--secret", default=os.environ.get("RESTAURANT_ERP_SECRET"),
                        help="السر المستخدم في بناء النسخة")
    parser.add_argument("--extra-days", type=int, default=None,
                        help="بدل مفتاح تفعيل دائم، وّلد كود تمديد تجربة بإجمالي عدد الأيام هذا")
    args = parser.parse_args()

    if not args.secret:
        print("[خطأ] لم يتم تحديد السر.")
        print("مرّره بـ --secret أو بمتغيّر البيئة RESTAURANT_ERP_SECRET.")
        return 1

    code = normalise_key(args.device_code)
    if len(code) != 8:
        print(f"[خطأ] رقم الجهاز يجب أن يكون 8 خانات، وصلني {len(code)}: {code!r}")
        print("انسخه كما هو من شاشة البرنامج عند العميل.")
        return 1

    if args.extra_days is not None:
        if args.extra_days <= 0:
            print("[خطأ] عدد أيام التمديد يجب أن يكون أكبر من صفر.")
            return 1
        ext = extension_key_for_device(code, args.extra_days, secret=args.secret)
        print()
        print("=" * 46)
        print(f"  رقم الجهاز    : {code}")
        print(f"  إجمالي الأيام الإضافية : {args.extra_days} يوم")
        print(f"  كود التمديد   : {ext}")
        print("=" * 46)
        print(f"  بصمة السر     : {fingerprint(args.secret)}")
        print("  (يجب أن تطابق البصمة التي بُنيت بها نسخة العميل)")
        print()
        print("أرسل سطر «كود التمديد» فقط للعميل - يُلصق في نفس خانة مفتاح التفعيل.")
        return 0

    key = key_for_device(code, secret=args.secret)

    print()
    print("=" * 46)
    print(f"  رقم الجهاز    : {code}")
    print(f"  مفتاح التفعيل : {key}")
    print("=" * 46)
    print(f"  بصمة السر     : {fingerprint(args.secret)}")
    print("  (يجب أن تطابق البصمة التي بُنيت بها نسخة العميل)")
    print()
    print("أرسل سطر «مفتاح التفعيل» فقط للعميل.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
