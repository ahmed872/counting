"""Audit trail for sensitive actions (P1-1).

One shared writer so every caller logs the same shape of row instead of
each screen inventing its own. Deliberately fire-and-forget in the sense
that a logging failure never blocks the real business operation it is
describing - an audit row that fails to write is a smaller problem than a
real sale/payroll/backup that gets rolled back because the *logging*
broke. Never pass a password or password hash as before/after data.
"""

import json


class AuditLogger:
    def __init__(self, db):
        self.db = db

    def log(self, action, user_id=None, username=None, entity_type=None,
             entity_id=None, before=None, after=None, branch_id=None):
        self.db.execute_query(
            """INSERT INTO audit_log
               (user_id, username, action, entity_type, entity_id, before_data, after_data, branch_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, username, action, entity_type, entity_id,
             json.dumps(before, ensure_ascii=False, default=str) if before is not None else None,
             json.dumps(after, ensure_ascii=False, default=str) if after is not None else None,
             branch_id),
        )

    def recent(self, limit=500):
        return self.db.fetch_all(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        )
