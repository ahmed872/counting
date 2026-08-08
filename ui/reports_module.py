from datetime import datetime

from PyQt6.QtCore import QDate
from PyQt6.QtGui import QTextDocument
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QComboBox,
    QDateEdit,
    QPushButton,
    QTextBrowser,
    QMessageBox,
    QFileDialog,
)

from logic.accounting import AccountingLogic

PERIOD_DAILY = "يومي"
PERIOD_WEEKLY = "أسبوعي"
PERIOD_MONTHLY = "شهري"
PERIOD_YEARLY = "سنوي"
PERIOD_CUSTOM = "فترة مخصصة"

CATEGORY_LABELS = {
    'raw_material': 'مواد خام',
    'purchase_expense': 'مصروفات مرتبطة بالمشتريات',
    'operating_expense': 'مصروفات تشغيلية',
}


def money(value):
    return f"{value:,.2f}"


class ReportsModule(QWidget):
    """Ready-made period reports (daily / weekly / monthly / yearly / custom)
    that can be printed or saved as PDF."""

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.accounting = AccountingLogic(db_manager)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel("التقارير")
        header.setStyleSheet("font-size: 22px; font-weight: 800; color: #1f3b57;")
        layout.addWidget(header)

        subtitle = QLabel("اختر نوع التقرير والفترة، ثم اطبعه أو احفظه PDF.")
        subtitle.setStyleSheet("color: #64748b;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        controls = QGroupBox("إعداد التقرير")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.period_input = QComboBox()
        self.period_input.addItems(
            [PERIOD_DAILY, PERIOD_WEEKLY, PERIOD_MONTHLY, PERIOD_YEARLY, PERIOD_CUSTOM]
        )
        self.period_input.currentTextChanged.connect(self.on_period_changed)

        self.branch_input = QComboBox()
        self.branch_input.addItem("كل الفروع", None)
        for branch in self.db.fetch_all("SELECT id, name FROM branches ORDER BY id"):
            self.branch_input.addItem(branch["name"], branch["id"])

        self.start_date = QDateEdit(QDate.currentDate())
        self.end_date = QDateEdit(QDate.currentDate())

        row.addWidget(self._label("نوع التقرير"))
        row.addWidget(self.period_input, 1)
        row.addSpacing(12)
        row.addWidget(self._label("الفرع"))
        row.addWidget(self.branch_input, 1)
        controls_layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(self._label("من"))
        row2.addWidget(self.start_date, 1)
        row2.addSpacing(12)
        row2.addWidget(self._label("إلى"))
        row2.addWidget(self.end_date, 1)
        controls_layout.addLayout(row2)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        generate_btn = QPushButton("عرض التقرير")
        generate_btn.setMinimumHeight(44)
        generate_btn.clicked.connect(self.generate_report)
        pdf_btn = QPushButton("حفظ PDF")
        pdf_btn.setMinimumHeight(44)
        pdf_btn.clicked.connect(self.save_pdf)
        print_btn = QPushButton("طباعة")
        print_btn.setMinimumHeight(44)
        print_btn.clicked.connect(self.print_report)
        buttons.addWidget(generate_btn, 2)
        buttons.addWidget(pdf_btn, 1)
        buttons.addWidget(print_btn, 1)
        controls_layout.addLayout(buttons)

        layout.addWidget(controls)

        self.viewer = QTextBrowser()
        self.viewer.setStyleSheet(
            "QTextBrowser { background:white; border:1px solid #dde3ea; border-radius:12px; padding:10px; }"
        )
        self.viewer.setMinimumHeight(320)
        layout.addWidget(self.viewer, 1)

        self.on_period_changed()

    def _label(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-weight:700; color:#334155;")
        return label

    def on_period_changed(self, _text=None):
        custom = self.period_input.currentText() == PERIOD_CUSTOM
        self.start_date.setEnabled(custom)
        self.end_date.setEnabled(custom)
        if not custom:
            start, end = self.resolve_period()
            self.start_date.setDate(QDate.fromString(start, "yyyy-MM-dd"))
            self.end_date.setDate(QDate.fromString(end, "yyyy-MM-dd"))
        self.generate_report()

    def resolve_period(self):
        period = self.period_input.currentText()
        today = QDate.currentDate()
        if period == PERIOD_DAILY:
            return today.toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
        if period == PERIOD_WEEKLY:
            return today.addDays(-6).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
        if period == PERIOD_MONTHLY:
            # Whole calendar month, not month-to-date: on the 1st of the month a
            # month-to-date report would show a single day, which is not what
            # "monthly report" means to the person reading it.
            first = QDate(today.year(), today.month(), 1)
            return first.toString("yyyy-MM-dd"), first.addMonths(1).addDays(-1).toString("yyyy-MM-dd")
        if period == PERIOD_YEARLY:
            first = QDate(today.year(), 1, 1)
            return first.toString("yyyy-MM-dd"), QDate(today.year(), 12, 31).toString("yyyy-MM-dd")
        return (self.start_date.date().toString("yyyy-MM-dd"),
                self.end_date.date().toString("yyyy-MM-dd"))

    def current_report_html(self):
        start, end = self.resolve_period()
        branch_id = self.branch_input.currentData()
        branch_name = self.branch_input.currentText()
        data = self.accounting.get_period_report(start, end, branch_id)
        return self.build_html(data, self.period_input.currentText(), branch_name)

    def generate_report(self):
        try:
            self.viewer.setHtml(self.current_report_html())
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    def build_html(self, d, period_label, branch_name):
        sales = d['sales']
        purchases = d['purchases']
        returns = d['returns']

        def row(label, value, bold=False, color=None):
            style = "font-weight:800;" if bold else ""
            if color:
                style += f"color:{color};"
            return (f"<tr><td style='padding:6px 10px;{style}'>{label}</td>"
                    f"<td style='padding:6px 10px;text-align:left;{style}'>{money(value)}</td></tr>")

        daily_rows = ""
        for entry in d['daily']:
            daily_rows += (
                "<tr>"
                f"<td style='padding:5px 8px'>{entry['day']}</td>"
                f"<td style='padding:5px 8px;text-align:left'>{money(entry['cash'])}</td>"
                f"<td style='padding:5px 8px;text-align:left'>{money(entry['pos'])}</td>"
                f"<td style='padding:5px 8px;text-align:left'>{money(entry['transfer'])}</td>"
                f"<td style='padding:5px 8px;text-align:left'>{money(entry['sales_total'])}</td>"
                f"<td style='padding:5px 8px;text-align:left'>{money(entry['purchases'])}</td>"
                f"<td style='padding:5px 8px;text-align:left'>{money(entry['net_vat'])}</td>"
                f"<td style='padding:5px 8px;text-align:left'>{money(entry['profit'])}</td>"
                "</tr>"
            )
        if not daily_rows:
            daily_rows = ("<tr><td colspan='8' style='padding:12px;text-align:center;color:#64748b'>"
                          "لا توجد حركات في هذه الفترة</td></tr>")

        profit_color = "#16a34a" if d['net_profit'] >= 0 else "#dc2626"

        return f"""
        <div dir="rtl" style="font-family:'Segoe UI',Tahoma,sans-serif; color:#1f2937;">
          <h2 style="color:#1f3b57;margin-bottom:2px;">تقرير {period_label}</h2>
          <div style="color:#64748b;margin-bottom:4px;">
            الفترة من {d['start_date']} إلى {d['end_date']} &nbsp;|&nbsp; {branch_name}
          </div>
          <div style="color:#94a3b8;font-size:11px;margin-bottom:14px;">
            تم إنشاء التقرير في {datetime.now().strftime('%Y-%m-%d %H:%M')}
          </div>

          <h3 style="color:#1f3b57;">1) المبيعات (شاملة الضريبة)</h3>
          <table width="100%" cellspacing="0" style="border:1px solid #dde3ea;">
            {row("كاش", sales['Cash']['total'])}
            {row("شبكة (مدى / فيزا)", sales['POS']['total'])}
            {row("تحويل بنكي", sales['Transfer']['total'])}
            {row("إجمالي التحصيل", sales['grand_total'], bold=True)}
            {row("مرتجعات مبيعات", returns['sales_returns'])}
            {row("صافي المبيعات (بدون ضريبة)", d['net_sales'], bold=True)}
          </table>

          <h3 style="color:#1f3b57;">2) المشتريات والمصروفات (بدون ضريبة)</h3>
          <table width="100%" cellspacing="0" style="border:1px solid #dde3ea;">
            {row(CATEGORY_LABELS['raw_material'], purchases['raw_material']['net'])}
            {row(CATEGORY_LABELS['purchase_expense'], purchases['purchase_expense']['net'])}
            {row(CATEGORY_LABELS['operating_expense'], purchases['operating_expense']['net'])}
            {row("مرتجعات مشتريات", returns['purchase_returns'])}
            {row("إجمالي المشتريات والمصروفات", purchases['grand_net'] - returns['purchase_returns'], bold=True)}
          </table>

          <h3 style="color:#1f3b57;">3) الأرباح</h3>
          <table width="100%" cellspacing="0" style="border:1px solid #dde3ea;">
            {row("صافي المبيعات", d['net_sales'])}
            {row("تكلفة المبيعات", d['cost_of_sales'])}
            {row("مجمل الربح", d['gross_profit'], bold=True)}
            {row("الرواتب والأجور", d['salaries_expense'])}
            {row("المصروفات التشغيلية", d['operating_expenses'])}
            {row("صافي الربح", d['net_profit'], bold=True, color=profit_color)}
          </table>

          <h3 style="color:#1f3b57;">4) ضريبة القيمة المضافة (15%)</h3>
          <table width="100%" cellspacing="0" style="border:1px solid #dde3ea;">
            {row("ضريبة المبيعات (مخرجات)", d['output_vat'])}
            {row("ضريبة المشتريات (مدخلات)", d['input_vat'])}
            {row("صافي الضريبة المستحقة للهيئة", d['net_vat'], bold=True, color="#e67e22")}
          </table>

          <h3 style="color:#1f3b57;">5) التفصيل اليومي</h3>
          <table width="100%" cellspacing="0" style="border:1px solid #dde3ea;font-size:12px;">
            <tr style="background:#1f3b57;color:white;">
              <th style="padding:6px 8px;">التاريخ</th>
              <th style="padding:6px 8px;">كاش</th>
              <th style="padding:6px 8px;">شبكة</th>
              <th style="padding:6px 8px;">تحويل</th>
              <th style="padding:6px 8px;">إجمالي المبيعات</th>
              <th style="padding:6px 8px;">المشتريات</th>
              <th style="padding:6px 8px;">صافي الضريبة</th>
              <th style="padding:6px 8px;">الربح</th>
            </tr>
            {daily_rows}
          </table>
        </div>
        """

    def _document(self):
        doc = QTextDocument()
        doc.setHtml(self.current_report_html())
        return doc

    def save_pdf(self):
        default = f"تقرير-{self.resolve_period()[0]}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "حفظ التقرير PDF", default, "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(path)
            self._document().print(printer)
            QMessageBox.information(self, "تم", f"تم حفظ التقرير في:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    def print_report(self):
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec() == QPrintDialog.DialogCode.Accepted:
                self._document().print(printer)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    def refresh_on_show(self):
        selected = self.branch_input.currentData()
        self.branch_input.clear()
        self.branch_input.addItem("كل الفروع", None)
        for branch in self.db.fetch_all("SELECT id, name FROM branches ORDER BY id"):
            self.branch_input.addItem(branch["name"], branch["id"])
        index = self.branch_input.findData(selected)
        if index >= 0:
            self.branch_input.setCurrentIndex(index)
        self.generate_report()
