import base64
from datetime import datetime

class AccountingLogic:
    def __init__(self, db_manager):
        self.db = db_manager

    def calculate_vat(self, amount, rate=0.15):
        vat = amount * rate
        total = amount + vat
        return vat, total

    def generate_zatca_qr(self, seller_name, tax_no, timestamp, total_amount, vat_amount):
        """
        ZATCA QR Code TLV (Tag-Length-Value) format:
        Tag 1: Seller Name
        Tag 2: Tax Number
        Tag 3: Timestamp
        Tag 4: Total Amount (with VAT)
        Tag 5: VAT Amount
        """
        def get_tlv(tag, value):
            tag_bytes = bytes([tag])
            length_bytes = bytes([len(str(value).encode('utf-8'))])
            value_bytes = str(value).encode('utf-8')
            return tag_bytes + length_bytes + value_bytes

        tlv_data = (
            get_tlv(1, seller_name) +
            get_tlv(2, tax_no) +
            get_tlv(3, timestamp) +
            get_tlv(4, total_amount) +
            get_tlv(5, vat_amount)
        )
        return base64.b64encode(tlv_data).decode('utf-8')

    def get_trial_balance(self):
        query = """
            SELECT 
                coa.code, 
                coa.name, 
                coa.type,
                SUM(ji.debit) as total_debit,
                SUM(ji.credit) as total_credit
            FROM chart_of_accounts coa
            LEFT JOIN journal_items ji ON coa.code = ji.account_code
            GROUP BY coa.code
        """
        return self.db.fetch_all(query)

    def get_financial_summary(self, start_date, end_date):
        revenue_query = """
            SELECT COALESCE(SUM(credit) - SUM(debit), 0) as value
            FROM journal_items ji
            JOIN journal_entries je ON ji.entry_id = je.id
            WHERE ji.account_code = '4000' AND date(je.date) BETWEEN date(?) AND date(?)
        """
        cogs_query = """
            SELECT COALESCE(SUM(debit) - SUM(credit), 0) as value
            FROM journal_items ji
            JOIN journal_entries je ON ji.entry_id = je.id
            WHERE ji.account_code = '5000' AND date(je.date) BETWEEN date(?) AND date(?)
        """
        expenses_query = """
            SELECT COALESCE(SUM(debit) - SUM(credit), 0) as value
            FROM journal_items ji
            JOIN journal_entries je ON ji.entry_id = je.id
            WHERE ji.account_code IN ('5100', '5200') AND date(je.date) BETWEEN date(?) AND date(?)
        """
        output_vat_query = """
            SELECT COALESCE(SUM(credit) - SUM(debit), 0) as value
            FROM journal_items ji
            JOIN journal_entries je ON ji.entry_id = je.id
            WHERE ji.account_code = '2100' AND date(je.date) BETWEEN date(?) AND date(?)
        """
        input_vat_query = """
            SELECT COALESCE(SUM(debit) - SUM(credit), 0) as value
            FROM journal_items ji
            JOIN journal_entries je ON ji.entry_id = je.id
            WHERE ji.account_code = '1200' AND date(je.date) BETWEEN date(?) AND date(?)
        """

        revenue = (self.db.fetch_one(revenue_query, (start_date, end_date))['value']) or 0
        cogs = (self.db.fetch_one(cogs_query, (start_date, end_date))['value']) or 0
        operating_expenses = (self.db.fetch_one(expenses_query, (start_date, end_date))['value']) or 0
        output_vat = (self.db.fetch_one(output_vat_query, (start_date, end_date))['value']) or 0
        input_vat = (self.db.fetch_one(input_vat_query, (start_date, end_date))['value']) or 0

        return {
            'revenue': revenue,
            'cogs': cogs,
            'operating_expenses': operating_expenses,
            'gross_profit': revenue - cogs,
            'net_profit': revenue - cogs - operating_expenses,
            'output_vat': output_vat,
            'input_vat': input_vat,
            'net_vat': output_vat - input_vat,
        }

    def get_balance_sheet(self):
        query = """
            SELECT
                coa.type,
                COALESCE(SUM(ji.debit), 0) as total_debit,
                COALESCE(SUM(ji.credit), 0) as total_credit
            FROM chart_of_accounts coa
            LEFT JOIN journal_items ji ON coa.code = ji.account_code
            GROUP BY coa.type
        """
        rows = self.db.fetch_all(query)
        balance = {row['type']: {'debit': row['total_debit'] or 0, 'credit': row['total_credit'] or 0} for row in rows}
        assets = balance.get('Asset', {}).get('debit', 0) - balance.get('Asset', {}).get('credit', 0)
        liabilities = balance.get('Liability', {}).get('credit', 0) - balance.get('Liability', {}).get('debit', 0)
        equity = balance.get('Equity', {}).get('credit', 0) - balance.get('Equity', {}).get('debit', 0)
        return {
            'assets': assets,
            'liabilities': liabilities,
            'equity': equity,
            'balanced': abs(assets - (liabilities + equity)) < 0.01,
        }
