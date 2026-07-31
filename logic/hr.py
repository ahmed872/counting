from datetime import datetime, timedelta

class HRLogic:
    def __init__(self, db_manager):
        self.db = db_manager

    def calculate_daily_rate(self, base_salary, allowances):
        return (base_salary + allowances) / 30

    def get_document_alerts(self, days=30):
        today = datetime.now().date()
        alert_date = today + timedelta(days=days)
        
        query = """
            SELECT name, 'إقامة' as doc_type, iqama_expiry as expiry_date FROM employees WHERE iqama_expiry IS NOT NULL AND iqama_expiry <= ?
            UNION
            SELECT name, 'جواز سفر' as doc_type, passport_expiry as expiry_date FROM employees WHERE passport_expiry IS NOT NULL AND passport_expiry <= ?
            UNION
            SELECT name, 'تصريح عمل' as doc_type, work_permit_expiry as expiry_date FROM employees WHERE work_permit_expiry IS NOT NULL AND work_permit_expiry <= ?
            UNION
            SELECT name, 'كرت عمل' as doc_type, work_card_expiry as expiry_date FROM employees WHERE work_card_expiry IS NOT NULL AND work_card_expiry <= ?
        """
        return self.db.fetch_all(query, (alert_date, alert_date, alert_date, alert_date))

    def record_attendance(self, employee_id, date, status):
        self.db.execute_query(
            "INSERT INTO attendance (employee_id, date, status) VALUES (?, ?, ?)",
            (employee_id, date, status)
        )

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
        rows = self.db.fetch_all(query, (f"{month:02d}", str(year)))
        payroll = []
        for row in rows:
            gross = (row['base_salary'] or 0) + (row['allowances'] or 0)
            daily_rate = self.calculate_daily_rate(row['base_salary'] or 0, row['allowances'] or 0)
            absence_deduction = daily_rate * (row['absent_days'] or 0)
            net_salary = gross - absence_deduction
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
                'net_salary': net_salary,
            })
        return payroll
