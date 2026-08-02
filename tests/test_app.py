"""End-to-end regression checks.

Run headlessly:  QT_QPA_PLATFORM=offscreen python tests/test_app.py

Covers the paths that have actually broken before: accounting identities,
VAT handling, stylesheet leaking onto child widgets, invisible buttons,
RTL date formatting, and content being cut off below the window.
"""

import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QApplication, QMessageBox, QPushButton, QDateEdit, QLabel, QScrollArea,
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QPoint

from database.db_manager import DBManager
from ui.main_window import MainWindow
from ui.theme import apply_theme

DB_PATH = "/tmp/_erp_regression.db"

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


def dominant_colour(widget):
    image = render(widget)
    counts = collections.Counter()
    for y in range(2, image.height() - 2, 2):
        for x in range(2, image.width() - 2, 2):
            counts[image.pixelColor(x, y).name()] += 1
    return counts.most_common(1)[0][0]


def is_near_white(hex_colour):
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return r > 235 and g > 235 and b > 235


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    silence_dialogs()
    db = DBManager(DB_PATH)
    app = QApplication(sys.argv)
    apply_theme(app)
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
        hr.attendance_status.setCurrentText("Absent")
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
            p.payment_status.setCurrentText(status)
            p.save_purchase()
        p.category_input.setCurrentIndex(p.category_input.findData("raw_material"))
        p.supplier_input.setCurrentIndex(p.supplier_input.findData(sid))
        p.amount_input.setText("500")
        p.payment_status.setCurrentText("Credit")
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
        p.payment_status.setCurrentText("Cash")
        p.save_purchase()
        before = db.fetch_one(
            "SELECT COALESCE(SUM(debit)-SUM(credit),0) v FROM journal_items WHERE account_code='5200'")["v"]
        p.table.setCurrentCell(0, 0)
        p.delete_selected_purchase()
        after = db.fetch_one(
            "SELECT COALESCE(SUM(debit)-SUM(credit),0) v FROM journal_items WHERE account_code='5200'")["v"]
        assert abs((before - after) - 999) < 0.01, f"{before} -> {after}"
    check("deleting a purchase also reverses its journal entry", deleting_a_purchase_reverses_its_entry)

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
        out = "/tmp/_erp_report_test.pdf"
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
        bad = []
        for page in pages:
            entry = goto(page)
            for btn in entry["page"].findChildren(QPushButton):
                if btn.isVisible() and btn.width() > 20 and btn.height() > 10:
                    fill = dominant_colour(btn)
                    if is_near_white(fill):
                        bad.append((page, btn.text()[:25], fill))
        assert not bad, bad
    check("no button renders white-on-white", all_buttons_visible)

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

    def nothing_is_unreachable():
        bad = []
        for page in pages:
            entry = goto(page)
            container = window.content_stack.currentWidget()
            scrollable = isinstance(container, QScrollArea) or bool(
                entry["page"].findChildren(QScrollArea))
            if scrollable:
                continue
            for btn in entry["page"].findChildren(QPushButton):
                if not btn.isVisible():
                    continue
                bottom = btn.mapTo(container, QPoint(0, 0)).y() + btn.height()
                if bottom > container.height() + 4:
                    bad.append((page, btn.text()[:25]))
        assert not bad, bad
    check("no page hides content below the window", nothing_is_unreachable)

    def every_page_opens():
        for page in pages:
            entry = goto(page)
            assert entry["page"].isVisible(), page
    check("every page opens without error", every_page_opens)

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
