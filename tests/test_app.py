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
