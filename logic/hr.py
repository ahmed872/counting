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
            SELECT id, name, 'إقامة' as doc_type, iqama_expiry as expiry_date FROM employees WHERE iqama_expiry IS NOT NULL AND iqama_expiry <= ?
            UNION
            SELECT id, name, 'جواز سفر' as doc_type, passport_expiry as expiry_date FROM employees WHERE passport_expiry IS NOT NULL AND passport_expiry <= ?
            UNION
            SELECT id, name, 'تصريح عمل' as doc_type, work_permit_expiry as expiry_date FROM employees WHERE work_permit_expiry IS NOT NULL AND work_permit_expiry <= ?
            UNION
            SELECT id, name, 'كرت عمل' as doc_type, work_card_expiry as expiry_date FROM employees WHERE work_card_expiry IS NOT NULL AND work_card_expiry <= ?
            ORDER BY expiry_date
        """
        return self.db.fetch_all(query, (alert_date, alert_date, alert_date, alert_date))

    def record_attendance(self, employee_id, date, status):
        self.db.execute_query(
            "INSERT INTO attendance (employee_id, date, status) VALUES (?, ?, ?)",
            (employee_id, date, status)
        )

    def add_deduction(self, employee_id, date, entry_type, amount, notes=""):
        """entry_type: 'Deduction' (penalty), 'Advance' (سلفة), or 'Bonus'."""
        self.db.execute_query(
            "INSERT INTO employee_deductions (employee_id, date, type, amount, notes) VALUES (?, ?, ?, ?, ?)",
            (employee_id, date, entry_type, amount, notes)
        )

    def get_employee_entries(self, employee_id, limit=50):
        return self.db.fetch_all(
            "SELECT * FROM employee_deductions WHERE employee_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (employee_id, limit)
        )

    def get_outstanding_advances_total(self):
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(amount), 0) as total FROM employee_deductions WHERE type = 'Advance' AND settled_run_id IS NULL"
        )
        return row['total'] or 0

    def get_monthly_payroll(self, month, year):
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
            GROUP BY e.id
            ORDER BY e.name
        """
        month_str = f"{month:02d}"
        year_str = str(year)
        rows = self.db.fetch_all(query, (month_str, year_str))
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

            unsettled_advances = self.db.fetch_one(
                "SELECT COALESCE(SUM(amount), 0) as total FROM employee_deductions WHERE employee_id = ? AND type = 'Advance' AND settled_run_id IS NULL",
                (row['id'],)
            )['total'] or 0

            expense_amount = gross - absence_deduction - other_deductions + bonuses
            net_salary = expense_amount - unsettled_advances

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
                'advances_recovered': unsettled_advances,
                'expense_amount': expense_amount,
                'net_salary': net_salary,
            })
        return payroll

    def is_payroll_posted(self, month, year):
        return self.db.fetch_one(
            "SELECT id FROM payroll_runs WHERE month = ? AND year = ?", (month, year)
        ) is not None

    def post_payroll(self, month, year):
        """Posts the month's payroll to the accounting journal:
        Debit Salaries Expense (5100) for gross-less-deductions-plus-bonuses,
        Credit Employee Advances (1300) for any advances recovered this run,
        Credit Cash (1000) for the actual net amount paid out.
        Marks unsettled advances as settled so they are not deducted twice."""
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
            """INSERT INTO payroll_runs (month, year, posted_at, total_expense, total_net_paid, total_advances_recovered)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (month, year, timestamp, total_expense, total_net_paid, total_advances_recovered)
        )

        for p in payroll:
            self.db.execute_query(
                """INSERT INTO payroll_run_items
                   (run_id, employee_id, gross_salary, absence_deduction, other_deductions, bonuses, advances_recovered, net_salary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, p['id'], p['gross_salary'], p['absence_deduction'], p['other_deductions'],
                 p['bonuses'], p['advances_recovered'], p['net_salary'])
            )
            self.db.execute_query(
                "UPDATE employee_deductions SET settled_run_id = ? WHERE employee_id = ? AND type = 'Advance' AND settled_run_id IS NULL",
                (run_id, p['id'])
            )

        journal_items = [{'account_code': '5100', 'debit': total_expense, 'credit': 0}]
        if total_advances_recovered:
            journal_items.append({'account_code': '1300', 'debit': 0, 'credit': total_advances_recovered})
        journal_items.append({'account_code': '1000', 'debit': 0, 'credit': total_net_paid})

        self.db.add_journal_entry(timestamp, f"صرف رواتب شهر {month:02d}/{year}", None, journal_items)
        return run_id

    def grant_advance(self, employee_id, date, amount, notes=""):
        """Cash advance paid out to an employee ahead of payroll; recovered automatically in the next run."""
        self.add_deduction(employee_id, date, 'Advance', amount, notes)
        journal_items = [
            {'account_code': '1300', 'debit': amount, 'credit': 0},
            {'account_code': '1000', 'debit': 0, 'credit': amount},
        ]
        self.db.add_journal_entry(date, f"سلفة موظف - {notes or ''}", None, journal_items)
