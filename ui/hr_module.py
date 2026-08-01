from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QPushButton, QFormLayout, QLineEdit,
                             QComboBox, QDateEdit, QLabel, QHeaderView, QMessageBox,
                             QGroupBox, QTabWidget, QScrollArea, QSizePolicy)
from PyQt6.QtCore import QDate, Qt
from ui.common_widgets import create_stat_card


class HRModule(QWidget):
    def __init__(self, db_manager, hr_logic):
        super().__init__()
        self.db = db_manager
        self.hr_logic = hr_logic
        self.init_ui()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(12)

        header = QLabel("إدارة الموارد البشرية")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #1f3b57;")
        root_layout.addWidget(header)

        subtitle = QLabel("متابعة بيانات العمال، الوثائق، الحضور، السلف والخصومات، والرواتب الشهرية من مكان واحد")
        subtitle.setStyleSheet("color: #64748b; margin-bottom: 4px;")
        root_layout.addWidget(subtitle)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setStyleSheet("QTabWidget::pane { border: 0; } QTabBar::tab { padding: 10px 16px; } QTabBar::tab:selected { font-weight: 700; }")
        root_layout.addWidget(tabs)

        setup_scroll = QScrollArea()
        setup_scroll.setWidgetResizable(True)
        setup_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        setup_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        setup_scroll_widget = QWidget()
        setup_layout = QVBoxLayout(setup_scroll_widget)
        setup_layout.setContentsMargins(6, 6, 6, 6)
        setup_layout.setSpacing(12)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self.total_employees_card = create_stat_card("إجمالي العاملين", "0", "#2980b9")
        self.doc_alerts_card = create_stat_card("تنبيهات الوثائق (30 يوم)", "0", "#e67e22")
        self.absent_card = create_stat_card("الغياب هذا الشهر", "0", "#c0392b")
        self.advances_card = create_stat_card("سلف قائمة (غير مسددة)", "0.00", "#8e44ad")
        cards_row.addWidget(self.total_employees_card)
        cards_row.addWidget(self.doc_alerts_card)
        cards_row.addWidget(self.absent_card)
        cards_row.addWidget(self.advances_card)
        setup_layout.addLayout(cards_row)

        form_group = QGroupBox("بيانات العامل")
        form_outer = QVBoxLayout(form_group)
        form_outer.setContentsMargins(6, 10, 6, 14)

        self.name_input = QLineEdit()
        self.job_input = QLineEdit()
        self.branch_input = QComboBox()
        self.load_branch_options()
        self.salary_input = QLineEdit()
        self.allowance_input = QLineEdit()
        self.iqama_input = QLineEdit()
        self.iqama_expiry = QDateEdit(QDate.currentDate())
        self.iqama_expiry.setCalendarPopup(True)
        self.passport_input = QLineEdit()
        self.passport_expiry = QDateEdit(QDate.currentDate())
        self.passport_expiry.setCalendarPopup(True)
        self.work_permit_input = QLineEdit()
        self.work_permit_expiry = QDateEdit(QDate.currentDate())
        self.work_permit_expiry.setCalendarPopup(True)
        self.work_card_input = QLineEdit()
        self.work_card_expiry = QDateEdit(QDate.currentDate())
        self.work_card_expiry.setCalendarPopup(True)

        self._apply_field_widths()

        # A single vertical form (one field per row) is far more robust across different
        # fonts/DPI settings than packing multiple columns side by side - a long label in
        # a narrower column is what causes cramped, hard-to-read forms on some systems.
        employee_form = QFormLayout()
        employee_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        employee_form.setSpacing(16)
        employee_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)

        employee_form.addRow("الاسم:", self.name_input)
        employee_form.addRow("الوظيفة:", self.job_input)
        employee_form.addRow("الفرع:", self.branch_input)
        employee_form.addRow("الراتب الأساسي:", self.salary_input)
        employee_form.addRow("البدلات:", self.allowance_input)
        employee_form.addRow("رقم الإقامة وتاريخ الانتهاء:", self._document_row(self.iqama_input, self.iqama_expiry))
        employee_form.addRow("رقم الجواز وتاريخ الانتهاء:", self._document_row(self.passport_input, self.passport_expiry))
        employee_form.addRow("رقم تصريح العمل وتاريخ الانتهاء:", self._document_row(self.work_permit_input, self.work_permit_expiry))
        employee_form.addRow("رقم كرت العمل وتاريخ الانتهاء:", self._document_row(self.work_card_input, self.work_card_expiry))

        form_outer.addLayout(employee_form)

        add_btn = QPushButton("إضافة موظف")
        add_btn.clicked.connect(self.add_employee)
        add_btn.setMinimumHeight(44)
        form_outer.addSpacing(6)
        form_outer.addWidget(add_btn)
        setup_layout.addWidget(form_group)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)
        attendance_group = QGroupBox("تسجيل الحضور والغياب")
        attendance_layout = QFormLayout(attendance_group)
        attendance_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.attendance_employee = QComboBox()
        self.attendance_date = QDateEdit(QDate.currentDate())
        self.attendance_date.setCalendarPopup(True)
        self.attendance_status = QComboBox()
        self.attendance_status.addItems(["Present", "Absent"])
        self.attendance_note = QLineEdit()
        self._apply_field_widths([self.attendance_employee, self.attendance_date, self.attendance_status, self.attendance_note])
        attendance_btn = QPushButton("تسجيل الحضور/الغياب")
        attendance_btn.clicked.connect(self.record_attendance)
        attendance_layout.addRow("العامل:", self.attendance_employee)
        attendance_layout.addRow("التاريخ:", self.attendance_date)
        attendance_layout.addRow("الحالة:", self.attendance_status)
        attendance_layout.addRow("ملاحظات:", self.attendance_note)
        attendance_layout.addRow(attendance_btn)
        action_row.addWidget(attendance_group)

        deduction_group = QGroupBox("سلف / خصومات / مكافآت")
        deduction_layout = QFormLayout(deduction_group)
        deduction_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.deduction_employee = QComboBox()
        self.deduction_type = QComboBox()
        self.deduction_type.addItem("خصم (Deduction)", "Deduction")
        self.deduction_type.addItem("سلفة (Advance)", "Advance")
        self.deduction_type.addItem("مكافأة (Bonus)", "Bonus")
        self.deduction_date = QDateEdit(QDate.currentDate())
        self.deduction_date.setCalendarPopup(True)
        self.deduction_amount = QLineEdit()
        self.deduction_notes = QLineEdit()
        self._apply_field_widths([self.deduction_employee, self.deduction_type, self.deduction_date, self.deduction_amount, self.deduction_notes])
        deduction_btn = QPushButton("تسجيل الحركة")
        deduction_btn.clicked.connect(self.add_deduction)
        deduction_layout.addRow("العامل:", self.deduction_employee)
        deduction_layout.addRow("النوع:", self.deduction_type)
        deduction_layout.addRow("التاريخ:", self.deduction_date)
        deduction_layout.addRow("المبلغ:", self.deduction_amount)
        deduction_layout.addRow("ملاحظات:", self.deduction_notes)
        deduction_layout.addRow(deduction_btn)
        action_row.addWidget(deduction_group)
        setup_layout.addLayout(action_row)

        payroll_group = QGroupBox("تشغيل وترحيل الرواتب الشهرية")
        payroll_layout = QFormLayout(payroll_group)
        payroll_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.payroll_month = QComboBox()
        for month in range(1, 13):
            self.payroll_month.addItem(f"{month:02d}", month)
        self.payroll_month.setCurrentIndex(QDate.currentDate().month() - 1)
        self.payroll_year = QLineEdit(str(QDate.currentDate().year()))
        self._apply_field_widths([self.payroll_month, self.payroll_year])
        buttons_row = QHBoxLayout()
        payroll_btn = QPushButton("حساب الرواتب (معاينة)")
        payroll_btn.clicked.connect(self.refresh_payroll)
        post_payroll_btn = QPushButton("ترحيل الرواتب للمحاسبة")
        post_payroll_btn.clicked.connect(self.post_payroll)
        buttons_row.addWidget(payroll_btn)
        buttons_row.addWidget(post_payroll_btn)
        payroll_layout.addRow("الشهر:", self.payroll_month)
        payroll_layout.addRow("السنة:", self.payroll_year)
        payroll_layout.addRow(buttons_row)
        setup_layout.addWidget(payroll_group)

        setup_scroll.setWidget(setup_scroll_widget)
        tabs.addTab(setup_scroll, "البيانات والحضور")

        tables_scroll = QScrollArea()
        tables_scroll.setWidgetResizable(True)
        tables_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        tables_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tables_widget = QWidget()
        tables_layout = QVBoxLayout(tables_widget)
        tables_layout.setContentsMargins(0, 0, 0, 0)
        tables_layout.setSpacing(12)

        self.payroll_table = QTableWidget()
        self.payroll_table.setColumnCount(10)
        self.payroll_table.setHorizontalHeaderLabels([
            "العامل", "الفرع", "الراتب الإجمالي", "أيام الغياب", "أيام الحضور",
            "خصم الغياب", "خصومات أخرى", "مكافآت", "سلف مستردة", "الصافي المستحق"
        ])
        self.payroll_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.payroll_table.verticalHeader().setVisible(False)
        self.payroll_table.setAlternatingRowColors(True)
        self.payroll_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.payroll_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.payroll_table.setMinimumHeight(220)
        payroll_box = QGroupBox("ملخص الرواتب")
        payroll_box_layout = QVBoxLayout(payroll_box)
        payroll_box_layout.addWidget(self.payroll_table)
        tables_layout.addWidget(payroll_box)

        self.table = QTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels(["الاسم", "الوظيفة", "الفرع", "الراتب", "البدلات", "رقم الإقامة", "انتهاء الإقامة", "رقم الجواز", "انتهاء الجواز", "رقم تصريح العمل", "انتهاء تصريح العمل", "رقم كرت العمل/انتهاؤه"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(280)
        employees_box = QGroupBox("قائمة العاملين والوثائق")
        employees_box_layout = QVBoxLayout(employees_box)
        employees_box_layout.addWidget(self.table)
        tables_layout.addWidget(employees_box)

        tables_scroll.setWidget(tables_widget)
        tabs.addTab(tables_scroll, "القوائم")

        self.load_employees()

    def _document_row(self, number_field, date_field):
        wrapper = QWidget()
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        number_field.setMinimumWidth(160)
        date_field.setMinimumWidth(150)
        row.addWidget(number_field, 1)
        row.addWidget(date_field)
        return wrapper


    def load_branch_options(self):
        self.branch_input.clear()
        for row in self.db.fetch_all("SELECT id, name FROM branches ORDER BY id"):
            self.branch_input.addItem(row["name"], row["id"])

    def _apply_field_widths(self, widgets=None):
        fields = widgets or [
            self.name_input,
            self.job_input,
            self.branch_input,
            self.salary_input,
            self.allowance_input,
            self.iqama_input,
            self.iqama_expiry,
            self.passport_input,
            self.passport_expiry,
            self.work_permit_input,
            self.work_permit_expiry,
            self.work_card_input,
            self.work_card_expiry,
        ]
        for field in fields:
            field.setMinimumWidth(160)

    def add_employee(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "ادخل اسم الموظف")
            return
        job = self.job_input.text().strip()
        branch_id = self.branch_input.currentData()
        try:
            salary = float(self.salary_input.text() or 0)
            allowance = float(self.allowance_input.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "الراتب أو البدلات غير صحيحة")
            return
        iqama = self.iqama_expiry.date().toString("yyyy-MM-dd")
        passport = self.passport_expiry.date().toString("yyyy-MM-dd")
        work_permit = self.work_permit_expiry.date().toString("yyyy-MM-dd")
        work_card = self.work_card_expiry.date().toString("yyyy-MM-dd")

        self.db.execute_query(
            "INSERT INTO employees (name, job_title, branch_id, base_salary, allowances, iqama_no, iqama_expiry, passport_no, passport_expiry, work_permit_no, work_permit_expiry, work_card_no, work_card_expiry) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, job, branch_id, salary, allowance, self.iqama_input.text().strip(), iqama, self.passport_input.text().strip(), passport, self.work_permit_input.text().strip(), work_permit, self.work_card_input.text().strip(), work_card)
        )
        QMessageBox.information(self, "نجاح", "تم إضافة الموظف بنجاح")
        self.name_input.clear()
        self.job_input.clear()
        self.salary_input.clear()
        self.allowance_input.clear()
        self.iqama_input.clear()
        self.passport_input.clear()
        self.work_permit_input.clear()
        self.work_card_input.clear()
        self.load_employees()
        self.refresh_payroll()

    def record_attendance(self):
        employee_id = self.attendance_employee.currentData()
        if employee_id is None:
            QMessageBox.warning(self, "تنبيه", "اختر العامل أولاً")
            return

        date = self.attendance_date.date().toString("yyyy-MM-dd")
        status = self.attendance_status.currentText()
        note = self.attendance_note.text().strip()
        self.hr_logic.record_attendance(employee_id, date, status)
        if note:
            self.db.execute_query("UPDATE attendance SET notes = ? WHERE employee_id = ? AND date = ?", (note, employee_id, date))
        QMessageBox.information(self, "نجاح", "تم تسجيل الحضور/الغياب")
        self.attendance_note.clear()
        self.refresh_payroll()

    def add_deduction(self):
        employee_id = self.deduction_employee.currentData()
        if employee_id is None:
            QMessageBox.warning(self, "تنبيه", "اختر العامل أولاً")
            return
        try:
            amount = float(self.deduction_amount.text())
            if amount <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "ادخل مبلغاً صحيحاً")
            return

        entry_type = self.deduction_type.currentData()
        date = self.deduction_date.date().toString("yyyy-MM-dd")
        notes = self.deduction_notes.text().strip()

        try:
            if entry_type == "Advance":
                self.hr_logic.grant_advance(employee_id, date, amount, notes)
            else:
                self.hr_logic.add_deduction(employee_id, date, entry_type, amount, notes)
        except Exception as e:
            QMessageBox.critical(self, "خطأ", str(e))
            return

        QMessageBox.information(self, "نجاح", "تم تسجيل الحركة")
        self.deduction_amount.clear()
        self.deduction_notes.clear()
        self.refresh_payroll()

    def post_payroll(self):
        try:
            month = self.payroll_month.currentData()
            year = int(self.payroll_year.text())
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "سنة غير صحيحة")
            return

        confirm = QMessageBox.question(
            self, "تأكيد الترحيل",
            f"سيتم ترحيل رواتب شهر {month:02d}/{year} إلى دفتر اليومية بشكل نهائي. متابعة؟",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self.hr_logic.post_payroll(month, year)
            QMessageBox.information(self, "نجاح", "تم ترحيل الرواتب إلى المحاسبة بنجاح")
        except Exception as e:
            QMessageBox.critical(self, "خطأ", str(e))
        self.refresh_payroll()

    def refresh_payroll(self):
        try:
            month = self.payroll_month.currentData()
            year = int(self.payroll_year.text())
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "سنة غير صحيحة")
            return

        payroll = self.hr_logic.get_monthly_payroll(month, year)
        self.payroll_table.setRowCount(len(payroll))
        total_absent = 0
        for row, item in enumerate(payroll):
            total_absent += item['absent_days']
            self.payroll_table.setItem(row, 0, QTableWidgetItem(item['name']))
            self.payroll_table.setItem(row, 1, QTableWidgetItem(item['branch_name'] or ""))
            self.payroll_table.setItem(row, 2, QTableWidgetItem(f"{item['gross_salary']:.2f}"))
            self.payroll_table.setItem(row, 3, QTableWidgetItem(str(item['absent_days'])))
            self.payroll_table.setItem(row, 4, QTableWidgetItem(str(item['present_days'])))
            self.payroll_table.setItem(row, 5, QTableWidgetItem(f"{item['absence_deduction']:.2f}"))
            self.payroll_table.setItem(row, 6, QTableWidgetItem(f"{item['other_deductions']:.2f}"))
            self.payroll_table.setItem(row, 7, QTableWidgetItem(f"{item['bonuses']:.2f}"))
            self.payroll_table.setItem(row, 8, QTableWidgetItem(f"{item['advances_recovered']:.2f}"))
            self.payroll_table.setItem(row, 9, QTableWidgetItem(f"{item['net_salary']:.2f}"))

        self.absent_card.value_label.setText(str(total_absent))
        self.load_employees()

    def load_employees(self):
        employees = self.db.fetch_all("SELECT e.*, b.name as branch_name FROM employees e JOIN branches b ON e.branch_id = b.id")
        self.attendance_employee.clear()
        self.deduction_employee.clear()
        for emp in employees:
            self.attendance_employee.addItem(emp['name'], emp['id'])
            self.deduction_employee.addItem(emp['name'], emp['id'])
        self.table.setRowCount(len(employees))
        for row, emp in enumerate(employees):
            self.table.setItem(row, 0, QTableWidgetItem(emp['name']))
            self.table.setItem(row, 1, QTableWidgetItem(emp['job_title']))
            self.table.setItem(row, 2, QTableWidgetItem(emp['branch_name']))
            self.table.setItem(row, 3, QTableWidgetItem(str(emp['base_salary'])))
            self.table.setItem(row, 4, QTableWidgetItem(str(emp['allowances'])))
            self.table.setItem(row, 5, QTableWidgetItem(emp['iqama_no'] or ""))
            self.table.setItem(row, 6, QTableWidgetItem(emp['iqama_expiry'] or ""))
            self.table.setItem(row, 7, QTableWidgetItem(emp['passport_no'] or ""))
            self.table.setItem(row, 8, QTableWidgetItem(emp['passport_expiry'] or ""))
            self.table.setItem(row, 9, QTableWidgetItem(emp['work_permit_no'] or ""))
            self.table.setItem(row, 10, QTableWidgetItem(emp['work_permit_expiry'] or ""))
            self.table.setItem(row, 11, QTableWidgetItem(f"{emp['work_card_no'] or ''} / {emp['work_card_expiry'] or ''}".strip(" /")))

        self.total_employees_card.value_label.setText(str(len(employees)))
        alerts = self.hr_logic.get_document_alerts()
        self.doc_alerts_card.value_label.setText(str(len(alerts)))
        outstanding_advances = self.hr_logic.get_outstanding_advances_total()
        self.advances_card.value_label.setText(f"{outstanding_advances:.2f}")

    def refresh_on_show(self):
        self.load_employees()
