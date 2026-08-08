import calendar
from datetime import datetime, timedelta

DOC_LABELS = {
    'iqama': 'إقامة',
    'passport': 'جواز سفر',
    'work_permit': 'تصريح عمل',
    'work_card': 'كرت عمل',
}


class HRLogic:
    def __init__(self, db_manager):
        self.db = db_manager

    def calculate_daily_rate(self, base_salary, allowances):
        return (base_salary + allowances) / 30

    def get_document_alerts(self, days=30):
        today = datetime.now().date()
        alert_date = today + timedelta(days=days)

        query = """
            SELECT id, name, 'إقامة' as doc_type, iqama_expiry as expiry_date FROM employees WHERE is_active = 1 AND iqama_expiry IS NOT NULL AND iqama_expiry <= ?
            UNION
            SELECT id, name, 'جواز سفر' as doc_type, passport_expiry as expiry_date FROM employees WHERE is_active = 1 AND passport_expiry IS NOT NULL AND passport_expiry <= ?
            UNION
            SELECT id, name, 'تصريح عمل' as doc_type, work_permit_expiry as expiry_date FROM employees WHERE is_active = 1 AND work_permit_expiry IS NOT NULL AND work_permit_expiry <= ?
            UNION
            SELECT id, name, 'كرت عمل' as doc_type, work_card_expiry as expiry_date FROM employees WHERE is_active = 1 AND work_card_expiry IS NOT NULL AND work_card_expiry <= ?
            ORDER BY expiry_date
        """
        return self.db.fetch_all(query, (alert_date, alert_date, alert_date, alert_date))

    def record_attendance(self, employee_id, date, status):
        """One record per employee per day: re-recording the same day corrects it
        rather than adding a second row. Stacking rows meant an absence saved
        twice was deducted from the employee's salary twice."""
        self.db.execute_query(
            """INSERT INTO attendance (employee_id, date, status) VALUES (?, ?, ?)
               ON CONFLICT(employee_id, date) DO UPDATE SET status = excluded.status""",
            (employee_id, date, status)
        )

    def get_attendance(self, employee_id, date):
        return self.db.fetch_one(
            "SELECT * FROM attendance WHERE employee_id = ? AND date = ?",
            (employee_id, date)
        )

    def add_deduction(self, employee_id, date, entry_type, amount, notes=""):
        """entry_type: 'Deduction' (penalty), 'Advance' (سلفة), or 'Bonus'."""
        self.db.execute_query(
            "INSERT INTO employee_deductions (employee_id, date, type, amount, notes) VALUES (?, ?, ?, ?, ?)",
            (employee_id, date, entry_type, amount, notes)
        )

    def get_outstanding_advances_total(self):
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(amount), 0) as total FROM employee_deductions WHERE type = 'Advance' AND settled_run_id IS NULL"
        )
        return row['total'] or 0

    def get_active_employees_summary(self):
        """Who is currently on payroll and what they cost - for the printed
        report, not tied to any one month's attendance/deductions."""
        rows = self.db.fetch_all(
            """SELECT e.name, e.job_title, e.base_salary, e.allowances, b.name as branch_name
               FROM employees e
               LEFT JOIN branches b ON b.id = e.branch_id
               WHERE e.is_active = 1
               ORDER BY e.name"""
        )
        return [{'name': r['name'], 'job_title': r['job_title'] or '', 'branch_name': r['branch_name'] or '',
                'base_salary': r['base_salary'] or 0, 'allowances': r['allowances'] or 0,
                'gross': (r['base_salary'] or 0) + (r['allowances'] or 0)} for r in rows]

    def get_monthly_payroll(self, month, year):
        period_end = f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
        query = """
            SELECT
                e.id,
                e.name,
                e.job_title,
                e.base_salary,
                e.allowances,
                b.name as branch_name,
                COALESCE(SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END), 0) as absent_days,
                COALESCE(SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END), 0) as present_days
            FROM employees e
            LEFT JOIN branches b ON e.branch_id = b.id
            LEFT JOIN attendance a ON a.employee_id = e.id
                AND strftime('%m', a.date) = ?
                AND strftime('%Y', a.date) = ?
            WHERE e.is_active = 1 OR e.terminated_date >= ?
            GROUP BY e.id
            ORDER BY e.name
        """
        month_str = f"{month:02d}"
        year_str = str(year)
        period_start = f"{year:04d}-{month:02d}-01"
        # A terminated employee still belongs in any period they were
        # actually employed during - only periods entirely after their last
        # working day should drop them. is_active alone cannot tell "gone
        # before this month" from "gone during/after it".
        rows = self.db.fetch_all(query, (month_str, year_str, period_start))
        payroll = []
        for row in rows:
            gross = (row['base_salary'] or 0) + (row['allowances'] or 0)
            daily_rate = self.calculate_daily_rate(row['base_salary'] or 0, row['allowances'] or 0)
            absence_deduction = daily_rate * (row['absent_days'] or 0)

            period_entries = self.db.fetch_all(
                """SELECT type, COALESCE(SUM(amount), 0) as total FROM employee_deductions
                   WHERE employee_id = ? AND strftime('%m', date) = ? AND strftime('%Y', date) = ?
                   GROUP BY type""",
                (row['id'], month_str, year_str)
            )
            other_deductions = 0
            bonuses = 0
            for e in period_entries:
                if e['type'] == 'Deduction':
                    other_deductions = e['total'] or 0
                elif e['type'] == 'Bonus':
                    bonuses = e['total'] or 0

            # Only advances granted on or before this period, not the whole
            # outstanding balance regardless of date - an advance recorded in
            # August has no business being recovered out of July's payroll,
            # which is what a plain "settled_run_id IS NULL" would do.
            outstanding_advances = self.db.fetch_one(
                """SELECT COALESCE(SUM(amount - COALESCE(amount_recovered, 0)), 0) as total
                   FROM employee_deductions
                   WHERE employee_id = ? AND type = 'Advance' AND settled_run_id IS NULL
                     AND date(date) <= date(?)""",
                (row['id'], period_end)
            )['total'] or 0

            # A deduction cannot exceed what there is to deduct from: 31
            # attendance rows in a 31-day month otherwise cost more than the
            # whole salary, and an advance bigger than one month's pay used to
            # push net_salary negative - paying the employee to have been
            # advanced money. Recovery here never exceeds what is actually
            # available, and whatever is left of the advance simply carries
            # over to be recovered from a later month.
            expense_amount = max(0.0, gross - absence_deduction - other_deductions + bonuses)
            advances_recovered = min(outstanding_advances, expense_amount)
            net_salary = expense_amount - advances_recovered

            payroll.append({
                'id': row['id'],
                'name': row['name'],
                'job_title': row['job_title'],
                'branch_name': row['branch_name'],
                'gross_salary': gross,
                'absent_days': row['absent_days'] or 0,
                'present_days': row['present_days'] or 0,
                'daily_rate': daily_rate,
                'absence_deduction': absence_deduction,
                'other_deductions': other_deductions,
                'bonuses': bonuses,
                'advances_recovered': advances_recovered,
                'advances_outstanding_after': outstanding_advances - advances_recovered,
                'expense_amount': expense_amount,
                'net_salary': net_salary,
            })
        return payroll

    def is_payroll_posted(self, month, year):
        return self.db.fetch_one(
            "SELECT id FROM payroll_runs WHERE month = ? AND year = ?", (month, year)
        ) is not None

    def get_posted_payroll(self, month, year):
        """The frozen record of what was actually posted to the journal for
        this month, not a live recalculation. Editing attendance or a
        deduction after posting must not make the screen disagree with the
        accounting entry that has already gone out - the entry is fixed, so
        what is shown for that month must be too."""
        rows = self.db.fetch_all(
            """SELECT i.*, e.name, e.job_title, b.name as branch_name
               FROM payroll_run_items i
               JOIN payroll_runs r ON r.id = i.run_id
               JOIN employees e ON e.id = i.employee_id
               LEFT JOIN branches b ON b.id = e.branch_id
               WHERE r.month = ? AND r.year = ?
               ORDER BY e.name""",
            (month, year)
        )
        return [{
            'id': row['employee_id'],
            'name': row['name'],
            'job_title': row['job_title'],
            'branch_name': row['branch_name'],
            'gross_salary': row['gross_salary'],
            'absent_days': row['absent_days'] or 0,
            'present_days': row['present_days'] or 0,
            'absence_deduction': row['absence_deduction'],
            'other_deductions': row['other_deductions'],
            'bonuses': row['bonuses'],
            'advances_recovered': row['advances_recovered'],
            'net_salary': row['net_salary'],
        } for row in rows]

    def post_payroll(self, month, year, paid_now=True):
        """Posts the month's payroll to the accounting journal:
        Debit Salaries Expense (5100) for gross-less-deductions-plus-bonuses,
        Credit Employee Advances (1300) for any advances recovered this run,
        Credit Cash (1000) for the actual net amount paid out - or, if
        paid_now is False, Credit Accrued Wages Payable (2200) instead,
        because the expense was earned this month but the cash has not
        actually left yet. Marks unsettled advances as settled so they are
        not deducted twice."""
        if self.is_payroll_posted(month, year):
            raise ValueError("تم ترحيل رواتب هذا الشهر مسبقاً")

        payroll = self.get_monthly_payroll(month, year)
        total_expense = sum(p['expense_amount'] for p in payroll)
        total_net_paid = sum(p['net_salary'] for p in payroll)
        total_advances_recovered = sum(p['advances_recovered'] for p in payroll)

        if not payroll or total_expense == 0:
            raise ValueError("لا يوجد بيانات رواتب لهذا الشهر")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run_id = self.db.insert_and_return_id(
            """INSERT INTO payroll_runs
               (month, year, posted_at, total_expense, total_net_paid, total_advances_recovered, paid_now)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (month, year, timestamp, total_expense, total_net_paid, total_advances_recovered, int(paid_now))
        )

        for p in payroll:
            self.db.execute_query(
                """INSERT INTO payroll_run_items
                   (run_id, employee_id, gross_salary, absence_deduction, other_deductions, bonuses,
                    advances_recovered, net_salary, absent_days, present_days)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, p['id'], p['gross_salary'], p['absence_deduction'], p['other_deductions'],
                 p['bonuses'], p['advances_recovered'], p['net_salary'], p['absent_days'], p['present_days'])
            )
            # Apply the recovered amount to the oldest outstanding advances
            # first, and only as far as it actually reaches. A row is marked
            # settled only once it has been recovered in full; a row that is
            # only partly covered this run keeps its remaining balance
            # outstanding for the next one, instead of being wiped either way.
            remaining = p['advances_recovered']
            if remaining > 0:
                rows = self.db.fetch_all(
                    """SELECT id, amount, COALESCE(amount_recovered, 0) as recovered
                       FROM employee_deductions
                       WHERE employee_id = ? AND type = 'Advance' AND settled_run_id IS NULL
                         AND date(date) <= date(?)
                       ORDER BY date, id""",
                    (p['id'], f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}")
                )
                for adv in rows:
                    if remaining <= 0.005:
                        break
                    owed = adv['amount'] - adv['recovered']
                    applied = min(owed, remaining)
                    new_recovered = adv['recovered'] + applied
                    fully_settled = new_recovered >= adv['amount'] - 0.005
                    self.db.execute_query(
                        "UPDATE employee_deductions SET amount_recovered = ?, "
                        "settled_run_id = ? WHERE id = ?",
                        (new_recovered, run_id if fully_settled else None, adv['id'])
                    )
                    remaining -= applied

        journal_items = [{'account_code': '5100', 'debit': total_expense, 'credit': 0}]
        if total_advances_recovered:
            journal_items.append({'account_code': '1300', 'debit': 0, 'credit': total_advances_recovered})
        credit_account = '1000' if paid_now else '2200'
        journal_items.append({'account_code': credit_account, 'debit': 0, 'credit': total_net_paid})

        description = (f"صرف رواتب شهر {month:02d}/{year}" if paid_now
                       else f"استحقاق رواتب شهر {month:02d}/{year} (لم تُدفع بعد)")
        self.db.add_journal_entry(timestamp, description, None, journal_items)
        return run_id

    def grant_advance(self, employee_id, date, amount, notes=""):
        """Cash advance paid out to an employee ahead of payroll; recovered automatically in the next run."""
        self.add_deduction(employee_id, date, 'Advance', amount, notes)
        journal_items = [
            {'account_code': '1300', 'debit': amount, 'credit': 0},
            {'account_code': '1000', 'debit': 0, 'credit': amount},
        ]
        self.db.add_journal_entry(date, f"سلفة موظف - {notes or ''}", None, journal_items)
