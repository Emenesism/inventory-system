from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QBoxLayout,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.config import AppConfig
from app.models.errors import InventoryFileError
from app.services.action_log_service import ActionLogService
from app.services.admin_service import AdminService, AdminUser
from app.services.inventory_service import InventoryService
from app.services.invoice_service import InvoiceService
from app.utils import dialogs
from app.utils.numeric import normalize_numeric_text


class SettingsPage(QWidget):
    _RIGHT_ALIGN = Qt.AlignRight | Qt.AlignAbsolute | Qt.AlignVCenter

    def __init__(
        self,
        config: AppConfig,
        invoice_service: InvoiceService,
        admin_service: AdminService,
        on_theme_changed=None,
        on_admin_updated=None,
        action_log_service: ActionLogService | None = None,
        current_admin_provider=None,
        inventory_service: InventoryService | None = None,
        on_inventory_updated=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        self.config = config
        self.invoice_service = invoice_service
        self.inventory_service = inventory_service
        self.admin_service = admin_service
        self.on_theme_changed = on_theme_changed
        self.on_admin_updated = on_admin_updated
        self.on_inventory_updated = on_inventory_updated
        self.action_log_service = action_log_service
        self._current_admin_provider = current_admin_provider
        self.current_admin: AdminUser | None = None
        self._layout_mode: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title = QLabel(self.tr("تنظیمات"))
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        title.setAlignment(self._RIGHT_ALIGN)
        subtitle = QLabel(self.tr("تنظیمات نمایش، حساب کاربری و مدیریت مدیران"))
        subtitle.setProperty("textRole", "muted")
        subtitle.setAlignment(self._RIGHT_ALIGN)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch(1)

        theme_card = QFrame()
        theme_card.setObjectName("Card")
        theme_layout = QHBoxLayout(theme_card)
        theme_layout.setContentsMargins(12, 8, 12, 8)
        theme_layout.setSpacing(8)
        theme_label = QLabel(self.tr("پوسته"))
        theme_label.setStyleSheet("font-weight: 600;")
        theme_layout.addWidget(theme_label)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(self.tr("روشن"), "light")
        self.theme_combo.addItem(self.tr("تیره"), "dark")
        self._configure_combo_rtl(self.theme_combo)
        self.theme_combo.setMinimumWidth(100)
        self.theme_combo.setCurrentIndex(
            1 if self.config.theme == "dark" else 0
        )
        self.theme_combo.currentIndexChanged.connect(self._apply_theme)
        theme_layout.addWidget(self.theme_combo)
        header.addWidget(theme_card)
        layout.addLayout(header)

        account_card = QFrame()
        account_card.setObjectName("Card")
        account_layout = QVBoxLayout(account_card)
        account_layout.setContentsMargins(16, 16, 16, 16)
        account_layout.setSpacing(12)

        account_title = QLabel(self.tr("حساب کاربری"))
        account_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        account_title.setAlignment(self._RIGHT_ALIGN)
        account_layout.addWidget(account_title)

        account_form = QGridLayout()
        account_form.setHorizontalSpacing(12)
        account_form.setVerticalSpacing(8)

        user_label = QLabel(self.tr("کاربر فعلی"))
        user_label.setProperty("fieldLabel", True)
        user_label.setAlignment(self._RIGHT_ALIGN)
        self.user_value = QLabel("-")
        self.user_value.setStyleSheet("font-weight: 600;")
        self.user_value.setAlignment(self._RIGHT_ALIGN)
        account_form.addWidget(user_label, 0, 0)
        account_form.addWidget(self.user_value, 0, 1)

        current_label = QLabel(self.tr("رمز عبور فعلی"))
        current_label.setProperty("fieldLabel", True)
        current_label.setAlignment(self._RIGHT_ALIGN)
        self.current_password_input = QLineEdit()
        self.current_password_input.setEchoMode(QLineEdit.Password)
        self._configure_line_edit_rtl(self.current_password_input)
        account_form.addWidget(current_label, 1, 0)
        account_form.addWidget(self.current_password_input, 1, 1)

        new_label = QLabel(self.tr("رمز عبور جدید"))
        new_label.setProperty("fieldLabel", True)
        new_label.setAlignment(self._RIGHT_ALIGN)
        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(QLineEdit.Password)
        self._configure_line_edit_rtl(self.new_password_input)
        account_form.addWidget(new_label, 2, 0)
        account_form.addWidget(self.new_password_input, 2, 1)

        confirm_label = QLabel(self.tr("تکرار رمز عبور"))
        confirm_label.setProperty("fieldLabel", True)
        confirm_label.setAlignment(self._RIGHT_ALIGN)
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        self._configure_line_edit_rtl(self.confirm_password_input)
        account_form.addWidget(confirm_label, 3, 0)
        account_form.addWidget(self.confirm_password_input, 3, 1)

        # Keep labels on the right edge, but reduce label-column width
        # so input boxes sit visually closer to labels in RTL layout.
        account_form.setColumnStretch(0, 0)
        account_form.setColumnStretch(1, 1)
        account_layout.addLayout(account_form)

        password_hint = QLabel(
            self.tr("برای امنیت بهتر، رمز عبور حداقل ۶ کاراکتر باشد.")
        )
        password_hint.setProperty("textRole", "muted")
        password_hint.setAlignment(self._RIGHT_ALIGN)
        account_layout.addWidget(password_hint)

        pass_button_row = QHBoxLayout()
        update_password_button = QPushButton(self.tr("به‌روزرسانی رمز"))
        update_password_button.clicked.connect(self._update_password)
        pass_button_row.addWidget(
            update_password_button,
            0,
            self._RIGHT_ALIGN,
        )
        account_layout.addLayout(pass_button_row)

        self.sell_price_alarm_card = QFrame()
        self.sell_price_alarm_card.setObjectName("Card")
        sell_price_alarm_layout = QVBoxLayout(self.sell_price_alarm_card)
        sell_price_alarm_layout.setContentsMargins(12, 12, 12, 12)
        sell_price_alarm_layout.setSpacing(8)

        sell_price_alarm_title = QLabel(self.tr("هشدار اختلاف قیمت فروش"))
        sell_price_alarm_title.setStyleSheet(
            "font-size: 14px; font-weight: 700;"
        )
        sell_price_alarm_title.setAlignment(self._RIGHT_ALIGN)
        sell_price_alarm_layout.addWidget(sell_price_alarm_title)

        sell_price_alarm_form = QGridLayout()
        sell_price_alarm_form.setHorizontalSpacing(10)
        sell_price_alarm_form.setVerticalSpacing(8)

        sell_price_alarm_label = QLabel(self.tr("حداقل اختلاف درصدی"))
        sell_price_alarm_label.setProperty("fieldLabel", True)
        sell_price_alarm_label.setAlignment(self._RIGHT_ALIGN)
        self.sell_price_alarm_input = QLineEdit()
        self.sell_price_alarm_input.setPlaceholderText(self.tr("مثال: 20"))
        self._configure_line_edit_rtl(self.sell_price_alarm_input)
        sell_price_alarm_form.addWidget(sell_price_alarm_label, 0, 0)
        sell_price_alarm_form.addWidget(self.sell_price_alarm_input, 0, 1)
        sell_price_alarm_form.setColumnStretch(0, 0)
        sell_price_alarm_form.setColumnStretch(1, 1)
        sell_price_alarm_layout.addLayout(sell_price_alarm_form)

        sell_price_alarm_button_row = QHBoxLayout()
        self.save_sell_price_alarm_button = QPushButton(
            self.tr("ذخیره درصد هشدار")
        )
        self.save_sell_price_alarm_button.clicked.connect(
            self._save_sell_price_alarm_percent
        )
        sell_price_alarm_button_row.addWidget(
            self.save_sell_price_alarm_button,
            0,
            self._RIGHT_ALIGN,
        )
        sell_price_alarm_layout.addLayout(sell_price_alarm_button_row)

        account_layout.addWidget(self.sell_price_alarm_card)
        self.sell_price_alarm_card.hide()

        self.sell_price_import_card = QFrame()
        self.sell_price_import_card.setObjectName("Card")
        sell_price_import_layout = QVBoxLayout(self.sell_price_import_card)
        sell_price_import_layout.setContentsMargins(12, 12, 12, 12)
        sell_price_import_layout.setSpacing(8)

        sell_price_import_title = QLabel(self.tr("به‌روزرسانی قیمت فروش"))
        sell_price_import_title.setStyleSheet(
            "font-size: 14px; font-weight: 700;"
        )
        sell_price_import_title.setAlignment(self._RIGHT_ALIGN)
        sell_price_import_layout.addWidget(sell_price_import_title)

        sell_price_import_hint = QLabel(
            self.tr(
                "فایل CSV یا XLSX محصولات را انتخاب کنید تا فقط قیمت فروش کالاهای موجود به‌روزرسانی شود (نام کالا تغییر نمی‌کند)."
            )
        )
        sell_price_import_hint.setProperty("textRole", "muted")
        sell_price_import_hint.setWordWrap(True)
        sell_price_import_hint.setAlignment(self._RIGHT_ALIGN)
        sell_price_import_layout.addWidget(sell_price_import_hint)

        sell_price_button_row = QHBoxLayout()
        self.import_sell_price_button = QPushButton(
            self.tr("درون‌ریزی قیمت فروش از فایل")
        )
        self.import_sell_price_button.clicked.connect(self._import_sell_prices)
        sell_price_button_row.addWidget(
            self.import_sell_price_button,
            0,
            self._RIGHT_ALIGN,
        )
        sell_price_import_layout.addLayout(sell_price_button_row)

        account_layout.addWidget(self.sell_price_import_card)
        self.sell_price_import_card.hide()

        self.admin_card = QFrame()
        self.admin_card.setObjectName("Card")
        admin_layout = QVBoxLayout(self.admin_card)
        admin_layout.setContentsMargins(16, 16, 16, 16)
        admin_layout.setSpacing(12)

        admin_title = QLabel(self.tr("مدیریت مدیران"))
        admin_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        admin_title.setAlignment(self._RIGHT_ALIGN)
        admin_layout.addWidget(admin_title)

        create_form = QGridLayout()
        create_form.setHorizontalSpacing(10)
        create_form.setVerticalSpacing(8)

        username_label = QLabel(self.tr("نام کاربری"))
        username_label.setProperty("fieldLabel", True)
        username_label.setAlignment(self._RIGHT_ALIGN)
        self.new_admin_username = QLineEdit()
        self.new_admin_username.setPlaceholderText(self.tr("نام کاربری"))
        self._configure_line_edit_rtl(self.new_admin_username)
        create_form.addWidget(username_label, 0, 0)
        create_form.addWidget(self.new_admin_username, 0, 1)

        password_label = QLabel(self.tr("رمز عبور"))
        password_label.setProperty("fieldLabel", True)
        password_label.setAlignment(self._RIGHT_ALIGN)
        self.new_admin_password = QLineEdit()
        self.new_admin_password.setPlaceholderText(self.tr("رمز عبور"))
        self.new_admin_password.setEchoMode(QLineEdit.Password)
        self._configure_line_edit_rtl(self.new_admin_password)
        create_form.addWidget(password_label, 1, 0)
        create_form.addWidget(self.new_admin_password, 1, 1)

        role_label = QLabel(self.tr("نقش"))
        role_label.setProperty("fieldLabel", True)
        role_label.setAlignment(self._RIGHT_ALIGN)
        self.new_admin_role = QComboBox()
        self.new_admin_role.addItem(self.tr("کارمند"), "employee")
        self.new_admin_role.addItem(self.tr("مدیر"), "manager")
        self._configure_combo_rtl(self.new_admin_role)
        create_form.addWidget(role_label, 2, 0)
        create_form.addWidget(self.new_admin_role, 2, 1)

        create_form.setColumnStretch(0, 0)
        create_form.setColumnStretch(1, 1)
        admin_layout.addLayout(create_form)

        create_button_row = QHBoxLayout()
        create_button = QPushButton(self.tr("ایجاد مدیر"))
        create_button.clicked.connect(self._create_admin)
        create_button_row.addWidget(
            create_button,
            0,
            self._RIGHT_ALIGN,
        )
        admin_layout.addLayout(create_button_row)

        self.admin_table = QTableWidget(0, 2)
        self.admin_table.setHorizontalHeaderLabels(
            [self.tr("نام کاربری"), self.tr("نقش")]
        )
        self.admin_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.admin_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.admin_table.setAlternatingRowColors(True)
        self.admin_table.setLayoutDirection(Qt.RightToLeft)
        admin_header = self.admin_table.horizontalHeader()
        admin_header.setDefaultAlignment(self._RIGHT_ALIGN)
        admin_header.setSectionResizeMode(0, QHeaderView.Stretch)
        admin_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        admin_header.setStretchLastSection(False)
        admin_header.setMinimumSectionSize(72)
        self.admin_table.verticalHeader().setDefaultSectionSize(30)
        self.admin_table.setMinimumHeight(220)
        admin_layout.addWidget(self.admin_table)

        admin_button_row = QHBoxLayout()
        delete_button = QPushButton(self.tr("حذف مورد انتخابی"))
        delete_button.clicked.connect(self._delete_selected_admin)
        admin_button_row.addWidget(
            delete_button,
            0,
            self._RIGHT_ALIGN,
        )
        admin_layout.addLayout(admin_button_row)

        self._content_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self._content_layout.setSpacing(16)
        self._content_layout.addWidget(account_card, 3)
        self._content_layout.addWidget(self.admin_card, 2)
        layout.addLayout(self._content_layout, 1)

        self.admin_card.hide()

        layout.addStretch(1)
        self._apply_responsive_layout(force=True)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_responsive_layout(force=True)

    def set_current_admin(self, admin: AdminUser | None) -> None:
        self.current_admin = admin
        if admin is None:
            self.user_value.setText("-")
            self.admin_card.hide()
            self.sell_price_alarm_card.hide()
            self.sell_price_import_card.hide()
            self._apply_responsive_layout(force=True)
            return
        self.user_value.setText(f"{admin.username} ({admin.role})")
        if admin.role == "manager":
            self.admin_card.show()
            self.sell_price_alarm_card.show()
            self.sell_price_import_card.show()
            self._refresh_admins()
            self._load_sell_price_alarm_percent()
        else:
            self.admin_card.hide()
            self.sell_price_alarm_card.hide()
            self.sell_price_import_card.hide()
        self._apply_responsive_layout(force=True)

    def refresh_admins(self) -> None:
        if self.current_admin is None or self.current_admin.role != "manager":
            return
        self._refresh_admins()

    def _update_password(self) -> None:
        if self.current_admin is None:
            return
        current = self.current_password_input.text()
        new_password = self.new_password_input.text()
        confirm = self.confirm_password_input.text()
        if not current or not new_password:
            dialogs.show_error(
                self,
                self.tr("رمز عبور"),
                self.tr("رمز فعلی و رمز جدید را وارد کنید."),
            )
            return
        if new_password != confirm:
            dialogs.show_error(
                self,
                self.tr("رمز عبور"),
                self.tr("تکرار رمز عبور با مقدار جدید یکسان نیست."),
            )
            return
        authenticated = self.admin_service.authenticate(
            self.current_admin.username, current
        )
        if authenticated is None:
            dialogs.show_error(
                self, self.tr("رمز عبور"), self.tr("رمز عبور فعلی نادرست است.")
            )
            return
        admin = (
            self._current_admin_provider()
            if self._current_admin_provider
            else None
        )
        admin_username = admin.username if admin else None
        self.admin_service.update_password(
            self.current_admin.admin_id,
            new_password,
            admin_username=admin_username,
        )
        if self.action_log_service:
            self.action_log_service.log_action(
                "password_change",
                self.tr("تغییر رمز عبور"),
                self.tr("کاربر: {username}").format(
                    username=self.current_admin.username
                ),
                admin=admin,
            )
        dialogs.show_info(
            self, self.tr("رمز عبور"), self.tr("رمز عبور به‌روزرسانی شد.")
        )
        self.current_password_input.clear()
        self.new_password_input.clear()
        self.confirm_password_input.clear()

    def _create_admin(self) -> None:
        if self.current_admin is None or self.current_admin.role != "manager":
            return
        username = self.new_admin_username.text()
        password = self.new_admin_password.text()
        role = str(self.new_admin_role.currentData())
        admin = (
            self._current_admin_provider()
            if self._current_admin_provider
            else None
        )
        admin_username = admin.username if admin else None
        try:
            self.admin_service.create_admin(
                username=username,
                password=password,
                role=role,
                admin_username=admin_username,
            )
        except ValueError as exc:
            dialogs.show_error(self, self.tr("مدیر"), str(exc))
            return
        self.new_admin_username.clear()
        self.new_admin_password.clear()
        self.new_admin_role.setCurrentIndex(0)
        self._refresh_admins()
        if self.action_log_service:
            self.action_log_service.log_action(
                "admin_create",
                self.tr("ایجاد ادمین جدید"),
                self.tr("نام کاربری: {username}\nنقش: {role}").format(
                    username=username, role=role
                ),
                admin=admin,
            )
        dialogs.show_info(self, self.tr("مدیر"), self.tr("مدیر جدید ایجاد شد."))

    def _refresh_admins(self) -> None:
        admins = self.admin_service.list_admins()
        self.admin_table.setRowCount(len(admins))
        for row_idx, admin in enumerate(admins):
            username_item = QTableWidgetItem(admin.username)
            username_item.setData(Qt.UserRole, admin.admin_id)
            username_item.setTextAlignment(self._RIGHT_ALIGN)
            self.admin_table.setItem(row_idx, 0, username_item)
            role_label = (
                self.tr("مدیر")
                if admin.role == "manager"
                else self.tr("کارمند")
            )
            role_item = QTableWidgetItem(role_label)
            role_item.setTextAlignment(self._RIGHT_ALIGN)
            self.admin_table.setItem(row_idx, 1, role_item)

    def _delete_selected_admin(self) -> None:
        if self.current_admin is None or self.current_admin.role != "manager":
            return
        row = self.admin_table.currentRow()
        if row < 0:
            dialogs.show_error(
                self,
                self.tr("مدیر"),
                self.tr("یک مدیر را برای حذف انتخاب کنید."),
            )
            return
        username_item = self.admin_table.item(row, 0)
        if username_item is None:
            return
        admin_id = username_item.data(Qt.UserRole)
        username = username_item.text()
        if admin_id is None:
            return
        if int(admin_id) == self.current_admin.admin_id:
            dialogs.show_error(
                self,
                self.tr("مدیر"),
                self.tr("امکان حذف مدیر فعلی وجود ندارد."),
            )
            return
        if not dialogs.ask_yes_no(
            self,
            self.tr("مدیر"),
            self.tr("مدیر «{username}» حذف شود؟").format(username=username),
        ):
            return
        admin = (
            self._current_admin_provider()
            if self._current_admin_provider
            else None
        )
        admin_username = admin.username if admin else None
        self.admin_service.delete_admin(
            int(admin_id), admin_username=admin_username
        )
        self._refresh_admins()
        if self.action_log_service:
            self.action_log_service.log_action(
                "admin_delete",
                self.tr("حذف ادمین"),
                self.tr("نام کاربری: {username}").format(username=username),
                admin=admin,
            )
        dialogs.show_info(self, self.tr("مدیر"), self.tr("مدیر حذف شد."))

    def _load_sell_price_alarm_percent(self) -> None:
        if self.inventory_service is None:
            return
        try:
            percent = self.inventory_service.fetch_sell_price_alarm_percent()
        except InventoryFileError:
            percent = (
                self.inventory_service.get_cached_sell_price_alarm_percent()
            )
        text = f"{percent:.2f}".rstrip("0").rstrip(".")
        self.sell_price_alarm_input.setText(text)

    def _save_sell_price_alarm_percent(self) -> None:
        if self.current_admin is None or self.current_admin.role != "manager":
            return
        if self.inventory_service is None:
            dialogs.show_error(
                self,
                self.tr("درصد هشدار قیمت فروش"),
                self.tr("سرویس موجودی در دسترس نیست."),
            )
            return
        raw = self.sell_price_alarm_input.text().strip()
        normalized = normalize_numeric_text(raw)
        if not normalized:
            dialogs.show_error(
                self,
                self.tr("درصد هشدار قیمت فروش"),
                self.tr("درصد هشدار را وارد کنید."),
            )
            return
        try:
            percent = float(normalized)
        except ValueError:
            dialogs.show_error(
                self,
                self.tr("درصد هشدار قیمت فروش"),
                self.tr("فرمت درصد هشدار معتبر نیست."),
            )
            return
        if percent < 0 or percent > 100:
            dialogs.show_error(
                self,
                self.tr("درصد هشدار قیمت فروش"),
                self.tr("درصد هشدار باید بین ۰ تا ۱۰۰ باشد."),
            )
            return
        try:
            saved_percent = (
                self.inventory_service.update_sell_price_alarm_percent(percent)
            )
        except InventoryFileError as exc:
            dialogs.show_error(
                self,
                self.tr("درصد هشدار قیمت فروش"),
                str(exc),
            )
            return
        self.sell_price_alarm_input.setText(
            f"{saved_percent:.2f}".rstrip("0").rstrip(".")
        )
        if self.on_inventory_updated:
            self.on_inventory_updated()
        admin = (
            self._current_admin_provider()
            if self._current_admin_provider
            else self.current_admin
        )
        if self.action_log_service:
            self.action_log_service.log_action(
                "sell_price_alarm_update",
                self.tr("به‌روزرسانی درصد هشدار قیمت فروش"),
                self.tr("درصد جدید: {percent}").format(percent=saved_percent),
                admin=admin,
            )
        dialogs.show_info(
            self,
            self.tr("درصد هشدار قیمت فروش"),
            self.tr("درصد هشدار قیمت فروش ذخیره شد."),
        )

    def _import_sell_prices(self) -> None:
        if self.current_admin is None or self.current_admin.role != "manager":
            return
        if self.inventory_service is None:
            dialogs.show_error(
                self,
                self.tr("به‌روزرسانی قیمت فروش"),
                self.tr("سرویس موجودی در دسترس نیست."),
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("انتخاب فایل قیمت فروش"),
            "",
            self.tr("فایل قیمت (*.xlsx *.xlsm *.csv)"),
        )
        if not file_path:
            return

        try:
            payload = self.inventory_service.import_sell_prices(file_path)
            self.inventory_service.load()
        except InventoryFileError as exc:
            dialogs.show_error(self, self.tr("به‌روزرسانی قیمت فروش"), str(exc))
            return

        if self.on_inventory_updated:
            self.on_inventory_updated()

        total_rows = int(payload.get("total_rows", 0) or 0)
        matched_rows = int(payload.get("matched_rows", 0) or 0)
        updated_products = int(payload.get("updated_products", 0) or 0)
        unmatched_count = int(payload.get("unmatched_count", 0) or 0)
        unmatched_names_raw = payload.get("unmatched_names", [])
        unmatched_names = (
            [str(item) for item in unmatched_names_raw if str(item).strip()]
            if isinstance(unmatched_names_raw, list)
            else []
        )
        format_name = str(payload.get("detected_format", "") or "")
        file_name = str(payload.get("file_name", "") or "")

        details_lines = [
            self.tr("فایل: {file}").format(file=file_name),
            self.tr("نوع تشخیص‌داده‌شده: {mode}").format(mode=format_name or "-"),
            self.tr("کل ردیف‌ها: {count}").format(count=total_rows),
            self.tr("ردیف‌های منطبق: {count}").format(count=matched_rows),
            self.tr("کالاهای به‌روزشده: {count}").format(count=updated_products),
            self.tr("نام‌های بدون تطبیق: {count}").format(count=unmatched_count),
            self.tr("تغییر نام کالا: انجام نمی‌شود"),
        ]
        if unmatched_names:
            details_lines.append(
                self.tr("نمونه نام‌های بدون تطبیق: {names}").format(
                    names="، ".join(unmatched_names[:8])
                )
            )

        admin = (
            self._current_admin_provider()
            if self._current_admin_provider
            else self.current_admin
        )
        if self.action_log_service:
            self.action_log_service.log_action(
                "sell_price_import",
                self.tr("درون‌ریزی قیمت فروش"),
                "\n".join(details_lines),
                admin=admin,
            )

        dialogs.show_info(
            self,
            self.tr("به‌روزرسانی قیمت فروش"),
            "\n".join(details_lines),
        )

    def _apply_theme(self, _index: int) -> None:
        self.config.theme = str(self.theme_combo.currentData() or "light")
        self.config.save()
        if self.on_theme_changed:
            self.on_theme_changed(self.config.theme)

    def _apply_responsive_layout(self, force: bool = False) -> None:
        width = self.width() or self.sizeHint().width()
        scale = self._ui_scale_factor()
        if scale >= 1.15:
            stack_threshold = int(1120 * min(scale, 1.35))
        else:
            stack_threshold = 980
        mode = "stacked" if width < stack_threshold else "split"
        if not force and mode == self._layout_mode:
            return
        self._layout_mode = mode

        if mode == "stacked":
            self._content_layout.setDirection(QBoxLayout.TopToBottom)
            self._content_layout.setSpacing(14 if scale >= 1.15 else 12)
            self._content_layout.setStretch(0, 0)
            self._content_layout.setStretch(1, 0)
        else:
            self._content_layout.setDirection(QBoxLayout.LeftToRight)
            self._content_layout.setSpacing(16)
            self._content_layout.setStretch(0, 3)
            self._content_layout.setStretch(1, 2)

        row_height = 30
        if scale >= 1.15:
            row_height = 38 if mode == "stacked" else 36
        self.admin_table.verticalHeader().setDefaultSectionSize(row_height)
        if scale >= 1.15:
            self.admin_table.setStyleSheet("font-size: 13px;")
        else:
            self.admin_table.setStyleSheet("")

    def _ui_scale_factor(self) -> float:
        screen = self.screen()
        if screen is None:
            app = QApplication.instance()
            if app is not None:
                screen = app.primaryScreen()
        factors: list[float] = [1.0]
        if screen is not None:
            dpi = float(screen.logicalDotsPerInch() or 96.0)
            if dpi > 0:
                factors.append(dpi / 96.0)
            try:
                ratio = float(screen.devicePixelRatio())
            except Exception:  # noqa: BLE001
                ratio = 1.0
            if ratio > 0:
                factors.append(ratio)
        try:
            widget_ratio = float(self.devicePixelRatioF())
        except Exception:  # noqa: BLE001
            widget_ratio = 1.0
        if widget_ratio > 0:
            factors.append(widget_ratio)
        return max(1.0, min(2.0, max(factors)))

    @staticmethod
    def _configure_line_edit_rtl(line_edit: QLineEdit) -> None:
        line_edit.setLayoutDirection(Qt.RightToLeft)
        line_edit.setAlignment(
            Qt.AlignRight | Qt.AlignAbsolute | Qt.AlignVCenter
        )
        line_edit.setCursorMoveStyle(Qt.VisualMoveStyle)

    @staticmethod
    def _configure_combo_rtl(combo: QComboBox) -> None:
        combo.setLayoutDirection(Qt.RightToLeft)
        popup = combo.view()
        if popup is not None:
            popup.setLayoutDirection(Qt.RightToLeft)
        for idx in range(combo.count()):
            combo.setItemData(
                idx,
                Qt.AlignRight | Qt.AlignAbsolute | Qt.AlignVCenter,
                Qt.TextAlignmentRole,
            )
