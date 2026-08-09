from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QPushButton, QFormLayout, QLineEdit,
                             QComboBox, QDateEdit, QLabel, QHeaderView, QMessageBox,
                             QGroupBox, QTabWidget)
from PyQt6.QtCore import QDate, Qt
from ui.common_widgets import create_stat_card, page_header, fill_table, fit_table_height, pin_height
from ui.formatting import money_item, money
from logic.money import parse_money
from logic.accounting import AccountingLogic


class HRModule(QWidget):
    def __init__(self, db_manager, hr_logic):
        super().__init__()
        self.db = db_manager
        self.hr_logic = hr_logic
        self.accounting = AccountingLogic(db_manager)
        self.init_ui()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(12)

        root_layout.addWidget(page_header(
            "الموارد البشرية",
            "بيانات العمال ووثائقهم، الحضور والغياب، السلف والخصومات، والرواتب الشهرية."))

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        root_layout.addWidget(tabs)

        # A plain widget, like the other three tabs - not its own QScrollArea.
        # The whole HR page already scrolls as a single unit (see add_page in
        # main_window.py); wrapping this one tab in a second, inner scroll
        # area on top of that gave "الموظفون" two separate scrollbars for
        # the same content, one nested inside the other - confirmed live,
        # and confusing about which one actually moved what.
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

        # Editing existing employees matters as much as adding them: a salary
        # typed wrong would otherwise be uncorrectable without wiping the database.
        self.employee_picker = QComboBox()
        self.employee_picker.currentIndexChanged.connect(self.on_employee_picked)
        picker_row = QHBoxLayout()
        picker_row.setSpacing(8)
        picker_label = QLabel("تعديل موظف موجود:")
        picker_label.setStyleSheet("font-weight:700; color:#334155;")
        picker_row.addWidget(picker_label)
        picker_row.addWidget(self.employee_picker, 1)
        form_outer.insertLayout(0, picker_row)

        # Asked at deactivation time rather than assumed to be "today": an
        # owner often does the paperwork a few days after someone's actual
        # last day, and payroll for the month they still worked must not
        # silently drop them just because today's date is later.
        termination_row = QHBoxLayout()
        termination_row.setSpacing(8)
        termination_label = QLabel("آخر يوم عمل (عند إنهاء الخدمة):")
        termination_label.setStyleSheet("color:#64748b; font-size:12px;")
        self.termination_date = QDateEdit(QDate.currentDate())
        self.termination_date.setCalendarPopup(True)
        # An employee's last working day cannot be scheduled in the future -
        # this only records that someone already left.
        self.termination_date.setMaximumDate(QDate.currentDate())
        termination_row.addWidget(termination_label)
        termination_row.addWidget(self.termination_date)
        termination_row.addStretch()
        form_outer.addLayout(termination_row)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)
        self.save_btn = QPushButton("إضافة موظف")
        self.save_btn.clicked.connect(self.save_employee)
        self.save_btn.setMinimumHeight(44)
        self.new_btn = QPushButton("موظف جديد")
        self.new_btn.clicked.connect(self.clear_employee_form)
        self.new_btn.setMinimumHeight(44)
        self.new_btn.setStyleSheet(
            "QPushButton { background-color:#64748b; border:1px solid #475569; }"
            "QPushButton:hover { background-color:#475569; border:1px solid #334155; }"
        )
        self.deactivate_btn = QPushButton("إنهاء خدمة الموظف")
        self.deactivate_btn.clicked.connect(self.deactivate_employee)
        self.deactivate_btn.setMinimumHeight(44)
        self.deactivate_btn.setStyleSheet(
            "QPushButton { background-color:#dc2626; border:1px solid #b91c1c; }"
            "QPushButton:hover { background-color:#b91c1c; border:1px solid #991b1b; }"
        )
        buttons_row.addWidget(self.save_btn, 2)
        buttons_row.addWidget(self.new_btn, 1)
        buttons_row.addWidget(self.deactivate_btn, 1)
        form_outer.addSpacing(6)
        form_outer.addLayout(buttons_row)
        setup_layout.addWidget(form_group)
        setup_layout.addStretch()

        attendance_group = QGroupBox("تسجيل الحضور والغياب")
        attendance_layout = QFormLayout(attendance_group)
        attendance_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        attendance_layout.setSpacing(16)
        self.attendance_employee = QComboBox()
        self.attendance_date = QDateEdit(QDate.currentDate())
        self.attendance_date.setCalendarPopup(True)
        # Attendance cannot be recorded for a day that has not happened yet.
        self.attendance_date.setMaximumDate(QDate.currentDate())
        self.attendance_status = QComboBox()
        self.attendance_status.addItem("حاضر", "Present")
        self.attendance_status.addItem("غائب", "Absent")
        self.attendance_note = QLineEdit()
        self._apply_field_widths([self.attendance_employee, self.attendance_date, self.attendance_status, self.attendance_note])
        attendance_btn = QPushButton("تسجيل الحضور/الغياب")
        attendance_btn.clicked.connect(self.record_attendance)
        attendance_layout.addRow("العامل:", self.attendance_employee)
        attendance_layout.addRow("التاريخ:", self.attendance_date)
        attendance_layout.addRow("الحالة:", self.attendance_status)
        attendance_layout.addRow("ملاحظات:", self.attendance_note)
        attendance_layout.addRow(attendance_btn)

        deduction_group = QGroupBox("سلف / خصومات / مكافآت")
        deduction_layout = QFormLayout(deduction_group)
        deduction_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        deduction_layout.setSpacing(16)
        self.deduction_employee = QComboBox()
        self.deduction_type = QComboBox()
        self.deduction_type.addItem("خصم", "Deduction")
        self.deduction_type.addItem("سلفة", "Advance")
        self.deduction_type.addItem("مكافأة", "Bonus")
        self.deduction_date = QDateEdit(QDate.currentDate())
        self.deduction_date.setCalendarPopup(True)
        # A deduction/advance/bonus records something already granted, not a
        # future promise.
        self.deduction_date.setMaximumDate(QDate.currentDate())
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
        tabs.addTab(setup_scroll_widget, "الموظفون")

        # --- Attendance / deductions get their own tab: cramming them under the
        # employee form pushed the payroll controls off the bottom of the window.
        daily_widget = QWidget()
        daily_layout = QVBoxLayout(daily_widget)
        daily_layout.setContentsMargins(6, 6, 6, 6)
        daily_layout.setSpacing(12)
        daily_layout.addWidget(attendance_group)
        daily_layout.addWidget(deduction_group)
        daily_layout.addStretch()
        tabs.addTab(daily_widget, "الحضور والسلف")

        payroll_widget = QWidget()
        payroll_tab_layout = QVBoxLayout(payroll_widget)
        payroll_tab_layout.setContentsMargins(6, 6, 6, 6)
        payroll_tab_layout.setSpacing(12)

        payroll_group = QGroupBox("تشغيل وترحيل الرواتب الشهرية")
        payroll_layout = QFormLayout(payroll_group)
        payroll_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        payroll_layout.setSpacing(16)
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
        payroll_tab_layout.addWidget(payroll_group)

        self.payroll_status_label = QLabel()
        self.payroll_status_label.setWordWrap(True)
        payroll_tab_layout.addWidget(self.payroll_status_label)

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
        # No internal scrollbar: this table was boxed into a fixed height
        # with its own hard-to-notice scrollbar, and three employees showed
        # as two with the third hidden below the fold. It now grows to fit
        # every row, and the page scrolls as a whole (see refresh_payroll).
        self.payroll_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.payroll_table.setMinimumHeight(90)
        payroll_box = QGroupBox("ملخص الرواتب")
        payroll_box_layout = QVBoxLayout(payroll_box)
        payroll_box_layout.addWidget(self.payroll_table)
        # pin_height, not a bare addWidget - a leftover stretch factor here
        # (and a bare addWidget without it) both let the box - a QTabWidget
        # page is handed the tab bar's own full available height regardless
        # of what its own layout asks for - grow well past what its table
        # (sized to fit only its own rows) actually needs, leaving a tall
        # dead gap below it. pin_height is the same fix already used on
        # every other QGroupBox in this app that must not stretch.
        payroll_tab_layout.addWidget(pin_height(payroll_box))

        # Settles account 2200 (رواتب مستحقة الدفع) built up by runs posted
        # with "لا" above - a lump-sum payment against the accrued balance,
        # not tied to any one month's run.
        accrued_box = QGroupBox("سداد رواتب مستحقة سابقاً")
        accrued_layout = QFormLayout(accrued_box)
        accrued_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        accrued_layout.setSpacing(16)
        self.accrued_balance_label = QLabel()
        self.accrued_balance_label.setStyleSheet("font-weight:700; color:#e67e22;")
        self.accrued_pay_amount = QLineEdit()
        self.accrued_pay_amount.setPlaceholderText("0.00")
        self.accrued_pay_method = QComboBox()
        self.accrued_pay_method.addItem("نقدي", "Cash")
        self.accrued_pay_method.addItem("تحويل بنكي", "Bank")
        accrued_pay_btn = QPushButton("تسجيل السداد")
        accrued_pay_btn.clicked.connect(self.pay_accrued_wages)
        accrued_layout.addRow("الرصيد المستحق حالياً:", self.accrued_balance_label)
        accrued_layout.addRow("المبلغ:", self.accrued_pay_amount)
        accrued_layout.addRow("طريقة السداد:", self.accrued_pay_method)
        accrued_layout.addRow(accrued_pay_btn)
        payroll_tab_layout.addWidget(accrued_box)
        payroll_tab_layout.addStretch()

        tabs.addTab(payroll_widget, "الرواتب")

        tables_widget = QWidget()
        tables_layout = QVBoxLayout(tables_widget)
        tables_layout.setContentsMargins(6, 6, 6, 6)
        tables_layout.setSpacing(12)

        self.table = QTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels(["الاسم", "الوظيفة", "الفرع", "الراتب", "البدلات", "رقم الإقامة", "انتهاء الإقامة", "رقم الجواز", "انتهاء الجواز", "رقم تصريح العمل", "انتهاء تصريح العمل", "رقم كرت العمل/انتهاؤه"])
        # Stretch used to force all 12 columns to squeeze into the visible
        # width no matter how long their content was - dates like
        # "2026-08-08" showed as "2026-0", and because Stretch mode forbids
        # the total column width from ever exceeding the viewport, there was
        # no horizontal scrollbar to reach the rest either. ResizeToContents
        # sizes each column to what it actually holds, and the table's own
        # horizontal scrollbar (shown automatically once that total width
        # exceeds the viewport) lets the owner scroll right/left to read
        # every field in full.
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # Horizontal scroll (above) stays on the table itself; vertical
        # scrolling is the page's job now, so the table shows every employee
        # instead of a few behind its own internal scrollbar.
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setMinimumHeight(90)
        employees_box = QGroupBox("قائمة العاملين والوثائق")
        employees_box_layout = QVBoxLayout(employees_box)
        employees_box_layout.addWidget(self.table)
        # pin_height - see the note on payroll_box above for why a bare
        # addWidget (with or without a layout stretch factor) was not
        # enough: a QTabWidget page gets handed the tab bar's own full
        # available height regardless of what its own layout asks for.
        # Reported live as "this page looks suspicious" - a tall dead gap
        # below a table sized to fit only its own row.
        tables_layout.addWidget(pin_height(employees_box))
        tables_layout.addStretch()

        tabs.addTab(tables_widget, "قائمة العاملين")

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

    @property
    def editing_employee_id(self):
        return self.employee_picker.currentData()

    def _clear_employee_fields(self):
        for field in (self.name_input, self.job_input, self.salary_input,
                      self.allowance_input, self.iqama_input, self.passport_input,
                      self.work_permit_input, self.work_card_input):
            field.clear()
        self.save_btn.setText("إضافة موظف")
        self.deactivate_btn.setEnabled(False)
        self.termination_date.setDate(QDate.currentDate())

    def clear_employee_form(self):
        """Resets the form back to 'add a new employee'.

        Cannot rely on setCurrentIndex(0) alone: Qt only emits
        currentIndexChanged when the index actually changes, and this is most
        often called while the picker is *already* on index 0 - right after
        adding someone, or when the form was never in edit mode to begin with.
        In both of those cases the picker's index does not change, no signal
        fires, and on_employee_picked() never runs - so the just-typed data
        silently stayed in the boxes. A second "إضافة موظف" click then saved
        those same values again, and "موظف جديد" appeared to do nothing at
        all in the one situation it is used most: reverting a stray click into
        the picker instead of choosing to edit someone.

        Clearing the fields directly, unconditionally, is what actually fixes
        both symptoms - the index reset is kept only to make the dropdown's
        own display consistent.
        """
        self.employee_picker.blockSignals(True)
        self.employee_picker.setCurrentIndex(0)
        self.employee_picker.blockSignals(False)
        self._clear_employee_fields()

    def on_employee_picked(self):
        emp_id = self.editing_employee_id
        if emp_id is None:
            self._clear_employee_fields()
            return

        emp = self.db.fetch_one("SELECT * FROM employees WHERE id = ?", (emp_id,))
        if not emp:
            return
        self.name_input.setText(emp["name"] or "")
        self.job_input.setText(emp["job_title"] or "")
        index = self.branch_input.findData(emp["branch_id"])
        if index >= 0:
            self.branch_input.setCurrentIndex(index)
        self.salary_input.setText(str(emp["base_salary"] or 0))
        self.allowance_input.setText(str(emp["allowances"] or 0))
        self.iqama_input.setText(emp["iqama_no"] or "")
        self.passport_input.setText(emp["passport_no"] or "")
        self.work_permit_input.setText(emp["work_permit_no"] or "")
        self.work_card_input.setText(emp["work_card_no"] or "")
        for value, widget in (
            (emp["iqama_expiry"], self.iqama_expiry),
            (emp["passport_expiry"], self.passport_expiry),
            (emp["work_permit_expiry"], self.work_permit_expiry),
            (emp["work_card_expiry"], self.work_card_expiry),
        ):
            if value:
                widget.setDate(QDate.fromString(str(value), "yyyy-MM-dd"))
        self.save_btn.setText("حفظ التعديلات")
        self.deactivate_btn.setEnabled(True)

    def save_employee(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "ادخل اسم الموظف")
            return
        job = self.job_input.text().strip()
        branch_id = self.branch_input.currentData()
        try:
            salary = parse_money(self.salary_input.text(), "الراتب الأساسي")
            allowance = parse_money(self.allowance_input.text(), "البدلات")
            if salary < 0 or allowance < 0:
                raise ValueError
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        values = (
            name, job, branch_id, salary, allowance,
            self.iqama_input.text().strip(), self.iqama_expiry.date().toString("yyyy-MM-dd"),
            self.passport_input.text().strip(), self.passport_expiry.date().toString("yyyy-MM-dd"),
            self.work_permit_input.text().strip(), self.work_permit_expiry.date().toString("yyyy-MM-dd"),
            self.work_card_input.text().strip(), self.work_card_expiry.date().toString("yyyy-MM-dd"),
        )

        emp_id = self.editing_employee_id
        if emp_id is None:
            self.db.execute_query(
                """INSERT INTO employees (name, job_title, branch_id, base_salary, allowances,
                   iqama_no, iqama_expiry, passport_no, passport_expiry,
                   work_permit_no, work_permit_expiry, work_card_no, work_card_expiry)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            message = "تم إضافة الموظف بنجاح"
        else:
            self.db.execute_query(
                """UPDATE employees SET name=?, job_title=?, branch_id=?, base_salary=?, allowances=?,
                   iqama_no=?, iqama_expiry=?, passport_no=?, passport_expiry=?,
                   work_permit_no=?, work_permit_expiry=?, work_card_no=?, work_card_expiry=?
                   WHERE id=?""",
                values + (emp_id,),
            )
            message = "تم حفظ التعديلات"

        QMessageBox.information(self, "نجاح", message)
        self.load_employees()
        self.clear_employee_form()
        self.refresh_payroll()

    def deactivate_employee(self):
        emp_id = self.editing_employee_id
        if emp_id is None:
            QMessageBox.warning(self, "تنبيه", "اختر موظفاً من القائمة أولاً")
            return
        name = self.name_input.text().strip()
        last_day = self.termination_date.date().toString("yyyy-MM-dd")
        answer = QMessageBox.question(
            self, "إنهاء خدمة موظف",
            f"سيتم إنهاء خدمة «{name}» اعتباراً من {last_day}.\n\n"
            "لن يظهر بعد ذلك في التنبيهات ولا في رواتب الشهور التالية، لكنه "
            "يبقى محسوباً في رواتب أي شهر لم يُرحَّل بعد ويكون قد عمل خلاله.\n"
            "بياناته وسجله المحاسبي القديم يبقى محفوظاً ولا يُحذف.\n\nمتابعة؟",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.db.execute_query(
            "UPDATE employees SET is_active = 0, terminated_date = ? WHERE id = ?",
            (last_day, emp_id))
        QMessageBox.information(self, "تم", "تم إنهاء خدمة الموظف")
        self.load_employees()
        self.clear_employee_form()
        self.refresh_payroll()

    def record_attendance(self):
        employee_id = self.attendance_employee.currentData()
        if employee_id is None:
            QMessageBox.warning(self, "تنبيه", "اختر العامل أولاً")
            return

        date = self.attendance_date.date().toString("yyyy-MM-dd")
        status = self.attendance_status.currentData()
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
            amount = parse_money(self.deduction_amount.text(), "المبلغ",
                                 allow_blank=False, allow_zero=False)
            if amount <= 0:
                raise ValueError
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
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

        if self.hr_logic.is_payroll_posted(month, year):
            QMessageBox.information(self, "مُرحَّل بالفعل",
                                    f"رواتب شهر {month:02d}/{year} مُرحَّلة مسبقاً ولا يمكن ترحيلها مرة أخرى.")
            return

        confirm = QMessageBox.question(
            self, "تأكيد الترحيل",
            f"سيتم ترحيل رواتب شهر {month:02d}/{year} إلى دفتر اليومية بشكل نهائي. متابعة؟",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Posting used to always assume the whole net amount left the
        # register the same moment - there was no way to say "earned this
        # month, still owed" (رواتب مستحقة), which is exactly the gap the
        # accountant's balance-sheet message pointed at. A "no" here credits
        # account 2200 instead of cash, and the amount can be settled later
        # from "سداد رواتب مستحقة" below without touching this month's entry.
        paid_now = QMessageBox.question(
            self, "هل تم الدفع؟",
            "هل تم دفع صافي الرواتب نقداً/تحويلاً الآن؟\n\n"
            "اختر «نعم» لو الفلوس خرجت فعلاً، أو «لا» لو الرواتب مستحقة "
            "وهتتدفع لاحقاً - هتتسجل كالتزام (رواتب مستحقة الدفع) بدل ما "
            "تتخصم من الخزينة على طول.",
        ) == QMessageBox.StandardButton.Yes

        try:
            self.hr_logic.post_payroll(month, year, paid_now=paid_now)
            QMessageBox.information(self, "نجاح", "تم ترحيل الرواتب إلى المحاسبة بنجاح")
        except Exception as e:
            QMessageBox.critical(self, "خطأ", str(e))
        self.refresh_payroll()

    def pay_accrued_wages(self):
        try:
            amount = parse_money(self.accrued_pay_amount.text(), "المبلغ",
                                 allow_blank=False, allow_zero=False)
            if amount <= 0:
                raise ValueError
        except ValueError as exc:
            QMessageBox.warning(self, "تنبيه", str(exc))
            return

        outstanding = self.accounting.get_account_balance('2200')
        if amount > outstanding + 0.01:
            QMessageBox.warning(self, "تنبيه",
                                f"الرصيد المستحق حالياً {money(outstanding)} ريال فقط، لا يمكن سداد أكثر منه.")
            return

        method = self.accrued_pay_method.currentData()
        cash_account = '1000' if method == 'Cash' else '1001'
        timestamp = QDate.currentDate().toString("yyyy-MM-dd")

        items = [
            {'account_code': '2200', 'debit': amount, 'credit': 0},
            {'account_code': cash_account, 'debit': 0, 'credit': amount},
        ]
        with self.db.transaction() as cursor:
            entry_id = self.db.insert_journal_entry(cursor, timestamp, "سداد رواتب مستحقة", None, items)
            cursor.execute(
                "INSERT INTO accrued_wage_payments (date, amount, method, journal_entry_id) VALUES (?, ?, ?, ?)",
                (timestamp, amount, method, entry_id),
            )

        QMessageBox.information(self, "نجاح", "تم تسجيل سداد الرواتب المستحقة")
        self.accrued_pay_amount.clear()
        self.refresh_payroll()

    def refresh_payroll(self):
        try:
            month = self.payroll_month.currentData()
            year = int(self.payroll_year.text())
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "سنة غير صحيحة")
            return

        # A posted month is a closed book: what actually went to the journal
        # is fixed, so the screen must show that frozen snapshot rather than
        # recalculating live - editing attendance or a deduction afterwards
        # must not make this table quietly disagree with the accounting
        # entry that has already gone out.
        posted = self.hr_logic.is_payroll_posted(month, year)
        if posted:
            payroll = self.hr_logic.get_posted_payroll(month, year)
            self.payroll_status_label.setText(
                f"رواتب شهر {month:02d}/{year} مُرحَّلة بالفعل - المعروض هو ما تم ترحيله فعلياً، "
                "وليس حساباً حياً. أي تعديل لاحق على الحضور أو السلف لا يغيّر هذا الشهر.")
            self.payroll_status_label.setStyleSheet(
                "color:#1f3b57; background:#eef6ff; border:1px solid #cfe0f5;"
                "border-radius:8px; padding:8px 12px; font-weight:700;")
        else:
            payroll = self.hr_logic.get_monthly_payroll(month, year)
            self.payroll_status_label.setText(
                f"معاينة حية لرواتب شهر {month:02d}/{year} - لم تُرحَّل بعد.")
            self.payroll_status_label.setStyleSheet(
                "color:#9a5a06; background:#fdf3e2; border:1px solid #f0d4a3;"
                "border-radius:8px; padding:8px 12px; font-weight:700;")

        self.accrued_balance_label.setText(f"{money(self.accounting.get_account_balance('2200'))} ريال")

        total_absent = 0
        if not fill_table(self.payroll_table, len(payroll), "لا يوجد موظفون مسجلون"):
            self.absent_card.value_label.setText("0")
            fit_table_height(self.payroll_table)
            self.load_employees()
            return
        for row, item in enumerate(payroll):
            total_absent += item['absent_days']
            self.payroll_table.setItem(row, 0, QTableWidgetItem(item['name']))
            self.payroll_table.setItem(row, 1, QTableWidgetItem(item['branch_name'] or ""))
            self.payroll_table.setItem(row, 2, money_item(item['gross_salary'], bold=False))
            self.payroll_table.setItem(row, 3, QTableWidgetItem(str(item['absent_days'])))
            self.payroll_table.setItem(row, 4, QTableWidgetItem(str(item['present_days'])))
            self.payroll_table.setItem(row, 5, money_item(item['absence_deduction'], bold=False))
            self.payroll_table.setItem(row, 6, money_item(item['other_deductions'], bold=False))
            self.payroll_table.setItem(row, 7, money_item(item['bonuses'], bold=False))
            self.payroll_table.setItem(row, 8, money_item(item['advances_recovered'], bold=False))
            self.payroll_table.setItem(row, 9, money_item(item['net_salary'], bold=True))

        self.absent_card.value_label.setText(str(total_absent))
        fit_table_height(self.payroll_table)
        self.load_employees()

    def load_employees(self):
        employees = self.db.fetch_all(
            """SELECT e.*, b.name as branch_name FROM employees e
               JOIN branches b ON e.branch_id = b.id
               WHERE e.is_active = 1 ORDER BY e.name"""
        )
        self.attendance_employee.clear()
        self.deduction_employee.clear()
        for emp in employees:
            self.attendance_employee.addItem(emp['name'], emp['id'])
            self.deduction_employee.addItem(emp['name'], emp['id'])

        # Repopulate the edit picker without firing its change handler, which
        # would otherwise wipe the form while the user is typing in it.
        self.employee_picker.blockSignals(True)
        current = self.employee_picker.currentData()
        self.employee_picker.clear()
        self.employee_picker.addItem("— موظف جديد —", None)
        for emp in employees:
            self.employee_picker.addItem(emp['name'], emp['id'])
        restored = self.employee_picker.findData(current)
        self.employee_picker.setCurrentIndex(restored if restored >= 0 else 0)
        self.employee_picker.blockSignals(False)
        if restored < 0:
            # Whoever was selected is gone (deactivated, or this is the first
            # load) - the same unconditional clear used elsewhere, since
            # relying on the blocked signal here would leave stale text typed
            # for someone who no longer exists in the picker.
            self._clear_employee_fields()

        if not fill_table(self.table, len(employees), "لا يوجد موظفون مسجلون بعد"):
            self.total_employees_card.value_label.setText("0")
            self.doc_alerts_card.value_label.setText(str(len(self.hr_logic.get_document_alerts())))
            self.advances_card.value_label.setText(money(self.hr_logic.get_outstanding_advances_total()))
            fit_table_height(self.table)
            return
        for row, emp in enumerate(employees):
            self.table.setItem(row, 0, QTableWidgetItem(emp['name']))
            self.table.setItem(row, 1, QTableWidgetItem(emp['job_title']))
            self.table.setItem(row, 2, QTableWidgetItem(emp['branch_name']))
            self.table.setItem(row, 3, money_item(emp['base_salary']))
            self.table.setItem(row, 4, money_item(emp['allowances']))
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
        self.advances_card.value_label.setText(money(outstanding_advances))
        fit_table_height(self.table)

    def refresh_on_show(self):
        self.load_employees()
        self.refresh_payroll()
