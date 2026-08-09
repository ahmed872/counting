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
    QTableWidget, QFrame,
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
    from main import apply_app_icon, install_arabic_dialog_buttons
    apply_app_icon(app)
    install_arabic_dialog_buttons(app)
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

    pages = ["dashboard", "sales", "hr", "purchases", "suppliers", "customers", "reports",
             "accounting", "other_balances"]

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

    def newest_journal_entry_id():
        return db.fetch_one("SELECT COALESCE(MAX(id),0) m FROM journal_entries")["m"]

    def delete_journal_entries_created_after(marker):
        """Test-only cleanup: grant_advance() and post_payroll() each post a
        journal entry with no easy handle back to it from here, so entries
        created after a captured id watermark are swept up by id range
        instead of guessed at by description text."""
        for row in db.fetch_all("SELECT id FROM journal_entries WHERE id > ?", (marker,)):
            db.delete_journal_entry(row["id"])

    def future_advance_does_not_leak_into_an_earlier_month():
        """An advance had no date filter at all on it - one granted in August
        was recoverable out of July's payroll, a month before it existed."""
        journal_marker = newest_journal_entry_id()
        emp_id = db.insert_and_return_id(
            "INSERT INTO employees (name, job_title, branch_id, base_salary, allowances) "
            "VALUES (?,?,?,?,?)", ("اختبار السلف", "عامل", 1, 3000, 0))
        window.hr_logic.grant_advance(emp_id, "2026-08-10", 500, "سلفة أغسطس")
        july = next(p for p in window.hr_logic.get_monthly_payroll(7, 2026) if p["id"] == emp_id)
        assert july["advances_recovered"] == 0, july["advances_recovered"]
        # Children before parent, now that foreign keys are actually enforced.
        db.execute_query("DELETE FROM employee_deductions WHERE employee_id = ?", (emp_id,))
        db.execute_query("DELETE FROM employees WHERE id = ?", (emp_id,))
        delete_journal_entries_created_after(journal_marker)
    check("an advance is not recovered from a month before it was granted",
          future_advance_does_not_leak_into_an_earlier_month)

    def advance_bigger_than_salary_never_makes_net_pay_negative():
        """An advance larger than one month's salary used to be recovered in
        full in a single run, driving net pay negative - paying someone to
        have been advanced money - and the whole advance was marked settled
        regardless, so the unrecovered remainder silently vanished from the
        books."""
        journal_marker = newest_journal_entry_id()
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
        delete_journal_entries_created_after(journal_marker)
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

    def terminated_employee_still_counted_in_the_month_they_worked():
        """The owner deactivating someone used to drop them from payroll
        immediately, including an unposted PAST month they had actually
        worked - is_active alone cannot tell "gone before this month" from
        "gone during/after it"."""
        emp_id = db.insert_and_return_id(
            "INSERT INTO employees (name, job_title, branch_id, base_salary, allowances, "
            "is_active, terminated_date) VALUES (?,?,?,?,?,?,?)",
            ("موظف منتهي الخدمة", "عامل", 1, 3000, 0, 0, "2026-03-20"))
        march = next((p for p in window.hr_logic.get_monthly_payroll(3, 2026) if p["id"] == emp_id), None)
        assert march is not None, "an employee terminated mid-month is missing from that month's payroll"
        april = next((p for p in window.hr_logic.get_monthly_payroll(4, 2026) if p["id"] == emp_id), None)
        assert april is None, "a terminated employee still appears in a month entirely after their last day"
        db.execute_query("DELETE FROM employees WHERE id = ?", (emp_id,))
    check("an employee terminated mid-month is still counted in that month's payroll",
          terminated_employee_still_counted_in_the_month_they_worked)

    def posted_payroll_is_a_frozen_snapshot():
        """Once a month is posted, the journal entry it produced is fixed -
        the screen must keep showing what was actually posted, not silently
        drift if attendance or a deduction for that same month is edited
        afterwards."""
        journal_marker = newest_journal_entry_id()
        emp_id = db.insert_and_return_id(
            "INSERT INTO employees (name, job_title, branch_id, base_salary, allowances) "
            "VALUES (?,?,?,?,?)", ("لقطة الرواتب المرحلة", "عامل", 1, 3000, 0))
        window.hr_logic.record_attendance(emp_id, "2026-04-05", "Absent")
        window.hr_logic.post_payroll(4, 2026)

        snapshot_before = next(p for p in window.hr_logic.get_posted_payroll(4, 2026) if p["id"] == emp_id)
        assert snapshot_before["absent_days"] == 1, snapshot_before["absent_days"]
        assert abs(snapshot_before["net_salary"] - 2900) < 0.01, snapshot_before["net_salary"]

        # Edit the same month's attendance after posting.
        window.hr_logic.record_attendance(emp_id, "2026-04-06", "Absent")
        live_after = next(p for p in window.hr_logic.get_monthly_payroll(4, 2026) if p["id"] == emp_id)
        assert live_after["absent_days"] == 2, \
            "sanity check: the live recalculation should see the new absence"

        snapshot_after = next(p for p in window.hr_logic.get_posted_payroll(4, 2026) if p["id"] == emp_id)
        assert snapshot_after["absent_days"] == 1, \
            "the posted snapshot changed after editing attendance for that month"
        assert abs(snapshot_after["net_salary"] - 2900) < 0.01, snapshot_after["net_salary"]

        db.execute_query("DELETE FROM payroll_run_items WHERE employee_id = ?", (emp_id,))
        db.execute_query("DELETE FROM payroll_runs WHERE month=4 AND year=2026 AND "
                          "(SELECT COUNT(*) FROM payroll_run_items WHERE run_id=payroll_runs.id)=0")
        db.execute_query("DELETE FROM attendance WHERE employee_id = ?", (emp_id,))
        db.execute_query("DELETE FROM employees WHERE id = ?", (emp_id,))
        delete_journal_entries_created_after(journal_marker)
    check("a posted month's payroll is a frozen snapshot, not a live recalculation",
          posted_payroll_is_a_frozen_snapshot)

    def payroll_table_shows_every_employee_not_just_the_first_few():
        """The owner's own screenshot: three employees in ملخص الرواتب,
        only two visible - the table was boxed into a fixed height with its
        own small internal scrollbar. It must now grow to fit every row
        (fit_table_height), with the page around it scrolling instead."""
        emp_ids = []
        for i in range(3):
            emp_ids.append(db.insert_and_return_id(
                "INSERT INTO employees (name, job_title, branch_id, base_salary, allowances) "
                "VALUES (?,?,?,?,?)", (f"موظف جدول الرواتب {i}", "عامل", 1, 3000, 0)))
        try:
            goto("hr")
            hr = window.hr
            from PyQt6.QtWidgets import QTabWidget
            tabs = hr.findChild(QTabWidget)
            for i in range(tabs.count()):
                if tabs.tabText(i) == "الرواتب":
                    tabs.setCurrentIndex(i)
            # An unposted month: the current month was already posted by an
            # earlier check, and a posted month shows its frozen snapshot,
            # not these employees created just now.
            hr.payroll_month.setCurrentIndex(hr.payroll_month.findData(9))
            hr.payroll_year.setText("2026")
            hr.refresh_payroll()
            for _ in range(3):
                app.processEvents()

            assert hr.payroll_table.verticalScrollBar().maximum() == 0, \
                "the payroll table still needs its own internal scrollbar"
            assert hr.payroll_table.rowCount() >= 3, hr.payroll_table.rowCount()

            names_shown = {hr.payroll_table.item(r, 0).text() for r in range(hr.payroll_table.rowCount())}
            for i in range(3):
                assert f"موظف جدول الرواتب {i}" in names_shown, \
                    f"موظف جدول الرواتب {i} is in the table's data but not shown"

            # And the row is actually visible on screen, not just present in
            # the model - the whole point of the page-level scroll.
            scroll = None
            node = hr.payroll_table.parentWidget()
            while node is not None:
                if isinstance(node, QScrollArea):
                    scroll = node
                    break
                node = node.parentWidget()
            assert scroll is not None, "the hr page has no page-level scroll area"
        finally:
            for emp_id in emp_ids:
                db.execute_query("DELETE FROM employees WHERE id = ?", (emp_id,))
            hr.payroll_month.setCurrentIndex(QDate.currentDate().month() - 1)
            hr.payroll_year.setText(str(QDate.currentDate().year()))
            window.hr.refresh_payroll()
    check("the payroll summary table shows every employee, not hidden behind its own scrollbar",
          payroll_table_shows_every_employee_not_just_the_first_few)

    def payroll_posted_as_owed_credits_accrued_wages_not_cash():
        """Posting used to always assume the net pay left the register on the
        spot. paid_now=False must credit 2200 (رواتب مستحقة الدفع) instead
        of cash, and settling it later must move the balance from 2200 to
        cash without touching the original salaries-expense entry."""
        journal_marker = newest_journal_entry_id()
        emp_id = db.insert_and_return_id(
            "INSERT INTO employees (name, job_title, branch_id, base_salary, allowances) "
            "VALUES (?,?,?,?,?)", ("موظف رواتب مستحقة", "عامل", 1, 3000, 0))
        # The shared test database already has other active employees by
        # this point in the run, so the run's total is whatever the live
        # calculation says right now, not just this one employee's salary.
        expected_total = sum(p['net_salary'] for p in window.hr_logic.get_monthly_payroll(2, 2026))
        window.hr_logic.post_payroll(2, 2026, paid_now=False)

        cash_moved = db.fetch_one(
            "SELECT COALESCE(SUM(credit),0) v FROM journal_items "
            "WHERE account_code='1000' AND entry_id > ?", (journal_marker,))["v"]
        assert abs(cash_moved) < 0.01, f"cash moved even though paid_now=False ({cash_moved})"

        accrued_after_post = window.accounting.accounting.get_account_balance('2200')
        assert abs(accrued_after_post - expected_total) < 0.01, (accrued_after_post, expected_total)

        goto("hr")
        hr = window.hr
        hr.accrued_pay_amount.setText("1000")
        hr.pay_accrued_wages()
        accrued_after_partial = window.accounting.accounting.get_account_balance('2200')
        assert abs(accrued_after_partial - (expected_total - 1000)) < 0.01, accrued_after_partial
        cash_after_partial = db.fetch_one(
            "SELECT COALESCE(SUM(credit),0) v FROM journal_items "
            "WHERE account_code='1000' AND entry_id > ?", (journal_marker,))["v"]
        assert abs(cash_after_partial - 1000) < 0.01, cash_after_partial

        db.execute_query("DELETE FROM accrued_wage_payments")
        run_id = db.fetch_one("SELECT id FROM payroll_runs WHERE month=2 AND year=2026")["id"]
        db.execute_query("DELETE FROM payroll_run_items WHERE run_id = ?", (run_id,))
        db.execute_query("DELETE FROM payroll_runs WHERE id = ?", (run_id,))
        db.execute_query("DELETE FROM employees WHERE id = ?", (emp_id,))
        delete_journal_entries_created_after(journal_marker)
    check("payroll posted as owed credits accrued wages, not cash, and can be settled later",
          payroll_posted_as_owed_credits_accrued_wages_not_cash)

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

    def stopping_a_supplier_hides_it_from_new_purchases_only():
        """The owner asked how to delete a supplier - there was no way to, and
        a hard delete would either be blocked by (or silently orphan) every
        past purchase, payment, and journal entry tied to it. 'Stop dealing
        with' is the safe equivalent: the supplier drops out of the new
        purchase picker, but stays fully visible and payable everywhere else,
        and can be turned back on."""
        goto("suppliers")
        s = window.suppliers
        s.name_input.setText("مورد سيتم إيقافه")
        s.add_supplier()
        sid = db.fetch_one("SELECT id FROM suppliers WHERE name='مورد سيتم إيقافه'")["id"]
        try:
            goto("purchases")
            p = window.purchases
            p.load_suppliers()
            assert p.supplier_input.findData(sid) >= 0, \
                "an active supplier is missing from the new-purchase picker"

            goto("suppliers")
            s.selected_supplier_id = sid
            s.toggle_supplier_active()
            assert db.fetch_one("SELECT is_active FROM suppliers WHERE id=?", (sid,))["is_active"] == 0

            goto("purchases")
            p.load_suppliers()
            assert p.supplier_input.findData(sid) < 0, \
                "a stopped supplier still appears in the new-purchase picker"

            # Still payable and still shown in the full list, just marked.
            goto("suppliers")
            s.load_suppliers()
            names = {s.payment_supplier.itemText(i) for i in range(s.payment_supplier.count())}
            assert "مورد سيتم إيقافه" in names, "a stopped supplier can no longer be paid"
            balances = window.accounting.accounting.get_all_supplier_balances()
            stopped = next(b for b in balances if b["id"] == sid)
            assert stopped["is_active"] is False

            # Reactivating brings it back into the new-purchase picker.
            s.selected_supplier_id = sid
            s.toggle_supplier_active()
            assert db.fetch_one("SELECT is_active FROM suppliers WHERE id=?", (sid,))["is_active"] == 1
            goto("purchases")
            p.load_suppliers()
            assert p.supplier_input.findData(sid) >= 0, \
                "reactivating did not bring the supplier back for new purchases"
        finally:
            db.execute_query("DELETE FROM suppliers WHERE id = ?", (sid,))
            goto("suppliers")
            window.suppliers.load_suppliers()
            goto("purchases")
            window.purchases.load_suppliers()
    check("stopping a supplier hides it from new purchases but keeps it payable and reversible",
          stopping_a_supplier_hides_it_from_new_purchases_only)

    def customer_credit_sale_and_collection():
        """The mirror image of the supplier ledger check: a credit sale
        creates a receivable (debit 1400, credit sales+VAT), a collection
        reduces it (debit cash, credit 1400) - and both must net out."""
        journal_marker = newest_journal_entry_id()
        goto("customers")
        c = window.customers
        c.name_input.setText("عميل الاختبار")
        c.opening_balance_input.setText("0")
        c.add_customer()
        cid = db.fetch_one("SELECT id FROM customers WHERE name='عميل الاختبار'")["id"]
        c.selected_customer_id = cid

        c.sale_amount.setText("1150")  # VAT-inclusive: 1000 net + 150 VAT
        c.record_credit_sale()
        balance = window.accounting.accounting.get_customer_statement(cid)["balance"]
        assert abs(balance - 1150) < 0.01, balance

        c.collect_amount.setText("400")
        c.record_collection()
        balance = window.accounting.accounting.get_customer_statement(cid)["balance"]
        assert abs(balance - 750) < 0.01, balance

        receivable_net = db.fetch_one(
            "SELECT COALESCE(SUM(debit),0) - COALESCE(SUM(credit),0) v FROM journal_items "
            "WHERE account_code='1400' AND entry_id > ?", (journal_marker,))["v"]
        assert abs(receivable_net - 750) < 0.01, \
            "account 1400 does not match the customer's own statement"

        db.execute_query("DELETE FROM customer_payments WHERE customer_id = ?", (cid,))
        db.execute_query("DELETE FROM customer_sales WHERE customer_id = ?", (cid,))
        db.execute_query("DELETE FROM customers WHERE id = ?", (cid,))
        delete_journal_entries_created_after(journal_marker)
    check("a credit sale to a customer creates a receivable that collection reduces",
          customer_credit_sale_and_collection)

    def overcollecting_a_customer_asks_first():
        """Same guard as overpaying a supplier, mirrored: collecting more
        than a customer owes is almost always a typo and must not go
        through silently."""
        journal_marker = newest_journal_entry_id()
        goto("customers")
        c = window.customers
        c.name_input.setText("عميل التحصيل الزائد")
        c.opening_balance_input.setText("100")
        c.add_customer()
        cid = db.fetch_one("SELECT id FROM customers WHERE name='عميل التحصيل الزائد'")["id"]
        c.reload_customer_picker(window.accounting.accounting.get_all_customer_balances())
        c.active_customer.setCurrentIndex(c.active_customer.findData(cid))
        app.processEvents()

        asked = []
        original = QMessageBox.question
        QMessageBox.question = staticmethod(
            lambda *a, **k: asked.append(a[1]) or QMessageBox.StandardButton.No)
        try:
            before = db.fetch_one("SELECT COUNT(*) c FROM customer_payments")["c"]
            c.collect_amount.setText("999999")
            c.record_collection()
            assert asked, "an over-collection was accepted without asking"
            after = db.fetch_one("SELECT COUNT(*) c FROM customer_payments")["c"]
            assert after == before, "answering no still recorded the collection"
        finally:
            QMessageBox.question = original
            db.execute_query("DELETE FROM customers WHERE id = ?", (cid,))
            delete_journal_entries_created_after(journal_marker)
    check("collecting more than a customer owes asks before going through",
          overcollecting_a_customer_asks_first)

    def stopping_a_customer_warns_on_new_credit_sales_only():
        """The mirror of the supplier stop/reactivate toggle: a stopped
        customer is warned about (not silently blocked, since settling a
        final balance can still need one more invoice) before a new credit
        sale, but collection and the statement keep working normally."""
        goto("customers")
        c = window.customers
        c.name_input.setText("عميل سيتم إيقافه")
        c.add_customer()
        cid = db.fetch_one("SELECT id FROM customers WHERE name='عميل سيتم إيقافه'")["id"]
        try:
            c.selected_customer_id = cid
            c.toggle_customer_active()
            assert db.fetch_one("SELECT is_active FROM customers WHERE id=?", (cid,))["is_active"] == 0

            asked = []
            original = QMessageBox.question
            QMessageBox.question = staticmethod(
                lambda *a, **k: asked.append(a[1]) or QMessageBox.StandardButton.No)
            try:
                c.sale_amount.setText("115")
                c.record_credit_sale()
                assert asked, "a credit sale to a stopped customer was accepted without asking"
            finally:
                QMessageBox.question = original

            c.selected_customer_id = cid
            c.toggle_customer_active()
            assert db.fetch_one("SELECT is_active FROM customers WHERE id=?", (cid,))["is_active"] == 1
        finally:
            db.execute_query("DELETE FROM customer_sales WHERE customer_id = ?", (cid,))
            db.execute_query("DELETE FROM customers WHERE id = ?", (cid,))
    check("stopping a customer warns before a new credit sale but never blocks collection",
          stopping_a_customer_warns_on_new_credit_sales_only)

    def loan_received_and_repaid():
        """A loan increases cash and the loans liability (2300) together;
        a repayment reduces both the liability and cash - cross-checked
        against account 2300 directly, the same rigor as the customer test."""
        journal_marker = newest_journal_entry_id()
        goto("other_balances")
        ob = window.other_balances
        ob.lender_input.setText("بنك الاختبار")
        ob.loan_amount_input.setText("5000")
        ob.record_new_loan()
        loan_id = db.fetch_one("SELECT id FROM loans WHERE lender_name='بنك الاختبار'")["id"]
        assert abs(window.accounting.accounting.get_loan_statement(loan_id)["balance"] - 5000) < 0.01

        ob.selected_loan_id = loan_id
        ob.loan_payment_amount.setText("1200")
        ob.record_loan_payment()
        balance = window.accounting.accounting.get_loan_statement(loan_id)["balance"]
        assert abs(balance - 3800) < 0.01, balance

        loan_net = db.fetch_one(
            "SELECT COALESCE(SUM(credit),0) - COALESCE(SUM(debit),0) v FROM journal_items "
            "WHERE account_code='2300' AND entry_id > ?", (journal_marker,))["v"]
        assert abs(loan_net - 3800) < 0.01, "account 2300 does not match the loan's own statement"

        db.execute_query("DELETE FROM loan_payments WHERE loan_id = ?", (loan_id,))
        db.execute_query("DELETE FROM loans WHERE id = ?", (loan_id,))
        delete_journal_entries_created_after(journal_marker)
    check("a loan received and partly repaid matches account 2300 exactly", loan_received_and_repaid)

    def prepaid_expense_release_matches_target_account():
        """A prepaid expense parks the full amount in 1500 on entry; each
        release moves only the released slice into the real expense account,
        never more than remains, and the remainder stays in 1500."""
        journal_marker = newest_journal_entry_id()
        goto("other_balances")
        ob = window.other_balances
        ob.prepaid_desc_input.setText("إيجار سنة كاملة (اختبار)")
        ob.prepaid_amount_input.setText("1200")
        ob.prepaid_target_input.setCurrentIndex(ob.prepaid_target_input.findData('5200'))
        ob.record_new_prepaid()
        prepaid_id = db.fetch_one(
            "SELECT id FROM prepaid_expenses WHERE description='إيجار سنة كاملة (اختبار)'")["id"]

        remaining = next(r for r in window.accounting.accounting.get_prepaid_expenses_with_balances()
                         if r['id'] == prepaid_id)['remaining']
        assert abs(remaining - 1200) < 0.01, remaining

        ob.selected_prepaid_id = prepaid_id
        ob.release_amount_input.setText("100")
        ob.release_prepaid()
        remaining = next(r for r in window.accounting.accounting.get_prepaid_expenses_with_balances()
                         if r['id'] == prepaid_id)['remaining']
        assert abs(remaining - 1100) < 0.01, remaining

        prepaid_1500_net = db.fetch_one(
            "SELECT COALESCE(SUM(debit),0) - COALESCE(SUM(credit),0) v FROM journal_items "
            "WHERE account_code='1500' AND entry_id > ?", (journal_marker,))["v"]
        assert abs(prepaid_1500_net - 1100) < 0.01, \
            "account 1500 does not match the prepaid expense's own remaining balance"
        expense_5200_debit = db.fetch_one(
            "SELECT COALESCE(SUM(debit),0) v FROM journal_items "
            "WHERE account_code='5200' AND entry_id > ?", (journal_marker,))["v"]
        assert abs(expense_5200_debit - 100) < 0.01, \
            "the released amount was not debited to the target expense account"

        # Trying to release more than remains must be refused, not clamp silently.
        ob.release_amount_input.setText("999999")
        ob.release_prepaid()
        remaining_after = next(r for r in window.accounting.accounting.get_prepaid_expenses_with_balances()
                               if r['id'] == prepaid_id)['remaining']
        assert abs(remaining_after - 1100) < 0.01, \
            "releasing more than remains changed the balance anyway"

        db.execute_query("DELETE FROM prepaid_expense_releases WHERE prepaid_expense_id = ?", (prepaid_id,))
        db.execute_query("DELETE FROM prepaid_expenses WHERE id = ?", (prepaid_id,))
        delete_journal_entries_created_after(journal_marker)
    check("a prepaid expense release matches account 1500 and the target expense account",
          prepaid_expense_release_matches_target_account)

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

        # Leaving البيان blank used to fall back to the raw internal status
        # code ("Cash"/"Credit") instead of a translated label - invisible
        # until the new "كشف حساب" ledger tab started showing raw journal
        # descriptions verbatim, which is exactly what surfaced it.
        descriptions = db.fetch_all(
            "SELECT description FROM journal_entries WHERE description LIKE '% - Cash' "
            "OR description LIKE '% - Credit'")
        assert not descriptions, \
            f"an untranslated payment status leaked into a journal description: {descriptions}"
    check("purchase categories hit the right accounts", purchases_route_by_category)

    def general_ledger_tab_shows_every_posting_with_a_running_balance():
        """كشف حساب (per account, not per supplier/customer): the table must
        show exactly the entries and running balance get_account_ledger
        computes from the same raw journal_items - the same rigor used for
        the loan/prepaid/customer checks above."""
        from ui.formatting import money
        goto("accounting")
        acc_page = window.accounting
        idx = acc_page.ledger_account_input.findData('1100')
        assert idx >= 0, "account 1100 is missing from the ledger picker"
        acc_page.ledger_account_input.setCurrentIndex(idx)
        app.processEvents()

        expected = window.accounting.accounting.get_account_ledger('1100')
        assert len(expected['entries']) > 0, "account 1100 should have postings by this point"
        assert acc_page.ledger_table.rowCount() == len(expected['entries']), \
            (acc_page.ledger_table.rowCount(), len(expected['entries']))

        last = expected['entries'][-1]
        last_row = acc_page.ledger_table.rowCount() - 1
        assert acc_page.ledger_table.item(last_row, 1).text() == (last['description'] or "")
        shown_debit = acc_page.ledger_table.item(last_row, 2).text()
        assert shown_debit == (money(last['debit']) if last['debit'] else ""), shown_debit

        assert acc_page.ledger_balance_label.text() == f"الرصيد: {money(expected['balance'])} ريال"
    check("the general ledger tab shows every posting to an account with the right running balance",
          general_ledger_tab_shows_every_posting_with_a_running_balance)

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

    def delivery_app_sales_post_to_the_bank_account_not_cash():
        """تطبيقات التوصيل (هنقرستيشن / جاهز وغيرها) settle to the bank, never
        handed over as physical cash - a new payment_method value the sales
        table's own CHECK constraint has to allow (it used to list only Cash/
        POS/Transfer), routed the same way a bank transfer already is. Uses a
        date outside the 2000-2100 range the accounting checks scan, and
        cleans itself up afterwards - see cashier_number_is_saved_and_shown
        for the same convention."""
        goto("sales")
        s = window.sales
        far_date = "1997-06-15"
        s.date_input.setDate(s.date_input.date().fromString(far_date, "yyyy-MM-dd"))
        s.cash_input.setText("0")
        s.network_input.setText("0")
        s.transfer_input.setText("0")
        s.delivery_input.setText("230")
        s.save_daily_sales()

        stored = db.fetch_one(
            "SELECT id, journal_entry_id, payment_method, total_amount FROM sales WHERE date = ?",
            (far_date,))
        assert stored is not None, "the delivery-apps row was not saved at all"
        assert stored["payment_method"] == "Delivery", stored["payment_method"]
        assert abs(stored["total_amount"] - 230) < 0.01, stored["total_amount"]

        items = db.fetch_all(
            "SELECT account_code, debit, credit FROM journal_items WHERE entry_id = ?",
            (stored["journal_entry_id"],))
        cash_debit = sum(i["debit"] for i in items if i["account_code"] == "1000")
        bank_debit = sum(i["debit"] for i in items if i["account_code"] == "1001")
        assert cash_debit == 0, "a delivery-app sale hit the cash account"
        assert abs(bank_debit - 230) < 0.01, "a delivery-app sale did not hit the bank account"

        match = next(
            (r for r in range(s.table.rowCount()) if s.table.item(r, 0).text() == far_date),
            None)
        assert match is not None, "the saved day is not shown in the history table"
        assert "230.00" in s.table.item(match, 5).text(), \
            "the delivery-apps column in the history table does not show the amount"

        db.execute_query("DELETE FROM sales WHERE date = ?", (far_date,))
        if stored["journal_entry_id"]:
            db.delete_journal_entry(stored["journal_entry_id"])
        # Tests below this one read s.date_input as "today" rather than
        # setting it themselves - restore it, or a later save lands on this
        # far-past date instead of the one those checks expect.
        s.date_input.setDate(QDate.currentDate())
        s.delivery_input.clear()
        s.load_history()
    check("delivery-app sales are their own payment channel and post to the bank, not cash",
          delivery_app_sales_post_to_the_bank_account_not_cash)

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

    def cashier_number_is_saved_and_shown():
        """A reference field only - which register the day's total came off
        of, for matching against a physical Z-report. Does not affect any
        accounting figure, and must not leak into other checks' totals, so
        it uses a date well outside the 2000-2100 range the accounting
        checks scan and cleans itself up afterwards."""
        goto("sales")
        sales = window.sales
        far_date = "1999-01-01"
        sales.date_input.setDate(sales.date_input.date().fromString(far_date, "yyyy-MM-dd"))
        sales.cash_input.setText("500")
        sales.cashier_input.setText("كاشير-3")
        sales.save_daily_sales()

        stored = db.fetch_one(
            "SELECT id, journal_entry_id, cashier_number FROM sales WHERE date = ?", (far_date,))
        assert stored["cashier_number"] == "كاشير-3", stored["cashier_number"]

        match = next(
            (r for r in range(sales.table.rowCount()) if sales.table.item(r, 0).text() == far_date),
            None)
        assert match is not None, "the saved day is not shown in the history table"
        assert sales.table.item(match, 8).text() == "كاشير-3"

        db.execute_query("DELETE FROM sales WHERE date = ?", (far_date,))
        if stored["journal_entry_id"]:
            db.delete_journal_entry(stored["journal_entry_id"])
        sales.load_history()
    check("the cashier/register reference number is saved and shown",
          cashier_number_is_saved_and_shown)

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
        # Net profit now correctly subtracts salaries too - it used to be
        # silently missing from this figure entirely. Read what payroll
        # actually posted rather than hard-coding it a second time, so this
        # check does not itself start guessing at a number that depends on
        # exactly which payroll runs happened to post earlier in the suite.
        salaries = acc.get_salaries_expense("2000-01-01", "2100-01-01")
        assert salaries > 0, "no salary postings found - the payroll test above did not run"
        assert abs(report["salaries_expense"] - salaries) < 0.01, report["salaries_expense"]
        assert abs(report["net_profit"] - (1000 - 1650 - 2000 - salaries)) < 0.01, report["net_profit"]
        # Output VAT 150 ; input VAT 150 + 75 + 22.5 + 300 = 547.5
        assert abs(report["output_vat"] - 150) < 0.01, report["output_vat"]
        assert abs(report["input_vat"] - 547.5) < 0.01, report["input_vat"]
        assert abs(report["net_vat"] - (150 - 547.5)) < 0.01, report["net_vat"]
    check("period report figures match the ledger", report_matches_ledger)

    def dashboard_and_accounting_agree_on_profit():
        """The dashboard's profit card and the accounting tab's income
        statement used to compute profit two different ways for the same
        restaurant on the same day: the income statement's cost of goods sold
        came from an account nothing ever posts to (always zero, so it was
        missing food cost entirely), and the dashboard's own formula never
        subtracted salaries. Two real numbers, silently disagreeing, both
        wrong in different directions. They now share one calculation."""
        acc = window.accounting.accounting
        start, end = "2000-01-01", "2100-01-01"
        period = acc.get_period_report(start, end, None)
        summary = acc.get_financial_summary(start, end)
        assert abs(period["net_profit"] - summary["net_profit"]) < 0.01, \
            (period["net_profit"], summary["net_profit"])
        assert abs(period["net_sales"] - summary["revenue"]) < 0.01
        assert abs(period["cost_of_sales"] - summary["cogs"]) < 0.01
        assert summary["cogs"] > 0, \
            "cost of goods sold is zero - the income statement is still reading a dead account"
    check("the dashboard and the accounting tab show the same profit",
          dashboard_and_accounting_agree_on_profit)

    def printed_report_shows_the_arithmetic_it_uses():
        """The report used to print gross_profit, then المصروفات التشغيلية,
        then a net_profit that had already subtracted salaries the reader was
        never shown - the two lines above it did not add up to the one below
        it. A restaurant owner handing this to his accountant on paper, which
        is exactly what this button is for, would be handing over numbers
        that visibly do not reconcile."""
        goto("reports")
        window.reports.generate_report()
        d = window.accounting.accounting.get_period_report(
            window.reports.resolve_period()[0], window.reports.resolve_period()[1],
            window.reports.branch_input.currentData())
        computed = d["gross_profit"] - d["salaries_expense"] - d["operating_expenses"]
        assert abs(computed - d["net_profit"]) < 0.01, (computed, d["net_profit"])
        html = window.reports.current_report_html()
        assert "الرواتب والأجور" in html, "the printed report does not show the salaries line it subtracts"
    check("the printed report's own numbers add up to the profit it shows",
          printed_report_shows_the_arithmetic_it_uses)

    def printed_report_covers_every_module():
        """The report used to cover only sales/purchases/profit/VAT for the
        chosen period - every other screen (suppliers, customers, loans,
        prepaid expenses, payroll, the balance sheet) had no printed record
        at all. Cross-checks each new section's total against the same live
        data the report itself pulls from, computed fresh right before the
        check so it can never drift from whatever the shared test database
        happens to hold by this point in the run."""
        from ui.formatting import money
        goto("reports")
        html = window.reports.current_report_html()
        for heading in ("الموردون - المستحق عليهم", "العملاء - المستحق لنا",
                        "القروض القائمة", "المصروفات المقدمة المتبقية",
                        "طاقم العمل الحالي", "ملخص الوضع المالي العام"):
            assert heading in html, f"missing report section: {heading}"

        acc = window.accounting.accounting
        expected_suppliers = sum(s['balance'] for s in acc.get_all_supplier_balances() if abs(s['balance']) > 0.01)
        expected_customers = sum(c['balance'] for c in acc.get_all_customer_balances() if abs(c['balance']) > 0.01)
        expected_loans = sum(l['balance'] for l in acc.get_all_loans_with_balances() if abs(l['balance']) > 0.01)
        expected_prepaid = sum(p['remaining'] for p in acc.get_prepaid_expenses_with_balances() if p['remaining'] > 0.01)
        expected_employees = sum(e['gross'] for e in window.hr_logic.get_active_employees_summary())
        bs = acc.get_balance_sheet()

        assert expected_suppliers > 0, "sanity check: the shared test data should include a supplier balance"
        assert expected_employees > 0, "sanity check: the shared test data should include active employees"
        assert money(expected_suppliers) in html, "supplier total in the report does not match live balances"
        assert money(expected_customers) in html, "customer total in the report does not match live balances"
        assert money(expected_loans) in html, "loan total in the report does not match live balances"
        assert money(expected_prepaid) in html, "prepaid total in the report does not match live balances"
        assert money(expected_employees) in html, "employee payroll total in the report does not match live data"
        assert money(bs['assets']) in html, "balance sheet assets total in the report does not match get_balance_sheet()"
        assert money(bs['liabilities']) in html, "balance sheet liabilities total in the report does not match get_balance_sheet()"
        assert ("متوازنة ✓" in html) == bs['balanced'], "the report's balance-sheet status contradicts get_balance_sheet()"
    check("the printed report covers suppliers, customers, loans, prepaid expenses, payroll, and the balance sheet",
          printed_report_covers_every_module)

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
                    if not table.isVisible() or table.height() >= 100:
                        continue
                    # A short table is only a problem if it is actually cut
                    # off the bottom of the window - tables now size to their
                    # own content (see fit_table_height), so a genuinely
                    # empty one is legitimately ~90px and, on a page short
                    # enough to need no scrolling at all, is already fully
                    # on screen. The same gate the button check above uses.
                    bottom = table.mapTo(window, table.rect().bottomLeft()).y()
                    if bottom > window.height() + 4 and not reachable(table):
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

    def all_expiring_documents_are_reachable():
        """The owner reported (with a screenshot) that one of three duplicate
        employees named صابر had 4 expiry alerts, but only some were visible
        and scrolling did not seem to bring the rest up. Reproduced live: the
        table held all 12 rows and its own scrollbar technically worked, but
        was boxed into ~180-270px with a small internal scrollbar easy to
        miss - unlike every other page, which scrolls as a whole with a big,
        high-contrast page scrollbar. The fix makes the alerts table grow to
        fit every row and puts the dashboard page itself inside that same
        page-level scroll area, so there is exactly one way to reach more
        content, not a hidden one nested inside another."""
        import datetime as dt
        today = dt.datetime.now().strftime("%Y-%m-%d")
        emp_ids = []
        for _ in range(3):
            emp_ids.append(db.insert_and_return_id(
                """INSERT INTO employees (name, job_title, base_salary, allowances, is_active,
                       iqama_no, iqama_expiry, passport_no, passport_expiry,
                       work_permit_no, work_permit_expiry, work_card_no, work_card_expiry)
                   VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("صابر (اختبار)", "طباخ", 4000, 0,
                 "111", today, "222", today, "333", today, "444", today)
            ))
        try:
            goto("dashboard")
            dash = window.dashboard
            assert dash.alerts_table.rowCount() >= 12, dash.alerts_table.rowCount()
            # No internal scrollbar hiding rows: the table must be tall enough
            # to show every one of them itself.
            assert dash.alerts_table.verticalScrollBar().maximum() == 0, \
                "the alerts table still needs its own internal scrollbar"

            scroll = None
            node = dash.parentWidget()
            while node is not None:
                if isinstance(node, QScrollArea):
                    scroll = node
                    break
                node = node.parentWidget()
            assert scroll is not None, "the dashboard page has no page-level scroll area"

            last_item = dash.alerts_table.item(dash.alerts_table.rowCount() - 1, 0)
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            app.processEvents()
            app.processEvents()
            row_y = dash.alerts_table.mapTo(
                window, dash.alerts_table.visualItemRect(last_item).topLeft()).y()
            assert 0 <= row_y <= window.height(), \
                f"last alert row is not reachable by scrolling (y={row_y})"
        finally:
            for emp_id in emp_ids:
                db.execute_query("DELETE FROM employees WHERE id = ?", (emp_id,))
    check("every expiring-document alert is reachable, not hidden below a small inner scrollbar",
          all_expiring_documents_are_reachable)

    def employee_table_scrolls_instead_of_truncating():
        """The owner sent a screenshot of the employee list with every column
        so squeezed that dates read "2026-0" and document numbers read "546"
        - Stretch resize mode forces all 12 columns to fit the viewport
        exactly, which also means there is structurally no way to scroll to
        see the rest, since Stretch never lets total column width exceed the
        viewport. Columns must now size to their content and the table must
        gain real horizontal scroll range once that content is wider than
        the viewport."""
        goto("hr")
        hr = window.hr
        emp_ids = []
        try:
            for _ in range(2):
                emp_ids.append(db.insert_and_return_id(
                    """INSERT INTO employees (name, job_title, branch_id, base_salary, allowances,
                           is_active, iqama_no, iqama_expiry, passport_no, passport_expiry,
                           work_permit_no, work_permit_expiry, work_card_no, work_card_expiry)
                       VALUES (?, ?, 1, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("صابر (اختبار)", "مهم", 5000, 1000,
                     "44", "2026-08-08", "5465", "2026-08-08",
                     "5465", "2026-08-08", "55665", "2026-08-08")
                ))
            hr.load_employees()
            app.processEvents()
            app.processEvents()
            row = next(r for r in range(hr.table.rowCount())
                       if hr.table.item(r, 0) and hr.table.item(r, 0).text() == "صابر (اختبار)")
            last_cell = hr.table.item(row, 11)
            assert last_cell.text() == "55665 / 2026-08-08", \
                f"cell text itself is truncated: {last_cell.text()!r}"
            total_width = sum(hr.table.columnWidth(c) for c in range(hr.table.columnCount()))
            assert total_width > hr.table.viewport().width(), \
                "columns still fit the viewport - nothing to verify a scrollbar against"
            assert hr.table.horizontalScrollBar().maximum() > 0, \
                "the table has no horizontal scroll range even though columns overflow it"
        finally:
            for emp_id in emp_ids:
                db.execute_query("DELETE FROM employees WHERE id = ?", (emp_id,))
            hr.load_employees()
    check("the employee list table scrolls to reveal long values instead of truncating them",
          employee_table_scrolls_instead_of_truncating)

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

    # ---------------- login and roles ----------------
    print("\n[auth]")

    def password_hashing_round_trips_and_never_stores_the_clear_text():
        from logic.auth import AuthLogic
        auth = AuthLogic(db)
        uid = auth.create_user("hash_test_user", "correct-horse", "viewer", "اختبار")
        row = db.fetch_one("SELECT password_hash FROM users WHERE id = ?", (uid,))
        assert "correct-horse" not in row["password_hash"], \
            "the clear-text password ended up in the stored hash"
        assert auth.authenticate("hash_test_user", "correct-horse") is not None
        assert auth.authenticate("hash_test_user", "wrong-password") is None, \
            "a wrong password was accepted"
        db.execute_query("DELETE FROM users WHERE id = ?", (uid,))
    check("a password is hashed, never stored in the clear, and a wrong one is rejected",
          password_hashing_round_trips_and_never_stores_the_clear_text)

    def unknown_username_and_wrong_password_look_identical():
        """A login attempt must not be usable to probe which usernames exist -
        both failures return exactly None, with no distinguishing detail."""
        from logic.auth import AuthLogic
        auth = AuthLogic(db)
        assert auth.authenticate("this_user_does_not_exist_at_all", "anything") is None
        uid = auth.create_user("probe_test_user", "real-password", "viewer")
        assert auth.authenticate("probe_test_user", "wrong") is None
        db.execute_query("DELETE FROM users WHERE id = ?", (uid,))
    check("an unknown username and a wrong password fail the same way",
          unknown_username_and_wrong_password_look_identical)

    def deactivated_user_cannot_log_in():
        from logic.auth import AuthLogic
        auth = AuthLogic(db)
        uid = auth.create_user("deactivated_test_user", "somepassword", "viewer")
        assert auth.authenticate("deactivated_test_user", "somepassword") is not None
        auth.set_active(uid, False)
        assert auth.authenticate("deactivated_test_user", "somepassword") is None, \
            "a deactivated user could still log in"
        db.execute_query("DELETE FROM users WHERE id = ?", (uid,))
    check("a deactivated user cannot log in even with the right password",
          deactivated_user_cannot_log_in)

    def default_admin_seats_are_seeded_once_on_an_empty_users_table():
        """Both need a working way in before anyone has created a single
        account by hand - one for whoever supports the program, one for the
        restaurant's own owner - each with a temporary password they are
        forced to change the first time they log in. Must never re-seed (and
        so never reset anything) once a real account already exists."""
        from logic.auth import AuthLogic
        temp_path = DB_PATH + ".auth_seed_test"
        if os.path.exists(temp_path):
            os.remove(temp_path)
        fresh_db = DBManager(temp_path)
        try:
            auth = AuthLogic(fresh_db)
            auth.ensure_default_admins()
            users = auth.list_users()
            assert len(users) == 2, f"expected exactly 2 seeded accounts, found {len(users)}"
            assert all(u["role"] == "admin" for u in users)
            assert all(u["must_change_password"] for u in users), \
                "a seeded admin account did not require a password change"
            usernames = {u["username"] for u in users}
            assert usernames == {"ahmed_admin", "admin"}, usernames

            # Seeding again (simulating a second startup) must not touch
            # anything, or a manually-added account count could get reset.
            auth.ensure_default_admins()
            assert len(auth.list_users()) == 2, "seeding ran a second time"
        finally:
            fresh_db = None
            if os.path.exists(temp_path):
                os.remove(temp_path)
    check("the two admin seats are seeded once on a fresh database, never again",
          default_admin_seats_are_seeded_once_on_an_empty_users_table)

    def an_existing_pre_login_database_gets_the_seed_admins_too():
        """Every customer database that already existed before this feature
        shipped has no users table at all - opening it must not lock them
        out. schema.sql's CREATE TABLE IF NOT EXISTS runs unconditionally on
        every startup (see DBManager.init_db), so the table itself appears
        automatically; this checks the seeding on top of that actually
        happens for a database that starts out with zero users, the same as
        any pre-existing install would."""
        from logic.auth import AuthLogic
        temp_path = DB_PATH + ".auth_upgrade_test"
        if os.path.exists(temp_path):
            os.remove(temp_path)
        import sqlite3
        # A database with real tables but genuinely no users table yet -
        # exactly what every customer's install looks like before this
        # feature shipped to them.
        conn = sqlite3.connect(temp_path)
        conn.execute("CREATE TABLE branches (id INTEGER PRIMARY KEY, name TEXT, location TEXT)")
        conn.execute("INSERT INTO branches (id, name, location) VALUES (1, 'الفرع الرئيسي', '')")
        conn.commit()
        conn.close()
        try:
            upgraded_db = DBManager(temp_path)
            auth = AuthLogic(upgraded_db)
            auth.ensure_default_admins()
            assert len(auth.list_users()) == 2, \
                "an existing pre-login database was not seeded with admin accounts"
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    check("an existing database from before this feature shipped still gets both admin seats",
          an_existing_pre_login_database_gets_the_seed_admins_too)

    def admin_can_create_a_manager_or_viewer_who_can_then_log_in():
        from logic.auth import AuthLogic
        auth = AuthLogic(db)
        uid = auth.create_user("new_manager_test", "startpass1", "manager", "مسئول تجريبي",
                               must_change_password=True)
        user = auth.authenticate("new_manager_test", "startpass1")
        assert user is not None
        assert user["role"] == "manager"
        assert user["must_change_password"] is True
        try:
            auth.create_user("new_manager_test", "anything", "viewer")
            raise AssertionError("a duplicate username was accepted")
        except ValueError:
            pass
        db.execute_query("DELETE FROM users WHERE id = ?", (uid,))
    check("an admin can create a manager/viewer account, and usernames cannot repeat",
          admin_can_create_a_manager_or_viewer_who_can_then_log_in)

    def forced_password_change_replaces_the_temporary_one():
        from logic.auth import AuthLogic
        auth = AuthLogic(db)
        uid = auth.create_user("forced_change_test", "temp-pass-1", "viewer",
                               must_change_password=True)
        auth.set_password(uid, "my-real-password", must_change_password=False)
        assert auth.authenticate("forced_change_test", "temp-pass-1") is None, \
            "the old temporary password still works"
        user = auth.authenticate("forced_change_test", "my-real-password")
        assert user is not None and user["must_change_password"] is False
        db.execute_query("DELETE FROM users WHERE id = ?", (uid,))
    check("setting a new password replaces the temporary one and clears the forced-change flag",
          forced_password_change_replaces_the_temporary_one)

    def changing_your_own_password_needs_the_current_one():
        from logic.auth import AuthLogic
        auth = AuthLogic(db)
        uid = auth.create_user("self_change_test", "old-password", "viewer")
        try:
            auth.change_own_password(uid, "wrong-current-password", "new-password")
            raise AssertionError("changed the password without the correct current one")
        except ValueError:
            pass
        auth.change_own_password(uid, "old-password", "new-password")
        assert auth.authenticate("self_change_test", "new-password") is not None
        db.execute_query("DELETE FROM users WHERE id = ?", (uid,))
    check("changing your own password requires knowing the current one",
          changing_your_own_password_needs_the_current_one)

    def viewer_role_can_look_but_cannot_touch_anything():
        """A مراقب can open every page and read every table, but every button,
        text field, dropdown and date picker that could change something is
        disabled - except on the dashboard and the reports page, neither of
        which has anything that mutates data in the first place."""
        from logic.auth import AuthLogic
        from PyQt6.QtWidgets import QPushButton, QLineEdit, QComboBox
        auth = AuthLogic(db)
        uid = auth.create_user("viewer_role_test", "viewerpass1", "viewer")
        viewer_user = auth.authenticate("viewer_role_test", "viewerpass1")
        viewer_window = MainWindow(db, current_user=viewer_user)
        viewer_window.show()
        app.processEvents()
        app.processEvents()
        try:
            assert not viewer_window.btn_settings.isVisible(), \
                "a viewer can still see the Settings nav button"

            save_btn = next(b for b in viewer_window.sales.findChildren(QPushButton)
                            if b.text() == "حفظ مبيعات اليوم")
            assert not save_btn.isEnabled(), "a viewer's save button on Sales is still enabled"
            assert not viewer_window.sales.cash_input.isEnabled(), \
                "a viewer's amount field on Sales is still enabled"

            add_employee_btn = viewer_window.hr.save_btn
            assert not add_employee_btn.isEnabled(), \
                "a viewer's add-employee button on HR is still enabled"

            # Dashboard and reports are exempt - nothing there mutates data.
            assert viewer_window.dashboard.threshold_input.isEnabled(), \
                "the dashboard's view filter should stay usable for a viewer"
        finally:
            viewer_window.close()
            db.execute_query("DELETE FROM users WHERE id = ?", (uid,))
    check("a viewer sees every page but cannot touch any button or field, except safe filters",
          viewer_role_can_look_but_cannot_touch_anything)

    def manager_role_has_full_operational_access_but_no_settings():
        from logic.auth import AuthLogic
        from PyQt6.QtWidgets import QPushButton
        auth = AuthLogic(db)
        uid = auth.create_user("manager_role_test", "managerpass1", "manager")
        manager_user = auth.authenticate("manager_role_test", "managerpass1")
        manager_window = MainWindow(db, current_user=manager_user)
        manager_window.show()
        app.processEvents()
        app.processEvents()
        try:
            assert not manager_window.btn_settings.isVisible(), \
                "a manager can still see the Settings nav button"
            save_btn = next(b for b in manager_window.sales.findChildren(QPushButton)
                            if b.text() == "حفظ مبيعات اليوم")
            assert save_btn.isEnabled(), "a manager's save button on Sales is disabled"
            assert manager_window.sales.cash_input.isEnabled(), \
                "a manager's amount field on Sales is disabled"
        finally:
            manager_window.close()
            db.execute_query("DELETE FROM users WHERE id = ?", (uid,))
    check("a manager keeps full operational access but never sees Settings",
          manager_role_has_full_operational_access_but_no_settings)

    def admin_sees_settings_and_the_user_list_inside_it():
        from logic.auth import AuthLogic
        auth = AuthLogic(db)
        uid = auth.create_user("admin_role_test", "adminpass1", "admin")
        admin_user = auth.authenticate("admin_role_test", "adminpass1")
        admin_window = MainWindow(db, current_user=admin_user)
        admin_window.show()
        app.processEvents()
        app.processEvents()
        try:
            assert admin_window.btn_settings.isVisible(), "an admin cannot see Settings at all"
            assert hasattr(admin_window.settings, "users_table"), \
                "an admin's Settings page has no user-management box"
        finally:
            admin_window.close()
            db.execute_query("DELETE FROM users WHERE id = ?", (uid,))
    check("an admin sees Settings, including the user-management box inside it",
          admin_sees_settings_and_the_user_list_inside_it)

    def settings_module_hides_the_users_box_for_non_admins():
        """Settings being admin-only is already enforced one level up (the nav
        button itself is hidden - see the viewer/manager checks above), but
        the module does not trust that alone: if it is ever embedded
        somewhere that check does not cover, a non-admin still must not get
        a user-management box with no such check of its own."""
        from ui.settings_module import SettingsModule
        viewer_settings = SettingsModule(db, current_user={"role": "viewer"})
        assert not hasattr(viewer_settings, "users_table"), \
            "a viewer's own Settings module still built the user-management box"
    check("SettingsModule itself never builds the user box for a non-admin",
          settings_module_hides_the_users_box_for_non_admins)

    def login_dialog_end_to_end_including_the_forced_password_change():
        """Drives the actual LoginDialog widget, not just the AuthLogic
        behind it - a wrong password shows an error and stays open; the
        right (temporary) password switches to the change-password step
        instead of logging in directly; a mismatched confirmation is
        rejected; and completing the step actually logs in as that user."""
        from ui.login_dialog import LoginDialog
        from logic.auth import AuthLogic
        auth = AuthLogic(db)
        uid = auth.create_user("login_dialog_test", "temp-pass-1", "viewer",
                               must_change_password=True)
        try:
            dialog = LoginDialog(db)
            dialog.show()
            app.processEvents()
            app.processEvents()
            dialog.username_field.setText("login_dialog_test")
            dialog.password_field.setText("wrong-password")
            dialog.try_login()
            assert dialog.authenticated_user is None, "a wrong password logged in anyway"
            assert dialog.login_status.isVisible()
            assert dialog.stack.currentIndex() == 0, \
                "a wrong password advanced past the login step"

            dialog.password_field.setText("temp-pass-1")
            dialog.try_login()
            assert dialog.authenticated_user is None, \
                "a temporary password logged in without forcing a change"
            assert dialog.stack.currentIndex() == 1, \
                "a temporary password did not move to the change-password step"

            dialog.new_password_field.setText("brand-new-pass")
            dialog.confirm_password_field.setText("does-not-match")
            dialog.try_change_password()
            assert dialog.authenticated_user is None, \
                "mismatched password confirmation was accepted anyway"

            dialog.confirm_password_field.setText("brand-new-pass")
            dialog.try_change_password()
            assert dialog.authenticated_user is not None
            assert dialog.authenticated_user["username"] == "login_dialog_test"
            assert dialog.authenticated_user["must_change_password"] is False

            assert auth.authenticate("login_dialog_test", "temp-pass-1") is None, \
                "the old temporary password still works after the dialog changed it"
            assert auth.authenticate("login_dialog_test", "brand-new-pass") is not None
        finally:
            dialog.close()
            db.execute_query("DELETE FROM users WHERE id = ?", (uid,))
    check("the login dialog rejects a wrong password and forces a real one past a temporary login",
          login_dialog_end_to_end_including_the_forced_password_change)

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

    def every_top_level_window_sets_its_own_taskbar_icon():
        """The owner reported the Windows taskbar showing a generic icon while
        the app was running, even though the title bar and shortcut were both
        correct. A window that only ever inherits QApplication.windowIcon()
        can still show a generic icon on the taskbar specifically - that
        inheritance is not reliable for the native taskbar button icon across
        every Qt/DWM combination. Proven here by clearing the application
        icon and confirming each top-level window still carries its own."""
        from PyQt6.QtGui import QIcon
        from ui.activation_dialog import ActivationDialog
        original = app.windowIcon()
        app.setWindowIcon(QIcon())
        try:
            fresh = MainWindow(db)
            assert not fresh.windowIcon().isNull(), \
                "the main window has no icon of its own once the app-level default is gone"
            fresh.close()
            dialog = ActivationDialog(db, "رسالة اختبار")
            assert not dialog.windowIcon().isNull(), \
                "the activation dialog has no icon of its own once the app-level default is gone"
            dialog.close()
        finally:
            app.setWindowIcon(original)
    check("every top-level window sets its own taskbar icon, not just the application default",
          every_top_level_window_sets_its_own_taskbar_icon)

    def sidebar_nav_never_overlaps_the_trial_banner():
        """The nav list grew to 9 buttons plus 3 group labels with no scroll
        of its own, so on a normal-height window the trial countdown ended
        up overlapping the last nav button instead of either being fully
        visible - Qt does not show an overflowing QVBoxLayout, it silently
        compresses it. Reproduced at the app's own documented minimum size."""
        window.resize(1280, 640)
        window.set_trial_banner(15)
        for _ in range(4):
            app.processEvents()
        try:
            banner = window.trial_banner.geometry()
            settings_btn = window.btn_settings.geometry()
            overlap = not (banner.bottom() <= settings_btn.top() or settings_btn.bottom() <= banner.top())
            assert not overlap, (banner, settings_btn)
            assert window.trial_banner.isVisible() and window.trial_banner.text(), \
                "the trial banner has no text/is hidden at the minimum window size"

            scroll = None
            node = window.btn_other_balances.parentWidget()
            while node is not None:
                if isinstance(node, QScrollArea):
                    scroll = node
                    break
                node = node.parentWidget()
            assert scroll is not None, "the nav list has no scroll area of its own"
        finally:
            window.resize(1440, 900)
            window.set_trial_banner(None)
            for _ in range(4):
                app.processEvents()
    check("the sidebar nav list never overlaps the trial banner, even on a short window",
          sidebar_nav_never_overlaps_the_trial_banner)

    def compact_form_labels_never_get_clipped_illegibly():
        """compact_form()'s caption used a flat 92px minimum with no
        wrapping, sized for short labels like "اسم المورد" - a longer one
        like "رصيد افتتاحي (مستحق له علينا)" rendered as a few letters with
        the rest simply gone, not even an ellipsis. Every label must either
        fit on one line or wrap, never lose text outright."""
        goto("customers")
        long_labels = [lbl for lbl in window.customers.findChildren(QLabel)
                       if "افتتاحي" in lbl.text()]
        assert long_labels, "the opening-balance label is missing entirely"
        for lbl in long_labels:
            assert lbl.wordWrap(), f"label does not wrap and can be clipped: {lbl.text()!r}"

        goto("purchases")
        return_labels = [lbl for lbl in window.purchases.findChildren(QLabel)
                         if "الأصل" in lbl.text()]
        assert return_labels, "the purchase-return category label is missing entirely"
        for lbl in return_labels:
            assert lbl.wordWrap(), f"label does not wrap and can be clipped: {lbl.text()!r}"
    check("compact_form labels wrap instead of being clipped illegibly",
          compact_form_labels_never_get_clipped_illegibly)

    def payroll_month_and_year_do_not_crowd_each_other():
        """Four QFormLayouts in the payroll tab (attendance, deductions,
        payroll, accrued wages) never called setSpacing(), unlike every other
        form in the same file - left at whatever the platform's default
        happens to be (6px, measured). On the owner's machine "الشهر" and
        "السنة" read as sitting right on top of each other. Checks the
        actual gap between the two fields, not just whether setSpacing() was
        called somewhere - QFormLayout.spacing() returns a real number
        either way, so a test on the getter alone could never fail.
        setSpacing(16) measured a 17px gap here versus 7px unset, so the
        assertion sits between the two and catches a regression to either."""
        from PyQt6.QtWidgets import QTabWidget
        goto("hr")
        hr = window.hr
        tabs = hr.findChild(QTabWidget)
        for i in range(tabs.count()):
            if tabs.tabText(i) == "الرواتب":
                tabs.setCurrentIndex(i)
        for _ in range(3):
            app.processEvents()
        gap = hr.payroll_year.geometry().top() - hr.payroll_month.geometry().bottom()
        assert gap >= 12, f"month/year fields are only {gap}px apart - looks crowded"
    check("the payroll month and year fields have a comfortable gap, not crowded together",
          payroll_month_and_year_do_not_crowd_each_other)

    def page_scroll_area_background_matches_the_white_content_card():
        """Every page is wrapped in a QScrollArea (see add_page). Its viewport
        paints the palette's plain grey Window colour by default, not its
        parent's - nothing in a page normally covers every last pixel up to
        the scrollbar's own edge, so that grey showed through as a hard-edged
        rectangular patch sitting inside the white, rounded content card,
        most visible at the very top corner next to the page title, right
        where the owner's screenshot showed it. Checked by actually painting
        the dashboard's page container and sampling a pixel at its top-left
        corner, just inside the QScrollArea but outside any child widget -
        exactly the spot that used to show the leaked grey."""
        goto("dashboard")
        container = window.content_stack.currentWidget()
        assert isinstance(container, QScrollArea), \
            "the dashboard is no longer wrapped in a page-level QScrollArea"
        real_size = container.size()
        container.resize(400, 300)
        for _ in range(3):
            app.processEvents()
        try:
            image = render(container)
            # Just inside the frame, above/left of where dashboard's own content
            # starts - painted only by the scroll area/viewport, never by a widget.
            colour = image.pixelColor(2, 2)
            white = colour.red() >= 250 and colour.green() >= 250 and colour.blue() >= 250
            assert white, f"scroll area corner is {colour.name()}, not white - the grey patch is back"
        finally:
            # This container is the *shared* window's actual page, not a
            # throwaway - left at 400x300, every later test that reads
            # geometry off this same dashboard page inherited the shrunken
            # size instead of the real window size, with no window resize of
            # its own to trigger a recovery.
            container.resize(real_size)
            for _ in range(3):
                app.processEvents()
    check("the page scroll area's background matches the white content card, no grey patch",
          page_scroll_area_background_matches_the_white_content_card)

    def page_widgets_have_no_leftover_grey_gaps():
        """The scroll area's own margin was fixed above, but the page WIDGET
        it wraps (e.g. DashboardModule) also paints the plain grey Window
        colour wherever nothing else covers a pixel - a label's own
        background is transparent, so the spacing between two widgets (the
        page title and the day's status banner, here) showed the same grey
        against the white card. Sampled at the real gap between them, not a
        guessed offset."""
        before = window.size()
        window.resize(1440, 900)   # a known comfortable size - irrelevant to what is being checked
        for _ in range(3):
            app.processEvents()
        try:
            goto("dashboard")
            dash = window.dashboard
            banner_top_local = dash.today_banner.geometry().top()
            gap_point = dash.mapTo(window, dash.today_banner.geometry().topLeft())
            gap_point.setY(gap_point.y() - banner_top_local // 2)
            image = render(window)
            colour = image.pixelColor(gap_point)
            white = colour.red() >= 250 and colour.green() >= 250 and colour.blue() >= 250
            assert white, f"a layout gap on the dashboard is {colour.name()}, not white"
        finally:
            window.resize(before)
            for _ in range(3):
                app.processEvents()
    check("page widgets have no leftover grey gaps between their own children",
          page_widgets_have_no_leftover_grey_gaps)

    def buttons_inside_scrollable_pages_keep_their_styling():
        """Giving the page's own QScrollArea (or its viewport, or the page
        widget itself) a Qt stylesheet - even a trivial "background:
        transparent" one - stops Qt cascading the app-wide QSS to every
        widget below it in that subtree, so a page's own buttons lost their
        blue fill and white text entirely, leaving only a thin outline (an
        actual regression caught while building the delivery-apps sales
        field). The two greyness fixes above must stay palette-only. Checked
        by sampling the centre of a real save button on a scrollable page -
        it must be a solid mid blue, not white."""
        goto("sales")
        save_btn = next(b for b in window.sales.findChildren(QPushButton)
                        if b.text() == "حفظ مبيعات اليوم")
        center = save_btn.mapTo(window, save_btn.rect().center())
        image = render(window)
        colour = image.pixelColor(center)
        near_white = colour.red() > 230 and colour.green() > 230 and colour.blue() > 230
        assert not near_white, f"the save button lost its background fill - now {colour.name()}"
    check("buttons inside scrollable pages keep their blue fill and white text",
          buttons_inside_scrollable_pages_keep_their_styling)

    def dashboard_stat_cards_fit_within_the_minimum_window_width():
        """create_stat_card()'s old 200px minimum meant the dashboard's row
        of 4 needed 836px - more than fits in the content area at the app's
        own documented minimum window size (1040px wide). Horizontal
        scrolling is deliberately off on every page (see add_page), so
        "عدد الموظفين" got pushed past the edge with no way to reach it at
        all - confirmed live. Reproduced at that exact size. (accounting and
        hr have their own, unrelated wide-toolbar overflow at this same
        window size - a pre-existing issue outside what this fix covers.)"""
        before = window.size()
        window.resize(1040, 640)
        for _ in range(3):
            app.processEvents()
        try:
            entry = goto("dashboard")
            page = entry["page"]
            container = window.content_stack.currentWidget()
            available = container.viewport().width() if isinstance(container, QScrollArea) else container.width()
            for card in page.findChildren(QFrame, "statCard"):
                right_edge = card.mapTo(page, card.rect().topRight()).x()
                assert right_edge <= available + 2, \
                    f"a dashboard stat card is pushed past the visible width " \
                    f"({right_edge}px in a {available}px viewport)"
        finally:
            window.resize(before)
            for _ in range(3):
                app.processEvents()
    check("dashboard stat cards fit within the app's own documented minimum window width",
          dashboard_stat_cards_fit_within_the_minimum_window_width)

    def mouse_wheel_over_a_table_still_scrolls_the_page():
        """Every table on a page that scrolls as a whole (see fit_table_height)
        has its own scrollbar turned off - Qt then silently swallows the wheel
        event instead of handing it up to the parent, since the table's own
        (invisible) scrollbar has nothing to do with it either way. The wheel
        did nothing at all while the cursor happened to be over a table -
        which on the dashboard is a large fraction of the page. Reproduced
        with a real QWheelEvent sent straight at the alerts table."""
        from PyQt6.QtGui import QWheelEvent
        from PyQt6.QtCore import QPoint, QPointF
        goto("dashboard")
        fake_alerts = [
            {"name": f"e{i}", "doc_type": "x", "expiry_date": "2026-08-20", "days_left": 11}
            for i in range(20)
        ]
        original_alerts = window.dashboard.hr_logic.get_document_alerts
        window.dashboard.hr_logic.get_document_alerts = lambda days=30: fake_alerts
        try:
            window.dashboard.refresh_dashboard()
            for _ in range(3):
                app.processEvents()
            container = window.content_stack.currentWidget()
            vbar = container.verticalScrollBar()
            assert vbar.maximum() > 0, "the dashboard is not even tall enough to need to scroll"
            before = vbar.value()
            table = window.dashboard.alerts_table
            point = table.viewport().rect().center()
            event = QWheelEvent(
                QPointF(point), QPointF(point), QPoint(0, 0), QPoint(0, -240),
                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase, False,
            )
            app.sendEvent(table.viewport(), event)
            app.processEvents()
            assert vbar.value() > before, \
                "scrolling the mouse wheel over a table does not move the page"
        finally:
            window.dashboard.hr_logic.get_document_alerts = original_alerts
            window.dashboard.refresh_dashboard()
            for _ in range(3):
                app.processEvents()
    check("the mouse wheel still scrolls the page when hovering over a table",
          mouse_wheel_over_a_table_still_scrolls_the_page)

    def transaction_dates_cannot_be_set_in_the_future():
        """A sale, purchase, attendance day, deduction or termination all
        record something that already happened - a mis-set clock or a stray
        calendar click used to be able to post revenue, VAT or a day's wage
        into a month that has not happened yet. Employee document EXPIRY
        dates are the opposite by nature - they are only ever meaningful in
        the future - and must stay uncapped, or the whole expiry-alert
        feature breaks; checked here too, so a blanket future fix never
        creeps onto them by mistake."""
        far_future = QDate.currentDate().addYears(1)

        goto("sales")
        for field in (window.sales.date_input, window.sales.return_date_input):
            field.setDate(far_future)
            assert field.date() <= QDate.currentDate(), \
                f"{field.objectName() or field} accepted a future date"

        goto("purchases")
        for field in (window.purchases.date_input, window.purchases.return_date_input):
            field.setDate(far_future)
            assert field.date() <= QDate.currentDate(), \
                f"{field.objectName() or field} accepted a future date"

        goto("hr")
        for field in (window.hr.attendance_date, window.hr.deduction_date, window.hr.termination_date):
            field.setDate(far_future)
            assert field.date() <= QDate.currentDate(), \
                f"{field.objectName() or field} accepted a future date"

        # Expiry fields must still accept a future date - that is their
        # entire purpose.
        for field in (window.hr.iqama_expiry, window.hr.passport_expiry,
                      window.hr.work_permit_expiry, window.hr.work_card_expiry):
            field.setDate(far_future)
            assert field.date() == far_future, \
                f"{field.objectName() or field} an expiry field must still accept a future date"
    check("transaction dates cannot be set in the future, but expiry dates still can",
          transaction_dates_cannot_be_set_in_the_future)

    def no_page_nests_a_second_scroll_area_inside_the_page_level_one():
        """Every page already scrolls as a single unit (see add_page in
        main_window.py). HR's "الموظفون" tab and two tabs on the accounting
        page each used to wrap their own content in a *second* QScrollArea
        on top of that - one scrollbar nested inside another, reported live
        as "two scrollbars, I don't know which one does what". A page's own
        widget tree must never contain a QScrollArea of its own; the outer
        one add_page already provides is the only one that should exist."""
        bad = []
        for label in pages:
            entry = goto(label)
            nested = entry["page"].findChildren(QScrollArea)
            if nested:
                bad.append((label, len(nested)))
        assert not bad, f"pages with their own nested scroll area: {bad}"
    check("no page nests a second scroll area inside the page-level one",
          no_page_nests_a_second_scroll_area_inside_the_page_level_one)

    def wide_content_is_reachable_by_horizontal_scroll_not_silently_clipped():
        """Horizontal scrolling used to be banned outright on every page, on
        the theory that content was always narrow enough not to need it.
        Real screenshots proved otherwise - a long QGroupBox title, or just
        the wider glyph metrics of the real "Segoe UI" font on a customer's
        Windows machine (this test box only ever renders with whatever
        fallback font Linux substitutes, so the bug never reproduced there),
        needed more width than the window provided, and with nowhere for
        the overflow to go it was clipped off the left edge under RTL,
        gone, unreachable. Forces the exact same shape of overflow
        deterministically - a much larger app-wide font - and checks the
        label that used to vanish is reachable by actually scrolling to it,
        not just that a scrollbar exists."""
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import QTabWidget, QLabel
        original_font = app.font()
        big_font = QFont(original_font)
        big_font.setPointSize(original_font.pointSize() + 6)
        try:
            app.setFont(big_font)
            before = window.size()
            window.resize(1280, 800)
            for _ in range(3):
                app.processEvents()
            goto("customers")
            window.customers.findChild(QTabWidget).setCurrentIndex(1)
            for _ in range(3):
                app.processEvents()

            container = window.content_stack.currentWidget()
            hbar = container.horizontalScrollBar()
            assert hbar.maximum() > 0, \
                "the stress font did not force any page wider than the window - test setup is not exercising the bug"
            # A user cannot drag a scrollbar they cannot see - reachable only
            # by code (hbar.setValue) is not the same as reachable by a
            # person using the actual window, and ScrollBarAlwaysOff would
            # still let the assertions below pass with nothing on screen for
            # anyone to actually grab.
            assert hbar.isVisible(), \
                "content overflows the window but the horizontal scrollbar is not visible to reach it"

            target = next(l for l in window.customers.findChildren(QLabel)
                          if "لا يوجد عملاء" in l.text())
            hbar.setValue(0)
            for _ in range(2):
                app.processEvents()
            before_visible = 0 <= target.mapTo(window, target.rect().topLeft()).x() < window.width()

            hbar.setValue(hbar.maximum())
            for _ in range(2):
                app.processEvents()
            after_x = target.mapTo(window, target.rect().topLeft()).x()
            after_visible = 0 <= after_x < window.width()
            assert after_visible, \
                f"scrolling all the way did not bring the clipped label into view (x={after_x})"
        finally:
            app.setFont(original_font)
            window.resize(before)
            for _ in range(3):
                app.processEvents()
    check("content wider than the window is reachable by horizontal scroll, not silently clipped",
          wide_content_is_reachable_by_horizontal_scroll_not_silently_clipped)

    def hr_table_boxes_do_not_stretch_into_a_dead_gap():
        """"قائمة العاملين والوثائق" and "ملخص الرواتب" each used to give
        their own QGroupBox a layout stretch factor of 1 - a leftover from
        before the whole HR page scrolled as one unit, when the box needed
        to claim all the window's spare height itself so the table inside
        was not squeezed down to a couple of rows. The table inside is now
        sized to fit only its own rows (fit_table_height), so stretching the
        box around it to fill the page's full viewport height just left a
        tall, empty gap between the box's title and the table - reported
        live as "this page looks suspicious." Checked by comparing the
        box's own height to the table's - they should be close, not the box
        dwarfing a small table inside it."""
        from PyQt6.QtWidgets import QTabWidget, QGroupBox
        goto("hr")
        tabs = window.hr.findChild(QTabWidget)
        for label, table in (("قائمة العاملين", window.hr.table),
                             ("الرواتب", window.hr.payroll_table)):
            for i in range(tabs.count()):
                if tabs.tabText(i) == label:
                    tabs.setCurrentIndex(i)
            for _ in range(2):
                app.processEvents()
            box = table.parentWidget()
            while box is not None and not isinstance(box, QGroupBox):
                box = box.parentWidget()
            assert box is not None, f"{label}: table is not inside a QGroupBox anymore"
            slack = box.height() - table.height()
            assert slack < 120, \
                f"{label}: the box is {slack}px taller than its table - stretched into a dead gap again"
    check("the HR employee-list and payroll-summary boxes hug their table, no stretched dead gap",
          hr_table_boxes_do_not_stretch_into_a_dead_gap)

    def employee_table_reserves_room_for_its_own_horizontal_scrollbar():
        """"قائمة العاملين" is the one table in the app that keeps its
        horizontal scrollbar switched on (ResizeToContents across 12
        columns, so dates are not truncated) instead of banning it like
        every other table. fit_table_height sized the table to header +
        rows only, so the scrollbar painted itself over the bottom of the
        last row instead of below it - reported live as employees "missing"
        from a list that in fact had all of them, just partly hidden.
        Checked by adding enough employees/columns of real width to force
        the scrollbar on, then confirming the table's own height leaves
        room below the last row's bottom edge for the scrollbar on top of
        it, instead of the scrollbar's rect overlapping that row."""
        goto("hr")
        hr = window.hr
        for i in range(4):
            hr.name_input.setText(f"موظف اختبار {i + 1}")
            hr.job_input.setText("عامل")
            hr.salary_input.setText("5000")
            hr.allowance_input.setText("500")
            hr.save_employee()
        for _ in range(2):
            app.processEvents()

        from PyQt6.QtWidgets import QTabWidget
        tabs = window.hr.findChild(QTabWidget)
        for i in range(tabs.count()):
            if tabs.tabText(i) == "قائمة العاملين":
                tabs.setCurrentIndex(i)
        for _ in range(2):
            app.processEvents()

        table = hr.table
        hbar = table.horizontalScrollBar()
        assert hbar.isVisible(), \
            "test setup did not force the horizontal scrollbar on - cannot check the overlap"
        last_row = table.rowCount() - 1
        row_bottom = table.rowViewportPosition(last_row) + table.rowHeight(last_row)
        assert row_bottom <= table.viewport().height(), (
            f"the horizontal scrollbar overlaps the last row: row bottom at "
            f"{row_bottom}px but the viewport is only {table.viewport().height()}px tall")
    check("the employee-list table leaves room below its last row for its own horizontal scrollbar",
          employee_table_reserves_room_for_its_own_horizontal_scrollbar)

    def hiding_a_form_does_not_leave_a_dead_gap_above_its_table():
        """"المبيعات اليومية" and friends live inside a QTabWidget tab, and a
        QTabWidget hands its current tab page the tab bar's own full
        available height regardless of what that page's layout actually
        needs (the same root cause behind the HR dead-gap bug above). The
        history table below the entry form was given a layout stretch
        factor - and even without one, QTableWidget's own default size
        policy wants to grow - so any height the tab page is handed beyond
        what its fixed-height content needs gets allocated to the table's
        layout cell; since the table cannot actually grow past its own
        fixed height, Qt centres it inside that cell instead, opening a
        blank gap above the table that grows exactly when hiding the entry
        form should have made the page more compact, not less - reported
        live as "why is everything crammed at the bottom instead of taking
        its own room". Checked by hiding the form and confirming the table
        moves up to sit right under the toggle button/history row, not
        floating in the middle of a lot of blank space."""
        goto("sales")
        page = window.sales
        toggle = next(
            b for b in page.findChildren(QPushButton)
            if b.text() in ("إظهار نموذج التسجيل", "إخفاء النموذج"))
        if toggle.text() == "إظهار نموذج التسجيل":
            toggle.click()
            for _ in range(2):
                app.processEvents()
        toggle.click()  # hide the form
        for _ in range(4):
            app.processEvents()
        gap = page.table.geometry().top() - (toggle.geometry().top() + toggle.geometry().height())
        assert gap < 40, (
            f"hiding the entry form left a {gap}px dead gap above the table "
            f"instead of the table sitting right under the toggle button")
    check("hiding the sales entry form does not leave a dead gap above the history table",
          hiding_a_form_does_not_leave_a_dead_gap_above_its_table)

    def document_expiry_alert_uses_arabic_ok_button():
        """A plain QMessageBox() with no explicit button falls back to Qt's
        own compiled-in English standard-button text ("OK") since this app
        never loads a QTranslator for Qt's own strings (see
        packaging/restaurant_erp.spec) - every OTHER dialog in the app
        supplies its own Arabic text, but this one alert, built with
        box.exec() and no addButton() call, slipped through and showed an
        English "OK" - reported live via screenshot. Checked by forcing an
        alert (an employee with a document expiring inside 30 days) and
        confirming the dialog's actual button carries the Arabic text, not
        the English default."""
        from main import show_expiry_notifications
        from datetime import date, timedelta
        row = db.fetch_one("SELECT id FROM employees LIMIT 1")
        if row is None:
            db.execute_query(
                "INSERT INTO employees (name, job_title, base_salary) VALUES (?, ?, ?)",
                ("موظف تنبيه", "عامل", 5000))
            row = db.fetch_one("SELECT id FROM employees LIMIT 1")
        soon = (date.today() + timedelta(days=5)).isoformat()
        db.execute_query("UPDATE employees SET iqama_expiry = ? WHERE id = ?", (soon, row["id"]))

        captured = {}
        original_exec = QMessageBox.exec

        def fake_exec(self):
            # Qt only auto-adds its English default button once the box is
            # actually shown/polished - exec() without ever showing it
            # would miss the exact bug being checked for here.
            self.show()
            app.processEvents()
            captured["box"] = self
            self.close()
            return QMessageBox.StandardButton.Ok

        QMessageBox.exec = fake_exec
        try:
            show_expiry_notifications(db)
        finally:
            QMessageBox.exec = original_exec
            db.execute_query("UPDATE employees SET iqama_expiry = NULL WHERE id = ?", (row["id"],))

        box = captured.get("box")
        assert box is not None, "test setup did not trigger the expiry alert at all"
        texts = [b.text().replace("&", "") for b in box.buttons()]
        assert "OK" not in texts, f"the alert still shows Qt's English default button: {texts}"
        assert "موافق" in texts, f"expected the Arabic موافق button, found: {texts}"
    check("the document-expiry alert's button reads موافق, not the English default OK",
          document_expiry_alert_uses_arabic_ok_button)

    def every_standard_dialog_button_is_arabic_app_wide():
        """Every QMessageBox.information/.warning/.question call across the
        app (there are dozens) relies on Qt's own standard buttons - "OK",
        "Yes", "No", "Cancel" - which come from Qt's QPlatformTheme
        translation context, not from any string this codebase writes.
        Reported live after the document-expiry alert's English "OK" turned
        out to be one instance of an app-wide gap, not a one-off: fixed
        centrally with a small translator (install_arabic_dialog_buttons in
        main.py) instead of hand-editing every call site. Checked directly
        against a real QMessageBox with every standard button turned on -
        the same object every information()/warning()/question() call
        builds internally - not through the test suite's own
        silence_dialogs() monkeypatch, which never asks Qt for real text."""
        box = QMessageBox()
        box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
        expected = {
            QMessageBox.StandardButton.Ok: "موافق",
            QMessageBox.StandardButton.Yes: "نعم",
            QMessageBox.StandardButton.No: "لا",
            QMessageBox.StandardButton.Cancel: "إلغاء",
        }
        for standard_button, arabic_text in expected.items():
            actual = box.button(standard_button).text().replace("&", "")
            assert actual == arabic_text, (
                f"standard button {standard_button} reads {actual!r}, expected {arabic_text!r}")
    check("every standard Qt dialog button (OK/Yes/No/Cancel) is Arabic app-wide",
          every_standard_dialog_button_is_arabic_app_wide)

    def primary_action_buttons_do_not_span_the_full_page_width():
        """A lone save/submit button stretching across the entire card - a
        QVBoxLayout gives every child the layout's full width by default,
        regardless of how short the button's own text is - read as
        disproportionate and was flagged by product review. Given a
        maximum width, the same QVBoxLayout/QFormLayout item defaults to
        right-aligning it instead of centring it (checked directly, see the
        commit this test shipped with) - which happens to match this RTL
        app's existing convention of controls starting from the right, so
        no layout restructuring was needed, just a cap on each button's
        own width. Checked on the worst offenders reported live: daily
        sales, HR attendance/deductions, and settings."""
        checks = [
            ("sales", 0, "حفظ مبيعات اليوم"),
            ("hr", 1, "تسجيل الحضور/الغياب"),
            ("settings", None, "إضافة مستخدم"),
        ]
        from PyQt6.QtWidgets import QTabWidget
        for nav_label, tab_index, button_text in checks:
            goto(nav_label)
            page = next(e["page"] for e in window.nav_entries if e["label"] == nav_label)
            if tab_index is not None:
                tabs = page.findChild(QTabWidget)
                tabs.setCurrentIndex(tab_index)
            for _ in range(2):
                app.processEvents()
            # A form starting collapsed on a short test window (see
            # _short_screen in sales_entry_module.py/purchase_module.py)
            # would otherwise hide the very button being checked.
            show_toggle = next(
                (b for b in page.findChildren(QPushButton) if b.text() == "إظهار نموذج التسجيل"), None)
            if show_toggle is not None:
                show_toggle.click()
                for _ in range(2):
                    app.processEvents()
            btn = next((b for b in page.findChildren(QPushButton) if b.text() == button_text), None)
            assert btn is not None, f"{nav_label}: could not find the '{button_text}' button anymore"
            assert btn.isVisible(), f"{nav_label}: '{button_text}' is not visible on its tab"
            ratio = btn.width() / page.width()
            assert ratio < 0.5, (
                f"{nav_label}: '{button_text}' still spans {ratio:.0%} of the page width - "
                f"expected a capped, right-aligned button, not a full-width one")
    check("primary action buttons (سجل مبيعات، تسجيل حضور، إضافة مستخدم) are capped, not full-width",
          primary_action_buttons_do_not_span_the_full_page_width)

    def secondary_buttons_have_a_solid_fill_not_a_transparent_outline():
        """danger_button() (حذف...) and the show/hide form toggle used a
        transparent background with only a border - reported live as
        looking like plain text rather than a clickable control. render()
        (see above) fills the pixmap white before painting, so a
        transparent button's own background renders back as pure white;
        checked the same way the login button check above tells a real
        fill from a transparent one - by rendering the real "حذف اليوم
        المحدد" button and confirming its centre pixel is not near-white."""
        goto("sales")
        page = window.sales
        delete_btn = next(b for b in page.findChildren(QPushButton) if b.text() == "حذف اليوم المحدد")
        image = render(delete_btn)
        colour = image.pixelColor(delete_btn.width() // 2, delete_btn.height() // 2)
        assert not is_near_white(colour.name()), (
            f"'حذف اليوم المحدد' looks transparent - centre pixel is {colour.name()}, "
            f"nearly white, meaning nothing but the render backdrop shows through")
    check("secondary buttons (حذف، إخفاء النموذج) have a solid fill, not a transparent outline",
          secondary_buttons_have_a_solid_fill_not_a_transparent_outline)

    def login_dialog_has_a_clean_white_background_and_a_working_button():
        """A plain QDialog paints the palette's grey Window colour by
        default, which read as an unfinished box floating on the desktop
        rather than part of the app - reported live. Given a QSS
        stylesheet on any *container* widget (a page's QScrollArea/
        viewport - see add_page) is what stopped the app-wide QSS from
        reaching buttons inside it earlier this session, this checks the
        dialog's own "دخول" button still renders with its real blue fill
        after giving the dialog itself a background stylesheet - proving
        that specific failure mode does not apply here."""
        from ui.login_dialog import LoginDialog
        from PyQt6.QtWidgets import QPushButton
        dialog = LoginDialog(db)
        dialog.show()
        for _ in range(2):
            app.processEvents()
        try:
            login_btn = next(b for b in dialog.findChildren(QPushButton) if b.text() == "دخول")
            image = render(login_btn)
            colour = image.pixelColor(login_btn.width() // 2, login_btn.height() // 2)
            near_white = colour.red() > 230 and colour.green() > 230 and colour.blue() > 230
            assert not near_white, f"the login button lost its background fill - now {colour.name()}"
        finally:
            dialog.close()
    check("the login dialog has a clean white background and a properly styled button",
          login_dialog_has_a_clean_white_background_and_a_working_button)

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
