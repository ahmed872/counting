from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QFormLayout, QLineEdit, 
                             QComboBox, QDateEdit, QLabel, QHeaderView, QMessageBox,
                             QGroupBox, QTabWidget, QGridLayout, QScrollArea, QSizePolicy)
from PyQt6.QtCore import QDate, Qt

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

        subtitle = QLabel("متابعة بيانات العمال، الوثائق، الحضور، والرواتب الشهرية من مكان واحد")
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
        cards_row.addWidget(self.info_card("إجمالي العاملين", "0"))
        cards_row.addWidget(self.info_card("تنبيهات الوثائق", "0"))
        cards_row.addWidget(self.info_card("الغياب الحالي", "0"))
        setup_layout.addLayout(cards_row)

        form_group = QGroupBox("بيانات العامل")
        form_group.setStyleSheet("QGroupBox { font-weight: 700; border: 1px solid #d8e0ea; border-radius: 12px; margin-top: 10px; padding-top: 16px; }")
        form_layout = QGridLayout(form_group)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)
        form_layout.setColumnStretch(0, 1)
        form_layout.setColumnStretch(1, 1)
        form_layout.setColumnStretch(2, 1)
        self.name_input = QLineEdit()
        self.job_input = QLineEdit()
        self.branch_input = QComboBox()
        self.branch_input.addItem("فرع الرياض", 1)
        self.branch_input.addItem("فرع جدة", 2)
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

        form_layout.addWidget(QLabel("الاسم"), 0, 0)
        form_layout.addWidget(self.name_input, 1, 0)
        form_layout.addWidget(QLabel("الوظيفة"), 0, 1)
        form_layout.addWidget(self.job_input, 1, 1)
        form_layout.addWidget(QLabel("الفرع"), 0, 2)
        form_layout.addWidget(self.branch_input, 1, 2)
        form_layout.addWidget(QLabel("الراتب الأساسي"), 2, 0)
        form_layout.addWidget(self.salary_input, 3, 0)
        form_layout.addWidget(QLabel("البدلات"), 2, 1)
        form_layout.addWidget(self.allowance_input, 3, 1)
        form_layout.addWidget(QLabel("رقم الإقامة"), 2, 2)
        form_layout.addWidget(self.iqama_input, 3, 2)
        form_layout.addWidget(QLabel("انتهاء الإقامة"), 4, 0)
        form_layout.addWidget(self.iqama_expiry, 5, 0)
        form_layout.addWidget(QLabel("رقم الجواز"), 4, 1)
        form_layout.addWidget(self.passport_input, 5, 1)
        form_layout.addWidget(QLabel("انتهاء الجواز"), 4, 2)
        form_layout.addWidget(self.passport_expiry, 5, 2)
        form_layout.addWidget(QLabel("رقم تصريح العمل"), 6, 0)
        form_layout.addWidget(self.work_permit_input, 7, 0)
        form_layout.addWidget(QLabel("انتهاء تصريح العمل"), 6, 1)
        form_layout.addWidget(self.work_permit_expiry, 7, 1)
        form_layout.addWidget(QLabel("رقم كرت العمل"), 6, 2)
        form_layout.addWidget(self.work_card_input, 7, 2)
        form_layout.addWidget(QLabel("انتهاء كرت العمل"), 8, 0)
        form_layout.addWidget(self.work_card_expiry, 9, 0)

        add_btn = QPushButton("إضافة موظف")
        add_btn.clicked.connect(self.add_employee)
        add_btn.setMinimumHeight(42)
        form_layout.addWidget(add_btn, 9, 2)
        setup_layout.addWidget(form_group)

        action_row = QVBoxLayout()
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

        payroll_group = QGroupBox("ملخص الرواتب الشهري")
        payroll_layout = QFormLayout(payroll_group)
        payroll_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.payroll_month = QComboBox()
        for month in range(1, 13):
            self.payroll_month.addItem(f"{month:02d}", month)
        self.payroll_month.setCurrentIndex(QDate.currentDate().month() - 1)
        self.payroll_year = QLineEdit(str(QDate.currentDate().year()))
        self._apply_field_widths([self.payroll_month, self.payroll_year])
        payroll_btn = QPushButton("حساب الرواتب")
        payroll_btn.clicked.connect(self.refresh_payroll)
        payroll_layout.addRow("الشهر:", self.payroll_month)
        payroll_layout.addRow("السنة:", self.payroll_year)
        payroll_layout.addRow(payroll_btn)
        action_row.addWidget(payroll_group)
        setup_layout.addLayout(action_row)

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
        self.payroll_table.setColumnCount(8)
        self.payroll_table.setHorizontalHeaderLabels(["العامل", "الفرع", "الراتب الإجمالي", "أيام الغياب", "أيام الحضور", "اليومية", "الخصم", "الصافي"])
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

        # Employee Table
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

    def info_card(self, title, value):
        frame = QGroupBox()
        frame.setStyleSheet("QGroupBox { background:#f8fbff; border:1px solid #dbe3ec; border-radius:12px; padding:10px; font-weight:600; }")
        frame.setMinimumHeight(88)
        layout = QVBoxLayout(frame)
        title_label = QLabel(title)
        title_label.setStyleSheet("color:#64748b;")
        value_label = QLabel(value)
        value_label.setStyleSheet("font-size:22px; font-weight:700; color:#1f3b57;")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        frame.value_label = value_label
        return frame

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
        job = self.job_input.text().strip()
        branch_id = self.branch_input.currentData()
        salary = float(self.salary_input.text() or 0)
        allowance = float(self.allowance_input.text() or 0)
        iqama = self.iqama_expiry.date().toString("yyyy-MM-dd")
        passport = self.passport_expiry.date().toString("yyyy-MM-dd")
        work_permit = self.work_permit_expiry.date().toString("yyyy-MM-dd")
        work_card = self.work_card_expiry.date().toString("yyyy-MM-dd")

        self.db.execute_query(
            "INSERT INTO employees (name, job_title, branch_id, base_salary, allowances, iqama_no, iqama_expiry, passport_no, passport_expiry, work_permit_no, work_permit_expiry, work_card_no, work_card_expiry) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, job, branch_id, salary, allowance, self.iqama_input.text().strip(), iqama, self.passport_input.text().strip(), passport, self.work_permit_input.text().strip(), work_permit, self.work_card_input.text().strip(), work_card)
        )
        QMessageBox.information(self, "نجاح", "تم إضافة الموظف بنجاح")
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
        for row, item in enumerate(payroll):
            self.payroll_table.setItem(row, 0, QTableWidgetItem(item['name']))
            self.payroll_table.setItem(row, 1, QTableWidgetItem(item['branch_name'] or ""))
            self.payroll_table.setItem(row, 2, QTableWidgetItem(f"{item['gross_salary']:.2f}"))
            self.payroll_table.setItem(row, 3, QTableWidgetItem(str(item['absent_days'])))
            self.payroll_table.setItem(row, 4, QTableWidgetItem(str(item['present_days'])))
            self.payroll_table.setItem(row, 5, QTableWidgetItem(f"{item['daily_rate']:.2f}"))
            self.payroll_table.setItem(row, 6, QTableWidgetItem(f"{item['absence_deduction']:.2f}"))
            self.payroll_table.setItem(row, 7, QTableWidgetItem(f"{item['net_salary']:.2f}"))

        self.load_employees()

    def load_employees(self):
        employees = self.db.fetch_all("SELECT e.*, b.name as branch_name FROM employees e JOIN branches b ON e.branch_id = b.id")
        self.attendance_employee.clear()
        for emp in employees:
            self.attendance_employee.addItem(emp['name'], emp['id'])
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
