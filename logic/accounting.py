
class AccountingLogic:
    def __init__(self, db_manager):
        self.db = db_manager

    def calculate_vat(self, amount, rate=0.15):
        vat = amount * rate
        total = amount + vat
        return vat, total

    def get_account_balance(self, account_code):
        """Raw balance of one account straight from the ledger - credit minus
        debit, which is the natural direction for a liability like accrued
        wages (2200) or loans (2300)."""
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(credit),0) - COALESCE(SUM(debit),0) v "
            "FROM journal_items WHERE account_code = ?", (account_code,))
        return row['v'] or 0

    def get_all_accounts(self):
        return self.db.fetch_all("SELECT code, name, type FROM chart_of_accounts ORDER BY code")

    def get_account_ledger(self, account_code):
        """Every journal item ever posted to one account (كشف حساب), in date
        order, with a running balance - not just its final total the way the
        trial balance shows it. The running balance grows with debit for an
        Asset/Expense account and with credit for a Liability/Equity/Revenue
        account, so it always reads as a plain increasing/decreasing number
        regardless of which side of the entry the account normally sits on."""
        account = self.db.fetch_one(
            "SELECT code, name, type FROM chart_of_accounts WHERE code = ?", (account_code,))
        if not account:
            return None

        rows = self.db.fetch_all(
            """SELECT je.date, je.description, ji.debit, ji.credit
               FROM journal_items ji
               JOIN journal_entries je ON je.id = ji.entry_id
               WHERE ji.account_code = ?
               ORDER BY je.date, je.id""",
            (account_code,),
        )
        debit_increases = account['type'] in ('Asset', 'Expense')
        balance = 0
        entries = []
        for row in rows:
            debit = row['debit'] or 0
            credit = row['credit'] or 0
            balance += (debit - credit) if debit_increases else (credit - debit)
            entries.append({'date': row['date'], 'description': row['description'],
                            'debit': debit, 'credit': credit, 'balance': balance})

        return {'account': account, 'entries': entries, 'balance': balance}

    def reverse_vat(self, total_amount, rate=0.15):
        """Given a VAT-inclusive total (e.g. the actual cash collected end-of-day),
        back out the pre-tax amount and the VAT portion."""
        amount = total_amount / (1 + rate)
        vat = total_amount - amount
        return amount, vat

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
        """The income statement's figures - now literally the same call the
        dashboard makes, reshaped to this method's own key names.

        This used to run its own COGS query against account 5000, and nothing
        anywhere in the app ever posts to account 5000: no screen moves
        inventory into cost of goods sold when it is sold rather than when it
        is bought, because this program does not track item-level stock at
        all - a deliberate choice made from the start, not an oversight, since
        the whole design is a daily total rather than a per-order system. The
        query was not wrong given what it was pointed at; what it was pointed
        at simply never received a posting, so cogs was silently 0 in every
        income statement this screen ever showed, and "net profit" here was
        revenue minus salaries and operating expenses only - every riyal spent
        on food or ingredients was missing from the figure entirely.

        Meanwhile the dashboard's own profit card used get_period_report(),
        which proxies cost of sales from purchases instead (the only
        consumption signal this data model actually has) - correctly, but
        get_period_report() had never included salaries in its own net profit
        either, so it was wrong in the opposite direction. The two screens
        showed two different numbers for the same restaurant on the same day,
        and neither of them was salaries-and-food-cost-complete.

        One formula now, computed once, read from both places.
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
        output_vat = (self.db.fetch_one(output_vat_query, (start_date, end_date))['value']) or 0
        input_vat = (self.db.fetch_one(input_vat_query, (start_date, end_date))['value']) or 0

        period = self.get_period_report(start_date, end_date, branch_id=None)

        return {
            'revenue': period['net_sales'],
            'cogs': period['cost_of_sales'],
            'operating_expenses': period['operating_expenses'],
            'salaries_expense': period['salaries_expense'],
            'gross_profit': period['gross_profit'],
            'net_profit': period['net_profit'],
            'output_vat': output_vat,
            'input_vat': input_vat,
            'net_vat': output_vat - input_vat,
        }

    def get_salaries_expense(self, start_date, end_date):
        """Payroll is posted company-wide (branch_id NULL on the journal
        entry - this program does not split an employee's salary across
        branches), so this has no branch filter to offer; a per-branch period
        report's net profit will not include salary cost. Worth knowing if a
        multi-branch owner ever compares a single branch's profit against the
        whole company's."""
        row = self.db.fetch_one(
            """SELECT COALESCE(SUM(debit) - SUM(credit), 0) as value
               FROM journal_items ji
               JOIN journal_entries je ON ji.entry_id = je.id
               WHERE ji.account_code = '5100' AND date(je.date) BETWEEN date(?) AND date(?)""",
            (start_date, end_date),
        )
        return row['value'] or 0

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

        revenue = balance.get('Revenue', {}).get('credit', 0) - balance.get('Revenue', {}).get('debit', 0)
        expense = balance.get('Expense', {}).get('debit', 0) - balance.get('Expense', {}).get('credit', 0)
        retained_earnings = revenue - expense
        equity = balance.get('Equity', {}).get('credit', 0) - balance.get('Equity', {}).get('debit', 0) + retained_earnings

        return {
            'assets': assets,
            'liabilities': liabilities,
            'equity': equity,
            'retained_earnings': retained_earnings,
            'balanced': abs(assets - (liabilities + equity)) < 0.01,
        }

    def get_balance_sheet_detail(self):
        """Per-account balances grouped under Assets / Liabilities / Equity for the قائمة المركز المالي view.
        Net profit-to-date (Revenue - Expense) is folded into Equity as 'الأرباح المرحّلة' to keep
        Assets = Liabilities + Equity even though the underlying ledger never closes Revenue/Expense."""
        query = """
            SELECT coa.code, coa.name, coa.type,
                   COALESCE(SUM(ji.debit), 0) as total_debit,
                   COALESCE(SUM(ji.credit), 0) as total_credit
            FROM chart_of_accounts coa
            LEFT JOIN journal_items ji ON coa.code = ji.account_code
            GROUP BY coa.code
            ORDER BY coa.code
        """
        rows = self.db.fetch_all(query)
        result = []
        revenue_total = 0
        expense_total = 0
        for row in rows:
            debit = row['total_debit'] or 0
            credit = row['total_credit'] or 0
            if row['type'] == 'Asset' and (debit or credit):
                result.append({'section': 'أصول', 'name': f"{row['code']} - {row['name']}", 'debit': debit - credit, 'credit': 0})
            elif row['type'] == 'Liability' and (debit or credit):
                result.append({'section': 'التزامات', 'name': f"{row['code']} - {row['name']}", 'debit': 0, 'credit': credit - debit})
            elif row['type'] == 'Equity' and (debit or credit):
                result.append({'section': 'حقوق ملكية', 'name': f"{row['code']} - {row['name']}", 'debit': 0, 'credit': credit - debit})
            elif row['type'] == 'Revenue':
                revenue_total += credit - debit
            elif row['type'] == 'Expense':
                expense_total += debit - credit

        retained_earnings = revenue_total - expense_total
        result.append({'section': 'حقوق ملكية', 'name': 'الأرباح المرحّلة (صافي الربح حتى تاريخه)', 'debit': 0, 'credit': retained_earnings})
        return result

    def get_trading_account(self, start_date, end_date, opening_inventory=0, closing_inventory=0):
        """حساب المتاجرة: opening inventory + purchases + purchase-related expenses - purchase returns
        = cost of goods available for sale; minus closing inventory = cost of goods sold."""
        purchases = self.db.fetch_one(
            """SELECT COALESCE(SUM(amount), 0) as v FROM purchases
               WHERE category = 'raw_material' AND date(date) BETWEEN date(?) AND date(?)""",
            (start_date, end_date),
        )['v'] or 0
        purchase_related_expenses = self.db.fetch_one(
            """SELECT COALESCE(SUM(amount), 0) as v FROM purchases
               WHERE category = 'purchase_expense' AND date(date) BETWEEN date(?) AND date(?)""",
            (start_date, end_date),
        )['v'] or 0
        purchase_returns = self.db.fetch_one(
            """SELECT COALESCE(SUM(amount), 0) as v FROM purchase_returns
               WHERE date(date) BETWEEN date(?) AND date(?)""",
            (start_date, end_date),
        )['v'] or 0
        sales_returns = self.db.fetch_one(
            """SELECT COALESCE(SUM(amount), 0) as v FROM sales_returns
               WHERE date(date) BETWEEN date(?) AND date(?)""",
            (start_date, end_date),
        )['v'] or 0

        summary = self.get_financial_summary(start_date, end_date)
        net_sales = summary['revenue']

        cogs_available = opening_inventory + purchases + purchase_related_expenses - purchase_returns
        cost_of_goods_sold = cogs_available - closing_inventory
        gross_profit = net_sales - cost_of_goods_sold

        return {
            'opening_inventory': opening_inventory,
            'purchases': purchases,
            'purchase_related_expenses': purchase_related_expenses,
            'purchase_returns': purchase_returns,
            'cogs_available': cogs_available,
            'closing_inventory': closing_inventory,
            'cost_of_goods_sold': cost_of_goods_sold,
            'net_sales': net_sales,
            'sales_returns': sales_returns,
            'gross_profit': gross_profit,
        }

    def get_supplier_statement(self, supplier_id):
        """Running ledger for a single supplier: opening balance + purchases (credit) - payments (debit) - purchase returns (debit)."""
        supplier = self.db.fetch_one("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
        if not supplier:
            return None

        entries = []
        opening_balance = supplier['opening_balance'] or 0
        if opening_balance:
            entries.append({'date': '', 'type': 'رصيد افتتاحي', 'debit': 0, 'credit': opening_balance})

        purchases = self.db.fetch_all(
            "SELECT date, total_amount FROM purchases WHERE supplier_id = ? AND payment_status = 'Credit' ORDER BY date",
            (supplier_id,),
        )
        for p in purchases:
            entries.append({'date': p['date'], 'type': 'فاتورة مشتريات آجلة', 'debit': 0, 'credit': p['total_amount'] or 0})

        payments = self.db.fetch_all(
            "SELECT date, amount, method FROM supplier_payments WHERE supplier_id = ? ORDER BY date",
            (supplier_id,),
        )
        for pay in payments:
            method_label = 'نقدي' if pay['method'] == 'Cash' else 'تحويل بنكي'
            entries.append({'date': pay['date'], 'type': f"سداد ({method_label})", 'debit': pay['amount'] or 0, 'credit': 0})

        returns = self.db.fetch_all(
            "SELECT date, amount, vat_amount FROM purchase_returns WHERE supplier_id = ? AND refund_method = 'CreditNote' ORDER BY date",
            (supplier_id,),
        )
        for r in returns:
            entries.append({'date': r['date'], 'type': 'مرتجع مشتريات', 'debit': (r['amount'] or 0) + (r['vat_amount'] or 0), 'credit': 0})

        entries.sort(key=lambda e: e['date'] or '')

        balance = 0
        for e in entries:
            balance += e['credit'] - e['debit']
            e['balance'] = balance

        return {'supplier': supplier, 'entries': entries, 'balance': balance}

    def get_all_supplier_balances(self):
        suppliers = self.db.fetch_all("SELECT * FROM suppliers ORDER BY name")
        results = []
        for s in suppliers:
            statement = self.get_supplier_statement(s['id'])
            results.append({'id': s['id'], 'name': s['name'], 'phone': s['phone'],
                            'balance': statement['balance'], 'is_active': bool(s['is_active'])})
        return results

    def get_customer_statement(self, customer_id):
        """Running ledger for a single customer: opening balance + credit
        sales (debit, what they owe us grows) - collections (credit, what
        they owe us shrinks). The mirror image of get_supplier_statement,
        with debit/credit read the other way round because a receivable is
        an asset (debit-increasing), not a liability."""
        customer = self.db.fetch_one("SELECT * FROM customers WHERE id = ?", (customer_id,))
        if not customer:
            return None

        entries = []
        opening_balance = customer['opening_balance'] or 0
        if opening_balance:
            entries.append({'date': '', 'type': 'رصيد افتتاحي', 'debit': opening_balance, 'credit': 0})

        sales = self.db.fetch_all(
            "SELECT date, amount, vat_amount FROM customer_sales WHERE customer_id = ? ORDER BY date",
            (customer_id,),
        )
        for s in sales:
            entries.append({'date': s['date'], 'type': 'بيع آجل',
                            'debit': (s['amount'] or 0) + (s['vat_amount'] or 0), 'credit': 0})

        payments = self.db.fetch_all(
            "SELECT date, amount, method FROM customer_payments WHERE customer_id = ? ORDER BY date",
            (customer_id,),
        )
        for pay in payments:
            method_label = 'نقدي' if pay['method'] == 'Cash' else 'تحويل بنكي'
            entries.append({'date': pay['date'], 'type': f"تحصيل ({method_label})",
                            'debit': 0, 'credit': pay['amount'] or 0})

        entries.sort(key=lambda e: e['date'] or '')

        balance = 0
        for e in entries:
            balance += e['debit'] - e['credit']
            e['balance'] = balance

        return {'customer': customer, 'entries': entries, 'balance': balance}

    def get_all_customer_balances(self):
        customers = self.db.fetch_all("SELECT * FROM customers ORDER BY name")
        results = []
        for c in customers:
            statement = self.get_customer_statement(c['id'])
            results.append({'id': c['id'], 'name': c['name'], 'phone': c['phone'],
                            'balance': statement['balance'], 'is_active': bool(c['is_active'])})
        return results

    def get_loan_statement(self, loan_id):
        """A loan is a liability, same sign convention as a supplier: the
        amount borrowed is a credit (what we owe grows), a repayment is a
        debit (what we owe shrinks)."""
        loan = self.db.fetch_one("SELECT * FROM loans WHERE id = ?", (loan_id,))
        if not loan:
            return None

        entries = [{'date': loan['date'], 'type': 'مبلغ القرض',
                    'debit': 0, 'credit': loan['amount'] or 0}]
        payments = self.db.fetch_all(
            "SELECT date, amount, method FROM loan_payments WHERE loan_id = ? ORDER BY date",
            (loan_id,),
        )
        for pay in payments:
            method_label = 'نقدي' if pay['method'] == 'Cash' else 'تحويل بنكي'
            entries.append({'date': pay['date'], 'type': f"سداد ({method_label})",
                            'debit': pay['amount'] or 0, 'credit': 0})

        entries.sort(key=lambda e: e['date'] or '')
        balance = 0
        for e in entries:
            balance += e['credit'] - e['debit']
            e['balance'] = balance

        return {'loan': loan, 'entries': entries, 'balance': balance}

    def get_all_loans_with_balances(self):
        loans = self.db.fetch_all("SELECT * FROM loans ORDER BY date")
        results = []
        for loan in loans:
            statement = self.get_loan_statement(loan['id'])
            results.append({'id': loan['id'], 'lender_name': loan['lender_name'],
                            'amount': loan['amount'], 'date': loan['date'],
                            'balance': statement['balance']})
        return results

    def get_prepaid_expenses_with_balances(self):
        """Each row's remaining balance is what has not yet been released
        into an actual expense - amount minus released_amount."""
        rows = self.db.fetch_all("SELECT * FROM prepaid_expenses ORDER BY date")
        return [{'id': r['id'], 'description': r['description'], 'amount': r['amount'],
                'date': r['date'], 'target_account_code': r['target_account_code'],
                'released_amount': r['released_amount'] or 0,
                'remaining': (r['amount'] or 0) - (r['released_amount'] or 0)} for r in rows]

    # ------------------------------------------------------------------
    # Reporting helpers
    # ------------------------------------------------------------------

    def _branch_clause(self, branch_id, alias):
        if branch_id:
            return f" AND {alias}.branch_id = ?", (branch_id,)
        return "", ()

    def get_sales_by_method(self, start_date, end_date, branch_id=None):
        clause, params = self._branch_clause(branch_id, "s")
        rows = self.db.fetch_all(
            f"""SELECT s.payment_method as method,
                       COALESCE(SUM(s.total_amount), 0) as total,
                       COALESCE(SUM(s.vat_amount), 0) as vat
                FROM sales s
                WHERE date(s.date) BETWEEN date(?) AND date(?){clause}
                GROUP BY s.payment_method""",
            (start_date, end_date) + params,
        )
        result = {m: {'total': 0.0, 'vat': 0.0} for m in ('Cash', 'POS', 'Transfer')}
        for row in rows:
            result.setdefault(row['method'], {'total': 0.0, 'vat': 0.0})
            result[row['method']]['total'] = row['total'] or 0
            result[row['method']]['vat'] = row['vat'] or 0
        result['grand_total'] = sum(v['total'] for k, v in result.items() if isinstance(v, dict))
        result['grand_vat'] = sum(v['vat'] for k, v in result.items() if isinstance(v, dict))
        result['net_sales'] = result['grand_total'] - result['grand_vat']
        return result

    def get_purchases_by_category(self, start_date, end_date, branch_id=None):
        clause, params = self._branch_clause(branch_id, "p")
        rows = self.db.fetch_all(
            f"""SELECT COALESCE(p.category, 'raw_material') as category,
                       COALESCE(SUM(p.amount), 0) as net,
                       COALESCE(SUM(p.vat_amount), 0) as vat,
                       COALESCE(SUM(p.total_amount), 0) as total
                FROM purchases p
                WHERE date(p.date) BETWEEN date(?) AND date(?){clause}
                GROUP BY COALESCE(p.category, 'raw_material')""",
            (start_date, end_date) + params,
        )
        result = {c: {'net': 0.0, 'vat': 0.0, 'total': 0.0}
                  for c in ('raw_material', 'purchase_expense', 'operating_expense')}
        for row in rows:
            result.setdefault(row['category'], {'net': 0.0, 'vat': 0.0, 'total': 0.0})
            result[row['category']] = {'net': row['net'] or 0, 'vat': row['vat'] or 0, 'total': row['total'] or 0}
        result['grand_net'] = sum(v['net'] for k, v in result.items() if isinstance(v, dict))
        result['grand_vat'] = sum(v['vat'] for k, v in result.items() if isinstance(v, dict))
        result['grand_total'] = sum(v['total'] for k, v in result.items() if isinstance(v, dict))
        return result

    def get_returns_summary(self, start_date, end_date, branch_id=None):
        sales_clause, sales_params = self._branch_clause(branch_id, "sr")
        purchase_clause, purchase_params = self._branch_clause(branch_id, "pr")
        sales_returns = self.db.fetch_one(
            f"""SELECT COALESCE(SUM(amount), 0) as net, COALESCE(SUM(vat_amount), 0) as vat
                FROM sales_returns sr
                WHERE date(sr.date) BETWEEN date(?) AND date(?){sales_clause}""",
            (start_date, end_date) + sales_params,
        )
        purchase_returns = self.db.fetch_one(
            f"""SELECT COALESCE(SUM(amount), 0) as net, COALESCE(SUM(vat_amount), 0) as vat
                FROM purchase_returns pr
                WHERE date(pr.date) BETWEEN date(?) AND date(?){purchase_clause}""",
            (start_date, end_date) + purchase_params,
        )
        return {
            'sales_returns': sales_returns['net'] or 0,
            'sales_returns_vat': sales_returns['vat'] or 0,
            'purchase_returns': purchase_returns['net'] or 0,
            'purchase_returns_vat': purchase_returns['vat'] or 0,
        }

    def get_daily_breakdown(self, start_date, end_date, branch_id=None):
        """Day-by-day sales / purchases / VAT, used for the period report table."""
        sales_clause, sales_params = self._branch_clause(branch_id, "s")
        purchase_clause, purchase_params = self._branch_clause(branch_id, "p")

        sales_rows = self.db.fetch_all(
            f"""SELECT date(s.date) as day,
                       COALESCE(SUM(CASE WHEN s.payment_method='Cash' THEN s.total_amount ELSE 0 END), 0) as cash,
                       COALESCE(SUM(CASE WHEN s.payment_method='POS' THEN s.total_amount ELSE 0 END), 0) as pos,
                       COALESCE(SUM(CASE WHEN s.payment_method='Transfer' THEN s.total_amount ELSE 0 END), 0) as transfer,
                       COALESCE(SUM(s.total_amount), 0) as total,
                       COALESCE(SUM(s.vat_amount), 0) as vat
                FROM sales s
                WHERE date(s.date) BETWEEN date(?) AND date(?){sales_clause}
                GROUP BY date(s.date)""",
            (start_date, end_date) + sales_params,
        )
        purchase_rows = self.db.fetch_all(
            f"""SELECT date(p.date) as day,
                       COALESCE(SUM(p.amount), 0) as net,
                       COALESCE(SUM(p.vat_amount), 0) as vat
                FROM purchases p
                WHERE date(p.date) BETWEEN date(?) AND date(?){purchase_clause}
                GROUP BY date(p.date)""",
            (start_date, end_date) + purchase_params,
        )

        days = {}
        for row in sales_rows:
            days[row['day']] = {
                'day': row['day'], 'cash': row['cash'] or 0, 'pos': row['pos'] or 0,
                'transfer': row['transfer'] or 0, 'sales_total': row['total'] or 0,
                'output_vat': row['vat'] or 0, 'purchases': 0.0, 'input_vat': 0.0,
            }
        for row in purchase_rows:
            entry = days.setdefault(row['day'], {
                'day': row['day'], 'cash': 0.0, 'pos': 0.0, 'transfer': 0.0,
                'sales_total': 0.0, 'output_vat': 0.0, 'purchases': 0.0, 'input_vat': 0.0,
            })
            entry['purchases'] = row['net'] or 0
            entry['input_vat'] = row['vat'] or 0

        result = []
        for day in sorted(days):
            entry = days[day]
            net_sales = entry['sales_total'] - entry['output_vat']
            entry['net_sales'] = net_sales
            entry['profit'] = net_sales - entry['purchases']
            entry['net_vat'] = entry['output_vat'] - entry['input_vat']
            result.append(entry)
        return result

    def get_period_report(self, start_date, end_date, branch_id=None):
        """Everything the period report needs, in one call."""
        sales = self.get_sales_by_method(start_date, end_date, branch_id)
        purchases = self.get_purchases_by_category(start_date, end_date, branch_id)
        returns = self.get_returns_summary(start_date, end_date, branch_id)

        net_sales = sales['net_sales'] - returns['sales_returns']
        output_vat = sales['grand_vat'] - returns['sales_returns_vat']
        input_vat = purchases['grand_vat'] - returns['purchase_returns_vat']

        cost_of_sales = purchases['raw_material']['net'] + purchases['purchase_expense']['net'] \
            - returns['purchase_returns']
        operating_expenses = purchases['operating_expense']['net']
        # Payroll is the other real cost of running the place, and it used to
        # be left out of this figure entirely - "net profit" here was silently
        # gross profit minus rent and utilities, with staff cost missing.
        # Company-wide only; see get_salaries_expense for why.
        salaries_expense = self.get_salaries_expense(start_date, end_date)

        gross_profit = net_sales - cost_of_sales
        net_profit = gross_profit - operating_expenses - salaries_expense

        return {
            'start_date': start_date,
            'end_date': end_date,
            'sales': sales,
            'purchases': purchases,
            'returns': returns,
            'net_sales': net_sales,
            'cost_of_sales': cost_of_sales,
            'operating_expenses': operating_expenses,
            'salaries_expense': salaries_expense,
            'gross_profit': gross_profit,
            'net_profit': net_profit,
            'output_vat': output_vat,
            'input_vat': input_vat,
            'net_vat': output_vat - input_vat,
            'daily': self.get_daily_breakdown(start_date, end_date, branch_id),
        }
