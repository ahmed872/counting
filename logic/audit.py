"""Audit trail: who did what, and when.

One shared writer so every caller logs the same shape of row instead of
each screen inventing its own. Deliberately fire-and-forget: a logging
failure never blocks the real business operation it is describing - an
audit row that fails to write is a smaller problem than a real sale or
payroll run that gets rolled back because the *logging* broke. Never pass
a password or password hash as before/after data.

Read-only from the app's own side - nothing in the UI can edit or delete a
row here, because an audit trail that can be quietly edited from inside
the same program it is meant to be watching is not an audit trail.
"""

import json


class AuditLogger:
    def __init__(self, db):
        self.db = db

    def log(self, action, user_id=None, username=None, entity_type=None,
            entity_id=None, before=None, after=None, branch_id=None):
        try:
            self.db.execute_query(
                """INSERT INTO audit_log
                   (user_id, username, action, entity_type, entity_id,
                    before_data, after_data, branch_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, username, action, entity_type, entity_id,
                 json.dumps(before, ensure_ascii=False, default=str) if before is not None else None,
                 json.dumps(after, ensure_ascii=False, default=str) if after is not None else None,
                 branch_id),
            )
        except Exception:
            pass

    def recent(self, limit=500):
        return self.db.fetch_all(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        )
