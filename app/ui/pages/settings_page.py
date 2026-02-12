from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.config import AppConfig
from app.services.action_log_service import ActionLogService
from app.services.admin_service import AdminService, AdminUser
from app.services.invoice_service import InvoiceService
from app.utils import dialogs


class SettingsPage(QWidget):
    def __init__(
        self,
        config: AppConfig,
        invoice_service: InvoiceService,
        admin_service: AdminService,
        on_theme_changed=None,
        on_admin_updated=None,
        action_log_service: ActionLogService | None = None,
        current_admin_provider=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.invoice_service = invoice_service
        self.admin_service = admin_service
        self.on_theme_changed = on_theme_changed
        self.on_admin_updated = on_admin_updated
        self.action_log_service = action_log_service
        self._current_admin_provider = current_admin_provider
        self.current_admin: AdminUser | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel(self.tr("تنظیمات"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        theme_row = QHBoxLayout()
        theme_label = QLabel(self.tr("پوسته:"))
        theme_row.addWidget(theme_label)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(self.tr("روشن"), "light")
        self.theme_combo.addItem(self.tr("تیره"), "dark")
        self.theme_combo.setCurrentIndex(
            1 if self.config.theme == "dark" else 0
        )
        self.theme_combo.currentIndexChanged.connect(self._apply_theme)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)

        card_layout.addLayout(theme_row)
        layout.addWidget(card)

        account_card = QFrame()
        account_card.setObjectName("Card")
        account_layout = QVBoxLayout(account_card)
        account_layout.setContentsMargins(16, 16, 16, 16)
        account_layout.setSpacing(12)

        account_title = QLabel(self.tr("حساب کاربری"))
        account_title.setStyleSheet("font-weight: 600;")
        account_layout.addWidget(account_title)

        user_row = QHBoxLayout()
        user_label = QLabel(self.tr("کاربر فعلی:"))
        user_row.addWidget(user_label)
        self.user_value = QLabel("-")
        user_row.addWidget(self.user_value, 1)
        account_layout.addLayout(user_row)

        current_row = QHBoxLayout()
        current_label = QLabel(self.tr("رمز عبور فعلی:"))
        current_row.addWidget(current_label)
        self.current_password_input = QLineEdit()
        self.current_password_input.setEchoMode(QLineEdit.Password)
        current_row.addWidget(self.current_password_input, 1)
        account_layout.addLayout(current_row)

        new_row = QHBoxLayout()
        new_label = QLabel(self.tr("رمز عبور جدید:"))
        new_row.addWidget(new_label)
        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(QLineEdit.Password)
        new_row.addWidget(self.new_password_input, 1)
        account_layout.addLayout(new_row)

        confirm_row = QHBoxLayout()
        confirm_label = QLabel(self.tr("تکرار رمز عبور:"))
        confirm_row.addWidget(confirm_label)
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        confirm_row.addWidget(self.confirm_password_input, 1)
        account_layout.addLayout(confirm_row)

        pass_button_row = QHBoxLayout()
        pass_button_row.addStretch(1)
        update_password_button = QPushButton(self.tr("به‌روزرسانی رمز"))
        update_password_button.clicked.connect(self._update_password)
        pass_button_row.addWidget(update_password_button)
        account_layout.addLayout(pass_button_row)

        layout.addWidget(account_card)

        self.admin_card = QFrame()
        self.admin_card.setObjectName("Card")
        admin_layout = QVBoxLayout(self.admin_card)
        admin_layout.setContentsMargins(16, 16, 16, 16)
        admin_layout.setSpacing(12)

        admin_title = QLabel(self.tr("مدیریت مدیران"))
        admin_title.setStyleSheet("font-weight: 600;")
        admin_layout.addWidget(admin_title)

        create_row = QHBoxLayout()
        self.new_admin_username = QLineEdit()
        self.new_admin_username.setPlaceholderText(self.tr("نام کاربری"))
        create_row.addWidget(self.new_admin_username)

        self.new_admin_password = QLineEdit()
        self.new_admin_password.setPlaceholderText(self.tr("رمز عبور"))
        self.new_admin_password.setEchoMode(QLineEdit.Password)
        create_row.addWidget(self.new_admin_password)

        self.new_admin_role = QComboBox()
        self.new_admin_role.addItem(self.tr("کارمند"), "employee")
        self.new_admin_role.addItem(self.tr("مدیر"), "manager")
        create_row.addWidget(self.new_admin_role)

        create_button = QPushButton(self.tr("ایجاد مدیر"))
        create_button.clicked.connect(self._create_admin)
        create_row.addWidget(create_button)
        admin_layout.addLayout(create_row)

        self.admin_table = QTableWidget(0, 2)
        self.admin_table.setHorizontalHeaderLabels(
            [self.tr("نام کاربری"), self.tr("نقش")]
        )
        self.admin_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.admin_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.admin_table.horizontalHeader().setStretchLastSection(True)
        self.admin_table.verticalHeader().setDefaultSectionSize(30)
        admin_layout.addWidget(self.admin_table)

        admin_button_row = QHBoxLayout()
        admin_button_row.addStretch(1)
        delete_button = QPushButton(self.tr("حذف مورد انتخابی"))
        delete_button.clicked.connect(self._delete_selected_admin)
        admin_button_row.addWidget(delete_button)
        admin_layout.addLayout(admin_button_row)

        layout.addWidget(self.admin_card)
        self.admin_card.hide()

        layout.addStretch(1)

    def set_current_admin(self, admin: AdminUser | None) -> None:
        self.current_admin = admin
        if admin is None:
            self.user_value.setText("-")
            self.admin_card.hide()
            return
        self.user_value.setText(f"{admin.username} ({admin.role})")
        if admin.role == "manager":
            self.admin_card.show()
            self._refresh_admins()
        else:
            self.admin_card.hide()

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
            self.admin_table.setItem(row_idx, 0, username_item)
            role_label = (
                self.tr("مدیر")
                if admin.role == "manager"
                else self.tr("کارمند")
            )
            self.admin_table.setItem(row_idx, 1, QTableWidgetItem(role_label))

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

    def _apply_theme(self, _index: int) -> None:
        self.config.theme = str(self.theme_combo.currentData() or "light")
        self.config.save()
        if self.on_theme_changed:
            self.on_theme_changed(self.config.theme)
