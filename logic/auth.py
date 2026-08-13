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
from datetime import datetime, timedelta

from logic.audit import AuditLogger

# P1-6: after this many consecutive failures, the account is locked out for
# this long. Deliberately modest, not a hard security boundary - this is a
# single offline desktop program with no network exposure to brute-force
# over, so the actual threat this defends against is someone with physical
# access to the machine trying passwords by hand while its owner is away
# from the desk, not an automated attack. Five wrong guesses is a real typo
# tolerance; a fifteen-minute wait after that is a real deterrent to guessing
# without locking a legitimate owner out for the rest of the day.
_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15

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
        self.audit = AuditLogger(db)

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

    def _now_iso(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def lockout_status(self, username):
        """Minutes remaining if `username` is currently locked out, or None -
        a separate query from authenticate() itself so the login screen can
        show a specific "too many attempts, wait N minutes" message without
        authenticate()'s own return value revealing whether a lockout is why
        it failed (unknown username, wrong password, and a lockout on a
        username that was never real all still return the same None from
        authenticate - see there)."""
        username = (username or "").strip().lower()
        row = self.db.fetch_one(
            "SELECT locked_until FROM login_lockouts WHERE username = ?", (username,))
        if not row or not row["locked_until"] or row["locked_until"] <= self._now_iso():
            return None
        remaining = datetime.strptime(row["locked_until"], "%Y-%m-%d %H:%M:%S") - datetime.now()
        return max(1, int(remaining.total_seconds() // 60) + 1)

    def _register_failed_login(self, username):
        row = self.db.fetch_one(
            "SELECT failed_count FROM login_lockouts WHERE username = ?", (username,))
        count = (row["failed_count"] if row else 0) + 1
        locked_until = None
        if count >= _MAX_FAILED_ATTEMPTS:
            locked_until = (datetime.now() + timedelta(minutes=_LOCKOUT_MINUTES)).strftime(
                "%Y-%m-%d %H:%M:%S")
            count = 0   # the next window after the lockout expires starts clean
        self.db.execute_query(
            "INSERT INTO login_lockouts (username, failed_count, locked_until) VALUES (?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET failed_count = excluded.failed_count, "
            "locked_until = excluded.locked_until",
            (username, count, locked_until),
        )
        if locked_until:
            self.audit.log("login_lockout_triggered", username=username)

    def _clear_failed_logins(self, username):
        self.db.execute_query("DELETE FROM login_lockouts WHERE username = ?", (username,))

    def authenticate(self, username, password):
        """Returns the user row (without the hash/salt) on success, or None -
        wrong password, unknown/deactivated username, and a lockout all look
        identical from the outside (see lockout_status for how the login
        screen still shows something more specific), so a login attempt
        cannot be used to probe which usernames exist or which are locked
        out. Every attempt is audit-logged here, in the one place every
        login in the app actually goes through, rather than depending on
        the login screen to remember to log it - success and failure alike,
        and never the password itself."""
        username = (username or "").strip().lower()

        if self.lockout_status(username) is not None:
            self.audit.log("login_blocked", username=username)
            return None

        row = self.db.fetch_one(
            "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
        )
        if row is None:
            self._register_failed_login(username)
            self.audit.log("login_failed", username=username)
            return None
        if not _verify_password(password or "", row["password_hash"], row["password_salt"]):
            self._register_failed_login(username)
            self.audit.log("login_failed", user_id=row["id"], username=username)
            return None
        self._clear_failed_logins(username)
        self.audit.log("login_success", user_id=row["id"], username=username)
        return self._public(row)

    def _require_admin(self, actor_role, action):
        """P1-6: enforced here, in the logic layer, not only by the
        Settings screen hiding the user-management box from anyone but an
        admin. A UI check can be skipped by a future screen that forgets
        to add it, or bypassed by anything that calls this method
        directly; this cannot. actor_role=None (the default) skips the
        check entirely - reserved for callers with no real "current user"
        of their own, such as ensure_default_admins() seeding the two
        admin seats on a brand new database before anyone has logged in
        at all."""
        if actor_role is not None and actor_role != ROLE_ADMIN:
            raise PermissionError(f"هذه العملية للأدمن فقط: {action}")

    def create_user(self, username, password, role, display_name=None,
                     must_change_password=False, branch_id=None,
                     actor_user_id=None, actor_username=None, actor_role=None):
        self._require_admin(actor_role, "إنشاء مستخدم")
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
        new_id = self.db.fetch_one("SELECT id FROM users WHERE username = ?", (username,))["id"]
        self.audit.log("user_created", user_id=actor_user_id, username=actor_username,
                        entity_type="user", entity_id=new_id,
                        after={"username": username, "role": role, "branch_id": branch_id})
        return new_id

    def list_users(self):
        rows = self.db.fetch_all(
            "SELECT u.id, u.username, u.role, u.branch_id, b.name AS branch_name, "
            "       u.display_name, u.must_change_password, u.is_active, u.created_at "
            "FROM users u LEFT JOIN branches b ON b.id = u.branch_id "
            "ORDER BY u.role, u.username"
        )
        return [dict(r) for r in rows]

    def set_password(self, user_id, new_password, must_change_password=False,
                      actor_user_id=None, actor_username=None, actor_role=None):
        self._require_admin(actor_role, "إعادة تعيين كلمة مرور مستخدم آخر")
        if not new_password:
            raise ValueError("كلمة المرور مطلوبة")
        password_hash, salt = _hash_password(new_password)
        self.db.execute_query(
            "UPDATE users SET password_hash = ?, password_salt = ?, must_change_password = ? "
            "WHERE id = ?",
            (password_hash, salt, 1 if must_change_password else 0, user_id),
        )
        # Never the password itself - only the fact that it changed and who
        # changed it.
        self.audit.log("password_changed", user_id=actor_user_id, username=actor_username,
                        entity_type="user", entity_id=user_id)

    def change_own_password(self, user_id, old_password, new_password):
        row = self.db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        if row is None or not _verify_password(old_password or "", row["password_hash"], row["password_salt"]):
            raise ValueError("كلمة المرور الحالية غير صحيحة")
        self.set_password(user_id, new_password, must_change_password=False,
                           actor_user_id=user_id, actor_username=row["username"])

    def set_active(self, user_id, is_active, actor_user_id=None, actor_username=None, actor_role=None):
        self._require_admin(actor_role, "تفعيل أو تعطيل مستخدم")
        self.db.execute_query(
            "UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id)
        )
        self.audit.log("user_activated" if is_active else "user_deactivated",
                        user_id=actor_user_id, username=actor_username,
                        entity_type="user", entity_id=user_id)

    def _public(self, row):
        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "branch_id": row["branch_id"],
            "display_name": row["display_name"],
            "must_change_password": bool(row["must_change_password"]),
        }
