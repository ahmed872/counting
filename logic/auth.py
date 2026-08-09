"""Login and per-role permissions.

Four roles: admin (everything, including managing other users), manager
(day-to-day operations - sales, purchases, HR, customers, suppliers,
accounting, reports - but no settings or user management), cashier (just
the daily sales-entry work - المبيعات اليومية, لوحة التحكم, العملاء - for
someone who should not see payroll, purchasing, or the books at all), and
viewer (read-only everywhere). Stored in English for the same reason every
other status code in this app is - see ui/labels.py - only ever translated
where it is actually shown to someone.

Passwords are never stored in the clear, only a salted PBKDF2 hash - the
same standard library primitives already used for the activation key in
logic/licence.py, just applied the way passwords specifically need to be
(salted, deliberately slow, one-way).
"""

import hashlib
import hmac
import os

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_CASHIER = "cashier"
ROLE_VIEWER = "viewer"

ROLE_LABELS = {
    ROLE_ADMIN: "أدمن",
    ROLE_MANAGER: "مسئول",
    ROLE_CASHIER: "كاشير",
    ROLE_VIEWER: "مراقب",
}

# Roles a person can be given from inside the app. Not admin - that would let
# any manager mint themselves a second admin account; the two admin seats are
# fixed at setup time (see ensure_default_admins) and stay that way.
ASSIGNABLE_ROLES = (ROLE_MANAGER, ROLE_CASHIER, ROLE_VIEWER)

_ITERATIONS = 200_000

# Seeded once, the very first time the users table is empty - one seat for
# whoever supports the program, one for the restaurant's own owner. Both are
# forced to change this password the first time they log in, so it only ever
# works as a one-time key to get in the door.
_DEFAULT_SEED_PASSWORD = "Erp@2026"


def _hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return digest.hex(), salt.hex()


def _verify_password(password, password_hash, salt_hex):
    salt = bytes.fromhex(salt_hex)
    digest, _ = _hash_password(password, salt)
    return hmac.compare_digest(digest, password_hash)


class AuthLogic:
    def __init__(self, db):
        self.db = db

    def ensure_default_admins(self):
        """Seeds the two admin seats the first time the users table is
        empty. Never runs again once at least one user exists, so it cannot
        reset anyone's account later - only ever fires on a brand new or
        freshly-upgraded database that has never had a user in it."""
        existing = self.db.fetch_one("SELECT COUNT(*) c FROM users")["c"]
        if existing:
            return
        for username, display_name in (
            ("ahmed_admin", "أحمد (الدعم الفني)"),
            ("admin", "صاحب المطعم"),
        ):
            self.create_user(
                username, _DEFAULT_SEED_PASSWORD, ROLE_ADMIN, display_name,
                must_change_password=True,
            )

    def authenticate(self, username, password):
        """Returns the user row (without the hash/salt) on success, or None -
        wrong password and unknown/deactivated username look identical from
        the outside, so a login attempt cannot be used to probe which
        usernames exist."""
        username = (username or "").strip().lower()
        row = self.db.fetch_one(
            "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
        )
        if row is None:
            return None
        if not _verify_password(password or "", row["password_hash"], row["password_salt"]):
            return None
        return self._public(row)

    def create_user(self, username, password, role, display_name=None,
                     must_change_password=False, branch_id=None):
        username = (username or "").strip().lower()
        if not username:
            raise ValueError("اسم المستخدم مطلوب")
        if not password:
            raise ValueError("كلمة المرور مطلوبة")
        if role not in (ROLE_ADMIN, ROLE_MANAGER, ROLE_CASHIER, ROLE_VIEWER):
            raise ValueError("صلاحية غير معروفة")
        # A cashier's whole job is scoped to one branch (see
        # apply_role_restrictions in main_window.py) - an account with no
        # branch to lock to would default to seeing every branch, exactly
        # the access a cashier is not supposed to have.
        if role == ROLE_CASHIER and not branch_id:
            raise ValueError("الكاشير لازم يتربط بفرع واحد")
        if self.db.fetch_one("SELECT id FROM users WHERE username = ?", (username,)):
            raise ValueError(f"اسم المستخدم «{username}» مستخدم بالفعل")
        password_hash, salt = _hash_password(password)
        self.db.execute_query(
            """INSERT INTO users
               (username, password_hash, password_salt, role, branch_id, display_name,
                must_change_password)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (username, password_hash, salt, role, branch_id if role == ROLE_CASHIER else None,
             display_name or username, 1 if must_change_password else 0),
        )
        return self.db.fetch_one("SELECT id FROM users WHERE username = ?", (username,))["id"]

    def list_users(self):
        rows = self.db.fetch_all(
            "SELECT u.id, u.username, u.role, u.branch_id, b.name AS branch_name, "
            "       u.display_name, u.must_change_password, u.is_active, u.created_at "
            "FROM users u LEFT JOIN branches b ON b.id = u.branch_id "
            "ORDER BY u.role, u.username"
        )
        return [dict(r) for r in rows]

    def set_password(self, user_id, new_password, must_change_password=False):
        if not new_password:
            raise ValueError("كلمة المرور مطلوبة")
        password_hash, salt = _hash_password(new_password)
        self.db.execute_query(
            "UPDATE users SET password_hash = ?, password_salt = ?, must_change_password = ? "
            "WHERE id = ?",
            (password_hash, salt, 1 if must_change_password else 0, user_id),
        )

    def change_own_password(self, user_id, old_password, new_password):
        row = self.db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        if row is None or not _verify_password(old_password or "", row["password_hash"], row["password_salt"]):
            raise ValueError("كلمة المرور الحالية غير صحيحة")
        self.set_password(user_id, new_password, must_change_password=False)

    def set_active(self, user_id, is_active):
        self.db.execute_query(
            "UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id)
        )

    def _public(self, row):
        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "branch_id": row["branch_id"],
            "display_name": row["display_name"],
            "must_change_password": bool(row["must_change_password"]),
        }
