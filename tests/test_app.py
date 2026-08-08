"""End-to-end regression checks.

Run headlessly:  QT_QPA_PLATFORM=offscreen python tests/test_app.py

Covers the paths that have actually broken before: accounting identities,
VAT handling, stylesheet leaking onto child widgets, invisible buttons,
RTL date formatting, and content being cut off below the window.
"""

import re
import os
import shutil
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QApplication, QMessageBox, QPushButton, QDateEdit, QLabel, QScrollArea,
    QTableWidget,
)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt, QDate

from database.db_manager import DBManager
from ui.main_window import MainWindow
from ui.theme import apply_theme

# Not a hard-coded /tmp: the release build runs these same checks on a Windows
# runner, where that path does not exist and every test would fail to open a
# database.
DB_PATH = os.path.join(tempfile.gettempdir(), "_erp_regression.db")

failures = []


def check(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except Exception as exc:  # noqa: BLE001 - report every failure, don't stop
        print(f"  FAIL  {name} -> {exc}")
        traceback.print_exc()
        failures.append(name)


def silence_dialogs():
    for attr in ("information", "warning", "critical"):
        setattr(QMessageBox, attr, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)


def render(widget):
    """Render onto a white-filled pixmap. A fresh QPixmap is uninitialised, so
    widgets with transparent backgrounds would otherwise leave garbage pixels
    and make these checks flaky. White also mirrors the real page background,
    so 'nothing was painted' shows up as white - which is what we test for."""
    pixmap = QPixmap(widget.size())
    pixmap.fill(Qt.GlobalColor.white)
    widget.render(pixmap)
    return pixmap.toImage()


def is_near_white(hex_colour):
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return r > 235 and g > 235 and b > 235


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    silence_dialogs()
    from main import pin_dpi_policy
    pin_dpi_policy()
    db = DBManager(DB_PATH)
    app = QApplication(sys.argv)
    apply_theme(app)
    from main import apply_app_icon
    apply_app_icon(app)
    window = MainWindow(db)
    window.resize(1280, 720)   # deliberately small: catches cut-off content
    window.show()
    app.processEvents()
    app.processEvents()

    def goto(label):
        entry = next(e for e in window.nav_entries if e["label"] == label)
        window.set_active_page(entry["index"])
        app.processEvents()
        app.processEvents()
        return entry

    pages = ["dashboard", "sales", "hr", "purchases", "suppliers", "reports", "accounting"]

    # ---------------- data entry flows ----------------
    print("\n[flows]")

    def add_employee():
        goto("hr")
        hr = window.hr
        hr.name_input.setText("خالد سعيد")
        hr.job_input.setText("طباخ")
        hr.salary_input.setText("6000")
        hr.allowance_input.setText("0")
        hr.save_employee()
        assert db.fetch_one("SELECT id FROM employees WHERE name='خالد سعيد'")
    check("add employee", add_employee)

    def edit_employee_salary():
        hr = window.hr
        emp_id = db.fetch_one("SELECT id FROM employees WHERE name='خالد سعيد'")["id"]
        hr.employee_picker.setCurrentIndex(hr.employee_picker.findData(emp_id))
        assert hr.salary_input.text().startswith("6000"), hr.salary_input.text()
        hr.salary_input.setText("6600")
        hr.save_employee()
        again = db.fetch_one("SELECT base_salary FROM employees WHERE id = ?", (emp_id,))
        assert abs(again["base_salary"] - 6600) < 0.01, again["base_salary"]
        # put it back so the payroll expectations below still hold
        hr.employee_picker.setCurrentIndex(hr.employee_picker.findData(emp_id))
        hr.salary_input.setText("6000")
        hr.save_employee()
        assert db.fetch_one("SELECT COUNT(*) c FROM employees")["c"] == 1, "edit created a duplicate row"
    check("editing an employee updates instead of duplicating", edit_employee_salary)

    def saving_twice_does_not_duplicate_the_employee():
        """A screenshot showed three identical employees named صابر after the
        save button was clicked three times with the same data still sitting
        in the form. The form was never actually cleared: clear_employee_form
        only reset the picker's index, and Qt does not emit
        currentIndexChanged when an index is set to the value it already
        holds - which is exactly the picker's state right after adding
        someone. The typed values stayed in the boxes, invisible to the user,
        and the next click saved them again."""
        hr = window.hr
        before = db.fetch_one("SELECT COUNT(*) c FROM employees WHERE name='صابر'")["c"]
        hr.name_input.setText("صابر")
        hr.job_input.setText("مهم")
        hr.salary_input.setText("5000")
        hr.allowance_input.setText("1000")
        hr.iqama_input.setText("44")
        for _ in range(3):
            hr.save_employee()
        after = db.fetch_one("SELECT COUNT(*) c FROM employees WHERE name='صابر'")["c"]
        assert after == before + 1, f"expected 1 new صابر, found {after - before}"
        assert hr.name_input.text() == "", \
            "the form still holds the saved values after a successful save"
    check("clicking save more than once does not duplicate the employee",
          saving_twice_does_not_duplicate_the_employee)

    def new_employee_button_actually_clears_the_form():
        """The same broken clear made this button feel useless: in the common
        case (already adding a new employee, picker already on index 0), the
        click changed nothing a user could see."""
        hr = window.hr
        hr.name_input.setText("نص مؤقت")
        hr.job_input.setText("نص مؤقت")
        hr.new_btn.click()
        assert hr.name_input.text() == "", "موظف جديد did not clear the name field"
        assert hr.job_input.text() == "", "موظف جديد did not clear the job field"
    check("the 'موظف جديد' button visibly clears the form",
          new_employee_button_actually_clears_the_form)

    def duplicate_attendance_counts_once():
        hr = window.hr
        emp_id = db.fetch_one("SELECT id FROM employees WHERE name='خالد سعيد'")["id"]
        for _ in range(3):
            window.hr_logic.record_attendance(emp_id, "2026-08-09", "Absent")
        rows = db.fetch_all(
            "SELECT * FROM attendance WHERE employee_id=? AND date='2026-08-09'", (emp_id,))
        assert len(rows) == 1, f"{len(rows)} attendance rows for one day"
        window.hr_logic.record_attendance(emp_id, "2026-08-09", "Present")
        row = window.hr_logic.get_attendance(emp_id, "2026-08-09")
        assert row["status"] == "Present", row["status"]
        # leave the day clean for the deduction check below
        db.execute_query("DELETE FROM attendance WHERE employee_id=? AND date='2026-08-09'", (emp_id,))
    check("same day recorded twice counts once and can be corrected", duplicate_attendance_counts_once)

    def absence_deducts_one_day():
        hr = window.hr
        emp_id = db.fetch_one("SELECT id FROM employees WHERE name='خالد سعيد'")["id"]
        hr.attendance_employee.setCurrentIndex(hr.attendance_employee.findData(emp_id))
        hr.attendance_status.setCurrentIndex(hr.attendance_status.findData("Absent"))
        hr.record_attendance()
        row = next(r for r in window.hr_logic.get_monthly_payroll(
            hr.payroll_month.currentData(), int(hr.payroll_year.text())) if r["id"] == emp_id)
        # (basic + allowances) / 30 == 6000/30 == 200
        assert abs(row["daily_rate"] - 200) < 0.01, row["daily_rate"]
        assert abs(row["absence_deduction"] - 200) < 0.01, row["absence_deduction"]
        assert abs(row["net_salary"] - 5800) < 0.01, row["net_salary"]
    check("one absent day deducts (basic+allowances)/30", absence_deducts_one_day)

    def post_payroll_once():
        hr = window.hr
        month, year = hr.payroll_month.currentData(), int(hr.payroll_year.text())
        window.hr_logic.post_payroll(month, year)
        try:
            window.hr_logic.post_payroll(month, year)
            raise AssertionError("payroll posted twice for the same month")
        except ValueError:
            pass
    check("payroll posts once and refuses a duplicate", post_payroll_once)

    def future_advance_does_not_leak_into_an_earlier_month():
        """An advance had no date filter at all on it - one granted in August
        was recoverable out of July's payroll, a month before it existed."""
        emp_id = db.insert_and_return_id(
            "INSERT INTO employees (name, job_title, branch_id, base_salary, allowances) "
            "VALUES (?,?,?,?,?)", ("اختبار السلف", "عامل", 1, 3000, 0))
        window.hr_logic.grant_advance(emp_id, "2026-08-10", 500, "سلفة أغسطس")
        july = next(p for p in window.hr_logic.get_monthly_payroll(7, 2026) if p["id"] == emp_id)
        assert july["advances_recovered"] == 0, july["advances_recovered"]
        # Children before parent, now that foreign keys are actually enforced.
        db.execute_query("DELETE FROM employee_deductions WHERE employee_id = ?", (emp_id,))
        db.execute_query("DELETE FROM employees WHERE id = ?", (emp_id,))
    check("an advance is not recovered from a month before it was granted",
          future_advance_does_not_leak_into_an_earlier_month)

    def advance_bigger_than_salary_never_makes_net_pay_negative():
        """An advance larger than one month's salary used to be recovered in
        full in a single run, driving net pay negative - paying someone to
        have been advanced money - and the whole advance was marked settled
        regardless, so the unrecovered remainder silently vanished from the
        books."""
        emp_id = db.insert_and_return_id(
            "INSERT INTO employees (name, job_title, branch_id, base_salary, allowances) "
            "VALUES (?,?,?,?,?)", ("سلفة كبيرة", "عامل", 1, 3000, 0))
        window.hr_logic.grant_advance(emp_id, "2026-05-01", 10000, "سلفة ضخمة")
        may = next(p for p in window.hr_logic.get_monthly_payroll(5, 2026) if p["id"] == emp_id)
        assert may["net_salary"] >= 0, may["net_salary"]
        assert may["advances_recovered"] == may["expense_amount"]
        window.hr_logic.post_payroll(5, 2026)
        remainder = db.fetch_one(
            "SELECT amount, amount_recovered, settled_run_id FROM employee_deductions "
            "WHERE employee_id = ? AND type='Advance'", (emp_id,))
        assert remainder["settled_run_id"] is None, \
            "an under-recovered advance was marked fully settled"
        assert remainder["amount"] - remainder["amount_recovered"] > 0
        june = next(p for p in window.hr_logic.get_monthly_payroll(6, 2026) if p["id"] == emp_id)
        assert june["advances_recovered"] > 0, "the remaining debt did not carry into next month"
        db.execute_query("DELETE FROM payroll_run_items WHERE employee_id = ?", (emp_id,))
        db.execute_query("DELETE FROM payroll_runs WHERE month=5 AND year=2026 AND "
                          "(SELECT COUNT(*) FROM payroll_run_items WHERE run_id=payroll_runs.id)=0")
        db.execute_query("DELETE FROM employee_deductions WHERE employee_id = ?", (emp_id,))
        db.execute_query("DELETE FROM employees WHERE id = ?", (emp_id,))
    check("an advance bigger than salary is recovered gradually, never below zero pay",
          advance_bigger_than_salary_never_makes_net_pay_negative)

    def a_31_day_month_cannot_deduct_more_than_the_salary():
        """A 31-day month allows 31 attendance rows, and 31 x daily_rate is
        more than the whole salary - the deduction used to be able to exceed
        what there was to deduct from."""
        emp_id = db.insert_and_return_id(
            "INSERT INTO employees (name, job_title, branch_id, base_salary, allowances) "
            "VALUES (?,?,?,?,?)", ("غياب كامل الشهر", "عامل", 1, 3000, 0))
        for day in range(1, 32):
            window.hr_logic.record_attendance(emp_id, f"2026-07-{day:02d}", "Absent")
        july = next(p for p in window.hr_logic.get_monthly_payroll(7, 2026) if p["id"] == emp_id)
        assert july["absent_days"] == 31, july["absent_days"]
        assert july["expense_amount"] >= 0, july["expense_amount"]
        db.execute_query("DELETE FROM attendance WHERE employee_id = ?", (emp_id,))
        db.execute_query("DELETE FROM employee_deductions WHERE employee_id = ?", (emp_id,))
        db.execute_query("DELETE FROM employees WHERE id = ?", (emp_id,))
    check("a month with 31 absences cannot deduct below zero pay",
          a_31_day_month_cannot_deduct_more_than_the_salary)

    def supplier_ledger():
        goto("suppliers")
        s = window.suppliers
        s.name_input.setText("مورد الاختبار")
        s.opening_balance_input.setText("1000")
        s.add_supplier()
        sid = db.fetch_one("SELECT id FROM suppliers WHERE name='مورد الاختبار'")["id"]
        s.selected_supplier_id = sid
        s.payment_amount.setText("400")
        s.record_payment()
        balance = window.accounting.accounting.get_supplier_statement(sid)["balance"]
        assert abs(balance - 600) < 0.01, balance
    check("supplier opening balance minus payment", supplier_ledger)

    def paying_a_supplier_needs_no_other_screen():
        """Choosing who is being paid belongs on the screen where the payment
        is entered. It used to be a read-only label that only filled in after
        selecting a row on a different tab, so the payment screen could not
        answer 'who am I paying?' on its own."""
        from PyQt6.QtWidgets import QComboBox
        goto("suppliers")
        s = window.suppliers
        assert isinstance(s.payment_supplier, QComboBox)
        assert s.payment_supplier.count() > 0, "the picker is empty"
        # Every supplier in the list must be choosable from it.
        names = {s.payment_supplier.itemText(i) for i in range(s.payment_supplier.count())}
        stored = {r["name"] for r in db.fetch_all("SELECT name FROM suppliers")}
        assert stored <= names, stored - names
        # Picking one there must actually point the payment at them.
        sid = db.fetch_one("SELECT id FROM suppliers WHERE name='مورد الاختبار'")["id"]
        s.payment_supplier.setCurrentIndex(s.payment_supplier.findData(sid))
        app.processEvents()
        assert s.selected_supplier_id == sid
        assert "ريال" in s.payment_balance_label.text() or "مسدد" in s.payment_balance_label.text()
    check("a supplier can be picked on the payment screen itself",
          paying_a_supplier_needs_no_other_screen)

    def overpaying_a_supplier_asks_first():
        """Paying more than is owed is almost always an extra zero or the wrong
        supplier. It went through silently and the balance just went negative."""
        asked = []
        original = QMessageBox.question
        QMessageBox.question = staticmethod(
            lambda *a, **k: asked.append(a[1]) or QMessageBox.StandardButton.No)
        try:
            goto("suppliers")
            s = window.suppliers
            sid = db.fetch_one("SELECT id FROM suppliers WHERE name='مورد الاختبار'")["id"]
            s.payment_supplier.setCurrentIndex(s.payment_supplier.findData(sid))
            app.processEvents()
            before = db.fetch_one("SELECT COUNT(*) c FROM supplier_payments")["c"]
            s.payment_amount.setText("999999")
            s.record_payment()
            assert asked, "an overpayment was accepted without asking"
            after = db.fetch_one("SELECT COUNT(*) c FROM supplier_payments")["c"]
            assert after == before, "answering no still recorded the payment"
        finally:
            QMessageBox.question = original
            window.suppliers.payment_amount.clear()
    check("paying more than is owed asks before going through",
          overpaying_a_supplier_asks_first)

    def negative_money_reads_correctly():
        """In a right-to-left line the bidi algorithm throws a leading minus to
        the visual right, so -1000 was displayed as '1,000.00-' - which scans as
        a positive number with a stray dash, on the screen where owing and being
        owed are the entire distinction."""
        from ui.formatting import money, LTR_ISOLATE, POP_ISOLATE
        negative = money(-1000)

        # Checking the order of the characters proves nothing - the minus is
        # first in the string either way. What was broken is how the string is
        # laid out, and the only thing that fixes that is the directional
        # control, so that is what gets asserted.
        assert negative.startswith(LTR_ISOLATE) and negative.endswith(POP_ISOLATE), (
            f"a negative amount carries no direction mark, so Arabic layout will "
            f"push the minus to the far side: {negative!r}")
        assert "-1,000.00" in negative

        # Positive amounts must stay clean: no invisible characters leaking into
        # exported reports or into anything compared as text.
        assert money(1000) == "1,000.00", repr(money(1000))
        assert money(0) == "0.00", repr(money(0))
    check("a negative amount still reads as negative in Arabic",
          negative_money_reads_correctly)

    def purchases_route_by_category():
        goto("purchases")
        p = window.purchases
        sid = db.fetch_one("SELECT id FROM suppliers WHERE name='مورد الاختبار'")["id"]
        for category, amount, status in (
            ("raw_material", "1000", "Cash"),
            ("purchase_expense", "150", "Cash"),
            ("operating_expense", "2000", "Cash"),
        ):
            p.category_input.setCurrentIndex(p.category_input.findData(category))
            p.supplier_input.setCurrentIndex(0)
            p.amount_input.setText(amount)
            p.payment_status.setCurrentIndex(p.payment_status.findData(status))
            p.save_purchase()
        p.category_input.setCurrentIndex(p.category_input.findData("raw_material"))
        p.supplier_input.setCurrentIndex(p.supplier_input.findData(sid))
        p.amount_input.setText("500")
        p.payment_status.setCurrentIndex(p.payment_status.findData("Credit"))
        p.save_purchase()

        def balance_of(code):
            row = db.fetch_one(
                "SELECT COALESCE(SUM(debit)-SUM(credit),0) v FROM journal_items WHERE account_code=?", (code,))
            return row["v"] or 0
        assert abs(balance_of("1100") - 1500) < 0.01, balance_of("1100")   # inventory
        assert abs(balance_of("5150") - 150) < 0.01, balance_of("5150")    # purchase expense
        assert abs(balance_of("5200") - 2000) < 0.01, balance_of("5200")   # operating expense
    check("purchase categories hit the right accounts", purchases_route_by_category)

    def daily_sales_vat():
        goto("sales")
        s = window.sales
        s.cash_input.setText("1150")
        s.network_input.setText("575")
        s.transfer_input.setText("0")
        app.processEvents()
        assert "1,725.00" in s.preview_label.text(), s.preview_label.text()
        s.save_daily_sales()
        row = db.fetch_one(
            "SELECT SUM(total_amount) t, SUM(vat_amount) v FROM sales")
        assert abs(row["t"] - 1725) < 0.01, row["t"]
        assert abs(row["v"] - 225) < 0.01, row["v"]   # 15% of the 1500 net
    check("daily sales split VAT out of a tax-inclusive total", daily_sales_vat)

    def saving_the_same_day_twice_replaces_it():
        goto("sales")
        s = window.sales
        day = s.date_input.date().toString("yyyy-MM-dd")
        branch = s.branch_input.currentData()
        before_total = db.fetch_one(
            "SELECT COALESCE(SUM(total_amount),0) t FROM sales WHERE branch_id=? AND date=?",
            (branch, day))["t"]
        before_entries = db.fetch_one(
            "SELECT COUNT(*) c FROM journal_entries WHERE description LIKE 'مبيعات يومية%'")["c"]
        s.cash_input.setText("1150")
        s.network_input.setText("0")
        s.transfer_input.setText("0")
        s.save_daily_sales()      # dialogs auto-answer Yes -> replace
        after_total = db.fetch_one(
            "SELECT COALESCE(SUM(total_amount),0) t FROM sales WHERE branch_id=? AND date=?",
            (branch, day))["t"]
        after_entries = db.fetch_one(
            "SELECT COUNT(*) c FROM journal_entries WHERE description LIKE 'مبيعات يومية%'")["c"]
        assert abs(after_total - 1150) < 0.01, f"{before_total} -> {after_total}"
        assert after_entries == before_entries, "replacing a day left a stale journal entry"
    check("re-saving a day replaces it instead of doubling it", saving_the_same_day_twice_replaces_it)

    def sales_returns_reduce_revenue_and_reverse_cleanly():
        """sales_returns already existed in the schema and every report was
        already reading from it, but nothing had a screen to write to it - a
        customer refund had no way to be recorded except reopening the whole
        day's sales entry and retyping the total, which conflates a refund
        with correcting a typo and leaves no record of why the number
        changed. Net revenue (credit minus debit on 4000, not just the
        credit side) must actually drop by the return, and deleting it must
        put the ledger back exactly where it was."""
        def net_revenue():
            return db.fetch_one(
                "SELECT COALESCE(SUM(credit)-SUM(debit),0) c FROM journal_items "
                "WHERE account_code='4000'")["c"]

        goto("sales")
        sales = window.sales
        before = net_revenue()

        sales.return_method_input.setCurrentIndex(sales.return_method_input.findData("Cash"))
        sales.return_amount_input.setText("115")
        sales.return_notes_input.setText("طلب غلط")
        sales.save_sales_return()
        after_return = net_revenue()
        assert abs((before - after_return) - 100) < 0.01, (before, after_return)

        row = db.fetch_one(
            "SELECT amount, vat_amount, journal_entry_id FROM sales_returns ORDER BY id DESC LIMIT 1")
        assert abs(row["amount"] - 100) < 0.01 and abs(row["vat_amount"] - 15) < 0.01
        assert row["journal_entry_id"], "the return has no journal entry linked to it"

        sales.returns_table.setCurrentCell(0, 0)
        sales.delete_selected_return()
        after_delete = net_revenue()
        assert abs(after_delete - before) < 0.01, "deleting the return did not restore revenue"
        assert db.fetch_one("SELECT COUNT(*) c FROM sales_returns")["c"] == 0
    check("a sales return reduces revenue and deleting it reverses cleanly",
          sales_returns_reduce_revenue_and_reverse_cleanly)

    def purchase_return_can_be_deleted_and_reverses_its_entry():
        """Purchase returns had no delete at all - the one correction flow
        every other screen in the app already has."""
        goto("purchases")
        pur = window.purchases
        # rowCount() alone is not a reliable "no rows yet" signal: an empty
        # table shows a single spanning placeholder row (fill_table), so the
        # count that actually matters is the database's, not the widget's.
        returns_before = db.fetch_one("SELECT COUNT(*) c FROM purchase_returns")["c"]
        i = pur.return_category_input.findData("raw_material")
        pur.return_category_input.setCurrentIndex(i)
        pur.return_amount_input.setText("80")
        pur.return_method_input.setCurrentIndex(pur.return_method_input.findData("Cash"))
        before = db.fetch_one(
            "SELECT COALESCE(SUM(credit)-SUM(debit),0) c FROM journal_items "
            "WHERE account_code='1100'")["c"]
        pur.save_purchase_return()
        returns_after = db.fetch_one("SELECT COUNT(*) c FROM purchase_returns")["c"]
        assert returns_after == returns_before + 1, (returns_before, returns_after)

        row = db.fetch_one(
            "SELECT id, journal_entry_id FROM purchase_returns ORDER BY id DESC LIMIT 1")
        assert row["journal_entry_id"], "the return has no journal entry linked to it"

        pur.returns_table.setCurrentCell(0, 0)
        pur.delete_selected_return()
        after = db.fetch_one(
            "SELECT COALESCE(SUM(credit)-SUM(debit),0) c FROM journal_items "
            "WHERE account_code='1100'")["c"]
        assert abs(after - before) < 0.01, "deleting the return did not reverse the inventory account"
        assert db.fetch_one("SELECT COUNT(*) c FROM purchase_returns")["c"] == returns_before
    check("a purchase return can be deleted and reverses its own entry",
          purchase_return_can_be_deleted_and_reverses_its_entry)

    def opening_balances_fix_negative_cash():
        goto("settings")
        st = window.settings
        st.opening_cash.setText("50000")
        st.opening_bank.setText("20000")
        st.opening_inventory.setText("0")
        st.save_opening_balances()
        bs = window.accounting.accounting.get_balance_sheet()
        assert bs["assets"] > 0, f"assets still negative: {bs['assets']}"
        assert bs["balanced"], bs
        # saving again must correct, not stack
        st.save_opening_balances()
        capital = db.fetch_one(
            "SELECT COALESCE(SUM(credit)-SUM(debit),0) v FROM journal_items WHERE account_code='3000'")["v"]
        assert abs(capital - 70000) < 0.01, capital
    check("opening balances lift assets positive and can be corrected", opening_balances_fix_negative_cash)

    def deleting_a_purchase_reverses_its_entry():
        goto("purchases")
        p = window.purchases
        p.category_input.setCurrentIndex(p.category_input.findData("operating_expense"))
        p.supplier_input.setCurrentIndex(0)
        p.description_input.setText("مصروف بالغلط")
        p.amount_input.setText("999")
        p.payment_status.setCurrentIndex(p.payment_status.findData("Cash"))
        p.save_purchase()
        before = db.fetch_one(
            "SELECT COALESCE(SUM(debit)-SUM(credit),0) v FROM journal_items WHERE account_code='5200'")["v"]
        p.table.setCurrentCell(0, 0)
        p.delete_selected_purchase()
        after = db.fetch_one(
            "SELECT COALESCE(SUM(debit)-SUM(credit),0) v FROM journal_items WHERE account_code='5200'")["v"]
        assert abs((before - after) - 999) < 0.01, f"{before} -> {after}"
    check("deleting a purchase also reverses its journal entry", deleting_a_purchase_reverses_its_entry)

    def unbalanced_journal_entries_are_refused():
        """Nothing previously stopped a caller with a mistake in it from
        posting an entry where debit and credit did not match - the trial
        balance would simply stop balancing, with no indication of which
        entry did it. This is the one invariant double-entry bookkeeping
        cannot survive without, enforced once at the write itself."""
        try:
            db.add_journal_entry("2026-01-01", "قيد اختبار غير متوازن", None, [
                {"account_code": "1000", "debit": 100, "credit": 0},
                {"account_code": "4000", "debit": 0, "credit": 40},
            ])
            raise AssertionError("an unbalanced entry was accepted")
        except ValueError:
            pass
        # And a balanced one must still go through normally.
        entry_id = db.add_journal_entry("2026-01-01", "قيد متوازن", None, [
            {"account_code": "1000", "debit": 100, "credit": 0},
            {"account_code": "4000", "debit": 0, "credit": 100},
        ])
        assert entry_id
        db.delete_journal_entry(entry_id)
    check("an unbalanced journal entry is refused", unbalanced_journal_entries_are_refused)

    def foreign_keys_are_actually_enforced():
        """SQLite ships FK checking off by default and does not remember the
        setting in the file - every connection has to turn it on itself, or
        every FOREIGN KEY in schema.sql is decoration. An attendance row
        could previously be inserted against an employee that does not
        exist."""
        conn = db.get_connection()
        try:
            enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            assert enabled == 1, "foreign_keys is not ON for a fresh connection"
            try:
                conn.execute(
                    "INSERT INTO attendance (employee_id, date, status) VALUES (?, ?, ?)",
                    (999999, "2026-01-01", "Present"))
                conn.commit()
                raise AssertionError("an attendance row for a nonexistent employee was accepted")
            except Exception as exc:
                assert "FOREIGN KEY" in str(exc), exc
        finally:
            conn.close()
    check("foreign key constraints are enforced, not just declared",
          foreign_keys_are_actually_enforced)

    def a_crash_mid_write_leaves_nothing_partial():
        """A purchase used to be two separate commits - the journal entry, then
        the purchase row - so a crash between them left a journal entry moving
        money with no invoice anywhere to explain it. Both writes now share one
        transaction; simulating the failure by raising inside the block proves
        the journal entry it already wrote does not survive the rollback."""
        entries_before = db.fetch_one("SELECT COUNT(*) c FROM journal_entries")["c"]
        purchases_before = db.fetch_one("SELECT COUNT(*) c FROM purchases")["c"]
        try:
            with db.transaction() as cursor:
                db.insert_journal_entry(cursor, "2026-01-01", "سيتم التراجع عنه", None, [
                    {"account_code": "1100", "debit": 500, "credit": 0},
                    {"account_code": "1000", "debit": 0, "credit": 500},
                ])
                raise RuntimeError("محاكاة انهيار قبل اكتمال الكتابة")
        except RuntimeError:
            pass
        assert db.fetch_one("SELECT COUNT(*) c FROM journal_entries")["c"] == entries_before, \
            "the journal entry survived a rollback"
        assert db.fetch_one("SELECT COUNT(*) c FROM purchases")["c"] == purchases_before
    check("a failure mid-write rolls back completely, not partially",
          a_crash_mid_write_leaves_nothing_partial)

    def purchase_return_credits_the_right_account():
        """Every return used to credit Inventory (1100) no matter what was
        actually being returned - refunding an operating expense quietly
        shrank the inventory account instead of the expense it was actually
        against."""
        goto("purchases")
        pur = window.purchases
        i = pur.return_category_input.findData("operating_expense")
        assert i >= 0
        pur.return_category_input.setCurrentIndex(i)
        pur.return_amount_input.setText("200")
        pur.return_method_input.setCurrentIndex(pur.return_method_input.findData("Cash"))
        before = db.fetch_one(
            "SELECT COALESCE(SUM(credit),0) c FROM journal_items WHERE account_code='5200'")["c"]
        returns_before = db.fetch_one("SELECT MAX(id) m FROM purchase_returns")["m"] or 0
        pur.save_purchase_return()
        after = db.fetch_one(
            "SELECT COALESCE(SUM(credit),0) c FROM journal_items WHERE account_code='5200'")["c"]
        assert after > before, "the operating-expense account was not credited"
        pur.return_amount_input.clear()
        # Leave the ledger exactly as later checks expect it - this test only
        # needed to prove the routing, not to actually change the books.
        new_row = db.fetch_one(
            "SELECT id, branch_id FROM purchase_returns WHERE id > ?", (returns_before,))
        if new_row:
            entry = db.fetch_one(
                "SELECT id FROM journal_entries WHERE description LIKE 'مرتجع مشتريات%' "
                "ORDER BY id DESC LIMIT 1")
            db.execute_query("DELETE FROM purchase_returns WHERE id = ?", (new_row["id"],))
            if entry:
                db.delete_journal_entry(entry["id"])
        pur.load_purchase_returns()
        pur.load_purchases()
    check("a purchase return credits the account its category actually used",
          purchase_return_credits_the_right_account)

    def credit_note_return_requires_a_supplier():
        """A credit-note return reduces one specific supplier's balance
        (account 2000). Posting one with nobody chosen moved the general
        ledger total with no supplier statement reflecting it, so the two
        stopped matching each other."""
        goto("purchases")
        pur = window.purchases
        pur.return_supplier_input.setCurrentIndex(-1)
        pur.return_amount_input.setText("150")
        pur.return_method_input.setCurrentIndex(pur.return_method_input.findData("CreditNote"))
        before = db.fetch_one("SELECT COUNT(*) c FROM purchase_returns")["c"]
        pur.save_purchase_return()
        after = db.fetch_one("SELECT COUNT(*) c FROM purchase_returns")["c"]
        assert after == before, "a credit-note return posted with no supplier chosen"
        pur.return_amount_input.clear()
    check("a credit-note return without a supplier is refused",
          credit_note_return_requires_a_supplier)

    # ---------------- accounting identities ----------------
    print("\n[accounting]")

    def trial_balance_balances():
        rows = window.accounting.accounting.get_trial_balance()
        debit = sum((r["total_debit"] or 0) for r in rows)
        credit = sum((r["total_credit"] or 0) for r in rows)
        assert abs(debit - credit) < 0.01, f"debit={debit} credit={credit}"
    check("trial balance: total debit == total credit", trial_balance_balances)

    def balance_sheet_balances():
        bs = window.accounting.accounting.get_balance_sheet()
        assert bs["balanced"], bs
        assert abs(bs["assets"] - (bs["liabilities"] + bs["equity"])) < 0.01, bs
    check("balance sheet: assets == liabilities + equity", balance_sheet_balances)

    def every_journal_entry_balances():
        rows = db.fetch_all(
            """SELECT entry_id, ROUND(SUM(debit)-SUM(credit), 2) AS diff
               FROM journal_items GROUP BY entry_id HAVING ABS(diff) > 0.009""")
        assert not rows, [(r["entry_id"], r["diff"]) for r in rows]
    check("every single journal entry is self-balancing", every_journal_entry_balances)

    def report_matches_ledger():
        acc = window.accounting.accounting
        report = acc.get_period_report("2000-01-01", "2100-01-01", None)
        # State at this point: the day's sales were replaced above with 1150
        # cash only -> 1000 net + 150 VAT. Purchases still standing are raw
        # material 1000 (cash) + 500 (credit), 150 freight and 2000 operating;
        # the 999 expense was added and deleted again, so it nets to zero.
        assert abs(report["net_sales"] - 1000) < 0.01, report["net_sales"]
        assert abs(report["cost_of_sales"] - 1650) < 0.01, report["cost_of_sales"]
        assert abs(report["operating_expenses"] - 2000) < 0.01, report["operating_expenses"]
        assert abs(report["gross_profit"] - (1000 - 1650)) < 0.01, report["gross_profit"]
        assert abs(report["net_profit"] - (1000 - 1650 - 2000)) < 0.01, report["net_profit"]
        # Output VAT 150 ; input VAT 150 + 75 + 22.5 + 300 = 547.5
        assert abs(report["output_vat"] - 150) < 0.01, report["output_vat"]
        assert abs(report["input_vat"] - 547.5) < 0.01, report["input_vat"]
        assert abs(report["net_vat"] - (150 - 547.5)) < 0.01, report["net_vat"]
    check("period report figures match the ledger", report_matches_ledger)

    def pdf_export_works():
        goto("reports")
        from PyQt6.QtPrintSupport import QPrinter
        out = os.path.join(tempfile.gettempdir(), "_erp_report_test.pdf")
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(out)
        window.reports._document().print(printer)
        assert os.path.exists(out) and os.path.getsize(out) > 1000
        os.remove(out)
    check("report exports a real PDF", pdf_export_works)

    # ---------------- UI regressions ----------------
    print("\n[ui]")

    def all_buttons_visible():
        """A button is invisible only if *nothing* of it renders - no fill, no
        border, no text. Outlined buttons (used for destructive actions so they
        don't compete with Save) legitimately have a white fill, so testing the
        dominant colour alone would wrongly flag them."""
        bad = []
        for page in pages:
            entry = goto(page)
            for btn in entry["page"].findChildren(QPushButton):
                if not (btn.isVisible() and btn.width() > 20 and btn.height() > 10):
                    continue
                image = render(btn)
                ink = 0
                for y in range(0, image.height(), 2):
                    for x in range(0, image.width(), 2):
                        if not is_near_white(image.pixelColor(x, y).name()):
                            ink += 1
                if ink < 12:
                    bad.append((page, btn.text()[:25], f"{ink} non-white px"))
        assert not bad, bad
    check("no button renders as a blank rectangle", all_buttons_visible)

    def no_stylesheet_leak_onto_labels():
        """A bare `QFrame {...}` rule also matches QLabel (a QFrame subclass) and
        paints a border on every label inside. Detect it by looking for a fully
        coloured top edge on labels."""
        bad = []
        for page in pages:
            entry = goto(page)
            for label in entry["page"].findChildren(QLabel):
                if not label.isVisible() or label.width() < 12 or label.height() < 8:
                    continue
                # Skip labels that give themselves a *visible* border or fill -
                # those are deliberate banners. "border: none" must NOT skip,
                # otherwise the stat-card labels (which explicitly reset their
                # border) would be excluded and the leak this guards against
                # would go undetected.
                own_style = label.styleSheet() or ""
                paints_itself = re.search(
                    r"border\s*:\s*(?!none|0)|background(-color)?\s*:\s*(?!transparent|none)",
                    own_style,
                )
                if paints_itself:
                    continue
                image = render(label)
                top = [image.pixelColor(x, 0) for x in range(0, image.width(), 2)]
                saturated = sum(
                    1 for c in top
                    if (max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue())) > 40
                    and max(c.red(), c.green(), c.blue()) > 60
                )
                if saturated > len(top) * 0.7:
                    bad.append((page, label.text()[:30]))
        assert not bad, bad
    check("no stray borders leaked onto labels", no_stylesheet_leak_onto_labels)

    def dates_are_iso_and_ltr():
        for date_edit in window.findChildren(QDateEdit):
            assert date_edit.displayFormat() == "yyyy-MM-dd", ascii(date_edit.displayFormat())
            assert date_edit.layoutDirection() == Qt.LayoutDirection.LeftToRight
    check("date fields are ISO and not bidi-reversed", dates_are_iso_and_ltr)

    def reachable(widget):
        """Whether the user can actually get to this widget.

        Walking the ancestors matters: the old version of this check skipped a
        whole page as soon as it contained any QScrollArea, so a page with one
        scrollable tab was exempt everywhere. It also has to be a scroll area
        that *can* scroll - one whose content already fits hides nothing, and
        one that cannot reach the widget is no help at all.
        """
        node = widget.parentWidget()
        while node is not None and node is not window:
            if isinstance(node, QScrollArea):
                return node.verticalScrollBar().maximum() > 0
            node = node.parentWidget()
        return False

    def nothing_is_unreachable():
        """Checked at 1024x600 as well as the normal size. The owner reported
        content he could not reach until he enlarged the window, and on a small
        laptop the accounting table was squeezed to 78px - one row - while the
        purchases list got 94px."""
        bad = []
        for width, height in ((1024, 600), (1280, 720)):
            window.resize(width, height)
            for _ in range(4):
                app.processEvents()
            for page in pages + ["settings"]:
                entry = goto(page)
                widget = entry["page"]
                for btn in widget.findChildren(QPushButton):
                    if not btn.isVisible():
                        continue
                    bottom = btn.mapTo(window, btn.rect().bottomLeft()).y()
                    if bottom > window.height() + 4 and not reachable(btn):
                        bad.append((f"{page}@{width}x{height}", "زر " + btn.text()[:22]))
                for table in widget.findChildren(QTableWidget):
                    if table.isVisible() and table.height() < 100 and not reachable(table):
                        bad.append((f"{page}@{width}x{height}", f"جدول {table.height()}px"))
        window.resize(1280, 720)
        for _ in range(4):
            app.processEvents()
        assert not bad, bad
    check("no page hides content below the window", nothing_is_unreachable)

    def trading_account_result_is_fully_reachable():
        """The trading account result is ten lines long with nothing to bound
        its height, and had no scroll area of its own. A screenshot showed it
        cut off flush against the bottom of the window mid-line, before
        reaching صافي المبيعات or gross profit - the number the whole
        calculation exists to produce."""
        from PyQt6.QtWidgets import QScrollArea

        def inside_scroll_area(widget):
            node = widget.parentWidget()
            while node is not None:
                if isinstance(node, QScrollArea):
                    return True
                node = node.parentWidget()
            return False

        goto("accounting")
        acc = window.accounting
        acc.opening_inventory_input.setValue(1000)
        acc.closing_inventory_input.setValue(200)
        acc.refresh_trading_account()
        assert inside_scroll_area(acc.trading_box), \
            "the trading account result has no scroll area of its own"
        assert "مجمل الربح" in acc.trading_box.text(), "the result text looks incomplete"
        assert inside_scroll_area(acc.income_box), \
            "the income statement result has no scroll area of its own"
    check("the trading account result can be scrolled to in full",
          trading_account_result_is_fully_reachable)

    def every_page_opens():
        for page in pages:
            entry = goto(page)
            assert entry["page"].isVisible(), page
    check("every page opens without error", every_page_opens)

    def no_english_shown_to_the_user():
        """The owner asked for an Arabic-only interface. Stored values stay
        English (CHECK constraints and every query depend on them) but nothing
        English may reach a label, a dropdown entry or a table cell."""
        from PyQt6.QtWidgets import QComboBox, QTableWidget
        banned = [
            "Present", "Absent", "Cash", "Credit", "Bank", "POS", "Transfer",
            "Asset", "Liability", "Equity", "Revenue", "Expense",
            "Deduction", "Advance", "Bonus", "CreditNote",
            "Input VAT", "Output VAT", "COGS", "Mini ERP",
        ]
        found = []

        def scan(text, where):
            if not text:
                return
            for word in banned:
                if word in text:
                    found.append((where, text[:45]))
                    return

        scan(window.windowTitle(), "window title")
        for page in pages + ["settings"]:
            entry = goto(page)
            widget = entry["page"]
            for label in widget.findChildren(QLabel):
                if label.isVisible():
                    scan(label.text(), f"{page}/label")
            for btn in widget.findChildren(QPushButton):
                if btn.isVisible():
                    scan(btn.text(), f"{page}/button")
            for combo in widget.findChildren(QComboBox):
                for i in range(combo.count()):
                    scan(combo.itemText(i), f"{page}/dropdown")
            for table in widget.findChildren(QTableWidget):
                for r in range(table.rowCount()):
                    for c in range(table.columnCount()):
                        item = table.item(r, c)
                        if item:
                            scan(item.text(), f"{page}/table")
                    if r > 30:
                        break
                for c in range(table.columnCount()):
                    header = table.horizontalHeaderItem(c)
                    if header:
                        scan(header.text(), f"{page}/header")
        assert not found, found
    check("nothing English is shown to the user", no_english_shown_to_the_user)

    def dpi_scaling_is_pinned_explicitly():
        """A customer reported the same .exe looking a different size on a
        second machine. Left unset, the rounding policy Qt uses to turn a
        display's scale factor (100%/125%/150%, all ordinary on real laptops)
        into whole logical pixels is whatever that Qt build happens to default
        to - which is not guaranteed to be the same policy on every customer's
        machine. Pinning it explicitly makes the layout follow the display's
        actual scale instead of whatever the platform guessed."""
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtCore import Qt as QtCore
        policy = QGuiApplication.highDpiScaleFactorRoundingPolicy()
        assert policy == QtCore.HighDpiScaleFactorRoundingPolicy.PassThrough, policy
    check("DPI scaling is pinned so window sizing is consistent across machines",
          dpi_scaling_is_pinned_explicitly)

    def absurd_amounts_cannot_wreck_the_books():
        """A held-down key put 99,999,999,999,999 into a day's sales. The entry
        was balanced, so the trial balance still said متوازن and nothing warned
        anyone, while every report and the balance sheet were quietly ruined.
        Silent corruption is the worst thing this program can do."""
        from logic.accounting import AccountingLogic

        def total_debit():
            return sum(r["total_debit"] or 0
                       for r in AccountingLogic(db).get_trial_balance())

        goto("sales")
        sales = window.sales
        before = total_debit()
        sales.date_input.setDate(QDate.currentDate().addDays(-900))
        sales.cash_input.setText("99999999999999")
        sales.network_input.setText("0")
        sales.transfer_input.setText("0")
        sales.save_daily_sales()
        assert abs(total_debit() - before) < 0.01, "an absurd sale reached the ledger"

        # The same guard has to hold on every money field, not just this one.
        goto("purchases")
        window.purchases.amount_input.setText("88888888888888")
        window.purchases.description_input.setText("اختبار")
        window.purchases.save_purchase()
        assert abs(total_debit() - before) < 0.01, "an absurd purchase reached the ledger"
    check("an absurd amount is refused instead of silently wrecking the books",
          absurd_amounts_cannot_wreck_the_books)

    def arabic_digits_are_accepted():
        """An Arabic keyboard produces ١٢٣. Refusing it makes a program written
        for Arabic speakers look broken."""
        from logic.money import parse_money
        assert parse_money("١٢٣٤") == 1234
        assert parse_money("1,500") == 1500        # people write separators
        assert parse_money("١٢٫٥") == 12.5         # Arabic decimal separator
        assert parse_money("") == 0
        for bad in ("abc", "-5", "1.2.3", "99999999999999"):
            try:
                parse_money(bad)
                raise AssertionError(f"{bad!r} was accepted")
            except ValueError:
                pass
    check("Arabic digits and separators are understood", arabic_digits_are_accepted)

    # ---------------- what actually ships ----------------
    print("\n[release]")

    def shipped_database_is_empty():
        """The evaluation copy must arrive with no data in it - the owner types
        his own. Only the chart of accounts and one renameable branch ship."""
        fresh_path = DB_PATH.replace(".db", "_fresh.db")
        if os.path.exists(fresh_path):
            os.remove(fresh_path)
        fresh = DBManager(fresh_path)
        try:
            for table in ("employees", "suppliers", "sales", "purchases",
                          "attendance", "journal_entries", "journal_items",
                          "payroll_runs", "supplier_payments", "app_settings"):
                count = fresh.fetch_one(f"SELECT COUNT(*) AS c FROM {table}")["c"]
                assert count == 0, f"{table} ships with {count} rows"
            assert fresh.fetch_one("SELECT COUNT(*) AS c FROM branches")["c"] == 1
            assert fresh.fetch_one("SELECT COUNT(*) AS c FROM chart_of_accounts")["c"] > 0
        finally:
            os.remove(fresh_path)
    check("the shipped database contains no data", shipped_database_is_empty)

    def trial_expires_and_survives_a_reset():
        """A week of use, then it stops - and deleting the database does not
        buy a second week, because the marker file remembers the install date."""
        import datetime as dt
        import json
        import tempfile
        import logic.trial as trial

        sandbox = tempfile.mkdtemp(prefix="_erp_trial_")
        saved_env = (os.environ.get("XDG_CONFIG_HOME"), os.environ.get("APPDATA"))
        os.environ["XDG_CONFIG_HOME"] = sandbox
        os.environ.pop("APPDATA", None)          # would otherwise win on Windows
        trial_db_path = DB_PATH.replace(".db", "_trial.db")
        real_date = dt.date

        class FrozenDate(real_date):
            offset = 0

            @classmethod
            def today(cls):
                return real_date.today() + dt.timedelta(days=cls.offset)

        trial.date = FrozenDate
        try:
            def fresh_db():
                if os.path.exists(trial_db_path):
                    os.remove(trial_db_path)
                return DBManager(trial_db_path)

            db_a = fresh_db()
            FrozenDate.offset = 0
            allowed, days_left, _ = trial.TrialManager(db_a).check()
            assert allowed and days_left == trial.TRIAL_DAYS, (allowed, days_left)

            FrozenDate.offset = 3
            allowed, days_left, _ = trial.TrialManager(db_a).check()
            assert allowed and days_left == trial.TRIAL_DAYS - 3, (allowed, days_left)

            FrozenDate.offset = trial.TRIAL_DAYS + 1
            allowed, _, message = trial.TrialManager(db_a).check()
            assert not allowed and message, "trial did not expire"

            # A brand new database on day 8 must still be expired.
            db_b = fresh_db()
            allowed, _, _ = trial.TrialManager(db_b).check()
            assert not allowed, "deleting the database reset the trial"

            # Winding the clock back is detected rather than rewarded.
            os.remove(os.path.join(sandbox, "RestaurantERP", "licence.json"))
            db_c = fresh_db()
            FrozenDate.offset = 2
            trial.TrialManager(db_c).check()
            FrozenDate.offset = -20
            allowed, _, _ = trial.TrialManager(db_c).check()
            assert not allowed, "rolling the clock back handed out a fresh trial"

            marker = json.load(open(os.path.join(sandbox, "RestaurantERP", "licence.json")))
            assert marker.get("tampered") is True
        finally:
            trial.date = real_date
            for key, value in zip(("XDG_CONFIG_HOME", "APPDATA"), saved_env):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            if os.path.exists(trial_db_path):
                os.remove(trial_db_path)
            shutil.rmtree(sandbox, ignore_errors=True)
    check("the trial expires and cannot be reset", trial_expires_and_survives_a_reset)

    def paying_unlocks_it_without_losing_anything():
        """The whole promise of activation: the books survive it.

        A customer who pays on day 21 must get his program back with every
        number still in it. If activation reset anything, or if he had to
        reinstall to apply the key, the sale would cost him his accounts."""
        import datetime as dt
        import tempfile
        import logic.trial as trial
        import logic.licence as licence

        sandbox = tempfile.mkdtemp(prefix="_erp_licence_")
        saved = (os.environ.get("XDG_CONFIG_HOME"), os.environ.get("APPDATA"),
                 os.environ.get("RESTAURANT_ERP_SECRET"))
        os.environ["XDG_CONFIG_HOME"] = sandbox
        os.environ.pop("APPDATA", None)
        real_date = dt.date
        licence_db_path = DB_PATH.replace(".db", "_licence.db")

        class FrozenDate(real_date):
            offset = 0

            @classmethod
            def today(cls):
                return real_date.today() + dt.timedelta(days=cls.offset)

        trial.date = FrozenDate
        try:
            if os.path.exists(licence_db_path):
                os.remove(licence_db_path)
            fresh = DBManager(licence_db_path)

            # The customer works for a while.
            fresh.execute_query(
                "INSERT INTO suppliers (name, opening_balance) VALUES (?, ?)",
                ("مورد قبل التفعيل", 5000),
            )
            before = fresh.fetch_one("SELECT COUNT(*) c FROM suppliers")["c"]

            # Record day one first. Without this the first check ever made is
            # the one taken from the future, so that becomes the install date
            # and the trial has not started, let alone expired.
            FrozenDate.offset = 0
            assert trial.TrialManager(fresh).check()[0], "day one was not allowed"

            FrozenDate.offset = trial.TRIAL_DAYS + 1
            allowed, _, message = trial.TrialManager(fresh).check()
            assert not allowed and message, "the trial did not expire"

            code = licence.device_code(fresh)
            assert len(code) == 8, code

            # A key for someone else's machine must not open this one.
            assert not licence.activate(fresh, licence.key_for_device("ZZZZ2345"))
            assert not licence.activate(fresh, "AAAA-BBBB-CCCC-DDDD")
            assert not licence.is_activated(fresh)

            key = licence.key_for_device(code)
            assert licence.activate(fresh, key), "the correct key was rejected"
            assert licence.is_activated(fresh)

            # However it comes back from WhatsApp.
            assert licence.is_valid(code, key.lower().replace("-", " "))

            # Time no longer matters.
            FrozenDate.offset = 900
            assert licence.is_activated(fresh), "activation expired with the trial"

            # And nothing was lost.
            after = fresh.fetch_one("SELECT COUNT(*) c FROM suppliers")["c"]
            assert after == before, f"activation lost data: {before} -> {after}"

            # Restoring a backup over the database must not deactivate a paid
            # copy - the licence is remembered outside it too.
            os.remove(licence_db_path)
            restored = DBManager(licence_db_path)
            assert licence.is_activated(restored), \
                "restoring a backup deactivated a paid copy"
        finally:
            trial.date = real_date
            for name, value in zip(
                    ("XDG_CONFIG_HOME", "APPDATA", "RESTAURANT_ERP_SECRET"), saved):
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            if os.path.exists(licence_db_path):
                os.remove(licence_db_path)
            shutil.rmtree(sandbox, ignore_errors=True)
    check("paying unlocks it in place, with every number still there",
          paying_unlocks_it_without_losing_anything)

    def the_expiry_screen_can_actually_activate():
        """Blocking startup with a message and exiting leaves nowhere to type
        the key. The box that stops the customer has to be the box that lets
        him in."""
        from PyQt6.QtWidgets import QLineEdit
        from ui.activation_dialog import ActivationDialog
        import logic.licence as licence

        dialog = ActivationDialog(db, "انتهت المدة")
        try:
            shown = dialog.code_field.text()
            assert shown == licence.device_code(db), shown
            assert dialog.code_field.isReadOnly(), "the device code is editable"
            assert isinstance(dialog.key_field, QLineEdit)

            # A wrong key must say so and must not let the program open.
            dialog.key_field.setText("WRON-GKEY-WRON-GKEY")
            dialog.try_activate()
            assert not dialog.activated
            # isVisibleTo, not isVisible: the dialog is never shown in a
            # headless run, and every child of an unshown window reports itself
            # hidden regardless of what the code did to it.
            assert dialog.status.isVisibleTo(dialog), "no error was shown"
            assert dialog.status.text(), "the error message is empty"

            buttons = [b.text() for b in dialog.findChildren(QPushButton)]
            assert any("تفعيل" in b for b in buttons), buttons
            assert any("نسخ" in b for b in buttons), buttons
        finally:
            dialog.deleteLater()
    check("the expiry screen is where the key is entered",
          the_expiry_screen_can_actually_activate)

    def arabic_day_counts_agree():
        """"20 أيام" is broken Arabic. Numbers 11 and up take the singular."""
        from logic.trial import arabic_days
        assert arabic_days(1) == "يوم واحد"
        assert arabic_days(2) == "يومان"
        assert arabic_days(5) == "5 أيام"
        assert arabic_days(20) == "20 يوماً"
        assert "أيام" not in arabic_days(20)
    check("day counts are written in correct Arabic", arabic_day_counts_agree)

    def manual_ships_and_opens():
        # Navigate here rather than relying on whichever page an earlier check
        # happened to leave open - a widget on a page that is not current is
        # not visible, and this asserted on visibility.
        goto("settings")
        settings = window.settings
        path = settings.manual_path()
        assert os.path.exists(path), f"the manual is missing: {path}"
        assert os.path.getsize(path) > 20000, "the manual looks truncated"
        with open(path, "rb") as handle:
            assert handle.read(5) == b"%PDF-", "the manual is not a PDF"

        button = next(
            b for b in settings.findChildren(QPushButton)
            if "دليل الاستخدام" in b.text()
        )
        assert button.isVisible() and button.isEnabled()

        # Click for real, but intercept the hand-off to the desktop so the test
        # does not spawn a PDF viewer. What is being checked is that the button
        # is wired up and passes the file that actually exists.
        from PyQt6.QtGui import QDesktopServices
        opened = []
        original = QDesktopServices.openUrl
        QDesktopServices.openUrl = staticmethod(
            lambda url: opened.append(url.toLocalFile()) or True
        )
        try:
            button.click()
        finally:
            QDesktopServices.openUrl = original
        # Compare the files, not the strings. On Windows manual_path() comes
        # back with backslashes while QUrl hands it over with forward slashes,
        # so a plain equality check fails on a build that is working perfectly.
        assert len(opened) == 1, opened
        assert os.path.samefile(opened[0], path), (opened[0], path)
    check("the manual is shipped and reachable from the settings page", manual_ships_and_opens)

    def the_manual_is_readable():
        """The customer opened the manual and every glyph was an empty box.

        The build was regenerating the PDF on a headless Windows runner, where
        Qt found no font with Arabic coverage and silently substituted one. The
        job stayed green and shipped a booklet of rectangles. The manual is now
        committed rather than regenerated, and this is the check that the
        committed file is still whole - fonts embedded, so it renders the same
        on a machine that has none of them installed."""
        import subprocess

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # The same verification the build runs, exercised here so a broken
        # manual fails locally too rather than only in CI.
        result = subprocess.run(
            [sys.executable, os.path.join(root, "packaging", "verify_artifacts.py")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        with open(window.settings.manual_path(), "rb") as handle:
            blob = handle.read()
        assert b"FontFile2" in blob or b"FontFile3" in blob or b"FontFile" in blob, \
            "the manual's fonts are not embedded - it will render as empty boxes"

        # And the build must not quietly replace it with a regenerated one.
        workflow = os.path.join(root, ".github", "workflows", "build-windows.yml")
        if os.path.exists(workflow):
            text = open(workflow, encoding="utf-8").read()
            assert "build_manual.py" not in text, \
                "the build regenerates the manual again - that is what broke it"
    check("the manual is readable and the build cannot replace it",
          the_manual_is_readable)

    def packaging_bundles_every_data_file():
        """Files loaded through resource_path() are data, not code, so
        PyInstaller cannot discover them by following imports. Anything missing
        from the spec builds a perfectly clean .exe that then dies on the
        restaurant's machine with a file-not-found - which is the worst place to
        find out. Every call site must be declared in the spec."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec_path = os.path.join(root, "packaging", "restaurant_erp.spec")
        assert os.path.exists(spec_path), "the packaging spec is missing"
        spec = open(spec_path, encoding="utf-8").read()

        wanted = set()
        for folder, _dirs, files in os.walk(root):
            if any(part in folder for part in (".git", "__pycache__", "dist")):
                continue
            for name in files:
                if not name.endswith(".py") or name == "paths.py":
                    continue
                source = open(os.path.join(folder, name), encoding="utf-8").read()
                for call in re.findall(r"resource_path\(([^)]*)\)", source):
                    for literal in re.findall(r"[\"']([^\"']+)[\"']", call):
                        wanted.add(literal)

        assert wanted, "no resource_path call sites found - did the helper move?"
        missing = [item for item in wanted if item not in spec]
        assert not missing, f"not bundled by the spec: {missing}"

        # And the files themselves have to exist to be bundled at all.
        from logic.paths import resource_path
        for path in (resource_path("database", "schema.sql"),
                     resource_path("docs", "دليل-الاستخدام.pdf")):
            assert os.path.exists(path), path
    check("the Windows build bundles every file the app loads", packaging_bundles_every_data_file)

    def sending_a_newer_version_keeps_his_books():
        """The customer asks for a change, gets a newer copy, replaces the old
        program with it - and every number he has entered is still there.

        This is the single most damaging thing this program could get wrong, and
        it is not covered by testing against a database the current code created.
        The database is built from the layout of the *first* released version,
        filled the way a working restaurant fills one, and only then opened with
        the code as it stands today.
        """
        import sqlite3
        from logic.upgrade import backup_before_upgrade, record_version, APP_VERSION

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        old_schema = os.path.join(root, "tests", "fixtures", "schema_v1.sql")
        assert os.path.exists(old_schema), "the old schema fixture is missing"

        workdir = tempfile.mkdtemp(prefix="_erp_upgrade_")
        old_db = os.path.join(workdir, "restaurant_erp.db")
        try:
            conn = sqlite3.connect(old_db)
            conn.executescript(open(old_schema, encoding="utf-8").read())
            cur = conn.cursor()
            cur.execute("INSERT INTO employees (name, job_title, base_salary, "
                        "allowances, branch_id) VALUES ('محمد أحمد','طباخ',5000,500,1)")
            cur.execute("INSERT INTO suppliers (name, opening_balance) "
                        "VALUES ('مورد اللحوم', 20000)")
            for day in range(1, 16):
                cur.execute(
                    "INSERT INTO sales (branch_id, date, total_amount, vat_amount, "
                    "payment_method) VALUES (1,?,?,?,'Cash')",
                    (f"2026-07-{day:02d}", 4600.0, 600.0))
            cur.execute("INSERT INTO purchases (supplier_id, branch_id, date, "
                        "total_amount, vat_amount, payment_status) "
                        "VALUES (1,1,'2026-07-05',2300,300,'Cash')")
            cur.execute("INSERT INTO journal_entries (date, description, branch_id) "
                        "VALUES ('2026-07-01','قيد قديم',1)")
            entry = cur.lastrowid
            cur.execute("INSERT INTO journal_items (entry_id, account_code, debit, "
                        "credit) VALUES (?, '1000', 4600, 0)", (entry,))
            cur.execute("INSERT INTO journal_items (entry_id, account_code, debit, "
                        "credit) VALUES (?, '4000', 0, 4600)", (entry,))
            conn.commit()

            def counts(path):
                c = sqlite3.connect(path)
                try:
                    out = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                           for t in ("employees", "suppliers", "sales", "purchases",
                                     "journal_entries", "journal_items")}
                    out["sales_total"] = c.execute(
                        "SELECT COALESCE(SUM(total_amount),0) FROM sales").fetchone()[0]
                    return out
                finally:
                    c.close()

            before = counts(old_db)
            conn.close()

            import hashlib

            def digest(path):
                with open(path, "rb") as handle:
                    return hashlib.sha256(handle.read()).hexdigest()

            untouched = digest(old_db)

            # The copy must be taken before the migrations run, so this is
            # called on the path, exactly as main.py does it.
            backup = backup_before_upgrade(old_db)
            assert backup and os.path.exists(backup), "no backup was taken"
            assert counts(backup) == before, "the backup is not a faithful copy"
            # Byte-for-byte, not just the same row counts. Comparing counts
            # cannot tell a pre-migration copy from a post-migration one - the
            # migrations do not change how many rows there are - and taking the
            # copy after they have already rewritten the file is the whole bug
            # this is here to prevent.
            assert digest(backup) == untouched, \
                "the backup was taken after the migrations had already run"

            upgraded = DBManager(old_db)
            record_version(upgraded)

            after = counts(old_db)
            assert after == before, f"the upgrade changed the data: {before} -> {after}"

            # Every screen has to open against it, not just the tables survive.
            upgraded_window = MainWindow(upgraded)
            upgraded_window.resize(1280, 720)
            upgraded_window.show()
            app.processEvents()
            try:
                for item in upgraded_window.nav_entries:
                    upgraded_window.set_active_page(item["index"])
                    app.processEvents()
            finally:
                upgraded_window.close()
                upgraded_window.deleteLater()

            # And the books still balance on his data.
            from logic.accounting import AccountingLogic
            rows = AccountingLogic(upgraded).get_trial_balance()
            debit = sum(r["total_debit"] or 0 for r in rows)
            credit = sum(r["total_credit"] or 0 for r in rows)
            assert abs(debit - credit) < 0.01, (debit, credit)

            # Running the same version again must not pile up more backups.
            assert backup_before_upgrade(old_db) is None, \
                "a backup was taken again for the same version"
            assert upgraded.get_setting("app_version") == APP_VERSION
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    check("sending a newer version keeps every number he entered",
          sending_a_newer_version_keeps_his_books)

    def the_icon_is_real_and_usable():
        """The shortcut icon is the first thing the customer sees, before the
        program has run at all.

        The small entries must be BMP, not PNG. PNG inside an .ico is legal and
        every image viewer reads it, but the Windows taskbar ignores those
        entries and falls back to a generic icon - which is what shipped once,
        with a correct-looking icon file that the taskbar refused to draw.
        """
        import struct
        from logic.paths import icon_path

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ico = os.path.join(root, "packaging", "app_icon.ico")
        assert os.path.exists(ico), "the .ico is missing"
        assert os.path.exists(icon_path()), "the runtime PNG icon is missing"

        with open(ico, "rb") as handle:
            blob = handle.read()
        reserved, kind, count = struct.unpack("<HHH", blob[:6])
        assert (reserved, kind) == (0, 1), "not an icon file"

        entries = {}
        for i in range(count):
            head = 6 + 16 * i
            width = blob[head] or 256
            length, offset = struct.unpack("<II", blob[head + 8:head + 16])
            payload = blob[offset:offset + length]
            assert len(payload) == length, f"entry {width} is truncated"
            entries[width] = payload

        for required in (16, 32, 256):
            assert required in entries, f"missing the {required}px size: {sorted(entries)}"

        for width, payload in entries.items():
            if width <= 64:
                assert payload[:4] != b"\x89PNG", (
                    f"the {width}px entry is PNG - the taskbar will not draw it")

        # Decode the 16px BMP by hand and confirm it is still a picture rather
        # than a flat blob: at that size a design either survives or it does not.
        payload = entries[16]
        header = struct.unpack("<IiiHHIIiiII", payload[:40])
        width, doubled_height, bpp = header[1], header[2], header[4]
        height = doubled_height // 2
        assert (width, height, bpp) == (16, 16, 32), (width, height, bpp)
        pixels = payload[40:40 + width * height * 4]
        shades = {pixels[i:i + 3] for i in range(0, len(pixels), 4)}
        assert len(shades) > 6, f"the 16px icon is a flat blob ({len(shades)} shades)"

        # And the running window must carry it, or the taskbar shows Python's.
        assert not app.windowIcon().isNull(), "the application has no window icon"
    check("the shortcut icon is a real multi-size icon and survives 16px",
          the_icon_is_real_and_usable)

    print("\n" + "=" * 52)
    if failures:
        print(f"FAILED ({len(failures)}): {failures}")
    else:
        print("ALL CHECKS PASSED")
    print("=" * 52)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
