from __future__ import annotations

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.models.errors import InventoryFileError
from app.services.fuzzy_search import get_fuzzy_matches
from app.services.inventory_service import InventoryService, ProductGroup
from app.utils import dialogs


class GroupSettingsDialog(QDialog):
    _RIGHT_ALIGN = Qt.AlignRight | Qt.AlignAbsolute | Qt.AlignVCenter

    def __init__(
        self,
        inventory_service: InventoryService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.inventory_service = inventory_service
        self._groups: list[ProductGroup] = []
        self._current_group_id: int | None = None

        self.setWindowTitle(self.tr("تنظیمات گروه بندی"))
        self.setModal(True)
        self.setMinimumSize(980, 700)
        self.resize(1140, 780)
        self.setLayoutDirection(Qt.RightToLeft)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title = QLabel(self.tr("تنظیمات گروه بندی"))
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        title.setAlignment(self._RIGHT_ALIGN)
        root.addWidget(title)

        subtitle = QLabel(
            self.tr(
                "در این بخش می‌توانید گروه‌های کالا بسازید و اعضای هر گروه را مدیریت کنید. تغییرات گروه در خرید و فروش روی همه اعضای همان گروه اعمال می‌شود."
            )
        )
        subtitle.setProperty("textRole", "muted")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(self._RIGHT_ALIGN)
        root.addWidget(subtitle)

        content = QHBoxLayout()
        content.setSpacing(16)
        root.addLayout(content, 1)

        groups_card = QFrame()
        groups_card.setObjectName("Card")
        groups_layout = QVBoxLayout(groups_card)
        groups_layout.setContentsMargins(14, 14, 14, 14)
        groups_layout.setSpacing(10)

        groups_title = QLabel(self.tr("گروه‌ها"))
        groups_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        groups_title.setAlignment(self._RIGHT_ALIGN)
        groups_layout.addWidget(groups_title)

        create_row = QHBoxLayout()
        create_row.setSpacing(8)
        self.new_group_input = QLineEdit()
        self.new_group_input.setPlaceholderText(self.tr("نام گروه جدید"))
        self._configure_line_edit_rtl(self.new_group_input)
        self.new_group_input.returnPressed.connect(self._create_group)
        create_row.addWidget(self.new_group_input, 1)

        self.create_group_button = QPushButton(self.tr("ایجاد گروه"))
        self.create_group_button.clicked.connect(self._create_group)
        create_row.addWidget(self.create_group_button)
        groups_layout.addLayout(create_row)

        self.groups_table = QTableWidget(0, 2)
        self.groups_table.setHorizontalHeaderLabels(
            [self.tr("نام گروه"), self.tr("تعداد اعضا")]
        )
        self.groups_table.setAlternatingRowColors(True)
        self.groups_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.groups_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.groups_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.groups_table.setLayoutDirection(Qt.RightToLeft)
        self.groups_table.verticalHeader().setDefaultSectionSize(40)
        groups_header = self.groups_table.horizontalHeader()
        groups_header.setDefaultAlignment(self._RIGHT_ALIGN)
        groups_header.setSectionResizeMode(0, QHeaderView.Stretch)
        groups_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.groups_table.itemSelectionChanged.connect(
            self._on_group_selection_changed
        )
        groups_layout.addWidget(self.groups_table, 1)

        content.addWidget(groups_card, 2)

        details_card = QFrame()
        details_card.setObjectName("Card")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(14, 14, 14, 14)
        details_layout.setSpacing(10)

        self.details_title = QLabel(self.tr("جزئیات گروه"))
        self.details_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        self.details_title.setAlignment(self._RIGHT_ALIGN)
        details_layout.addWidget(self.details_title)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self.group_name_input = QLineEdit()
        self.group_name_input.setPlaceholderText(self.tr("نام گروه"))
        self._configure_line_edit_rtl(self.group_name_input)
        self.group_name_input.returnPressed.connect(self._rename_group)
        name_row.addWidget(self.group_name_input, 1)

        self.rename_group_button = QPushButton(self.tr("ذخیره نام"))
        self.rename_group_button.clicked.connect(self._rename_group)
        name_row.addWidget(self.rename_group_button)
        details_layout.addLayout(name_row)

        add_member_hint = QLabel(
            self.tr("کالای مورد نظر را وارد کنید و به گروه اضافه کنید.")
        )
        add_member_hint.setProperty("textRole", "muted")
        add_member_hint.setAlignment(self._RIGHT_ALIGN)
        details_layout.addWidget(add_member_hint)

        add_member_row = QHBoxLayout()
        add_member_row.setSpacing(8)
        self.add_member_input = QLineEdit()
        self.add_member_input.setPlaceholderText(self.tr("نام کالا"))
        self._configure_line_edit_rtl(self.add_member_input)
        self.add_member_input.textChanged.connect(self._update_member_completer)
        self.add_member_input.returnPressed.connect(self._add_member)
        add_member_row.addWidget(self.add_member_input, 1)

        self.add_member_button = QPushButton(self.tr("افزودن به گروه"))
        self.add_member_button.clicked.connect(self._add_member)
        add_member_row.addWidget(self.add_member_button)
        details_layout.addLayout(add_member_row)

        self.members_table = QTableWidget(0, 1)
        self.members_table.setHorizontalHeaderLabels([self.tr("اعضای گروه")])
        self.members_table.setAlternatingRowColors(True)
        self.members_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.members_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.members_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.members_table.setLayoutDirection(Qt.RightToLeft)
        self.members_table.verticalHeader().setDefaultSectionSize(40)
        members_header = self.members_table.horizontalHeader()
        members_header.setDefaultAlignment(self._RIGHT_ALIGN)
        members_header.setSectionResizeMode(0, QHeaderView.Stretch)
        details_layout.addWidget(self.members_table, 1)

        detail_buttons = QHBoxLayout()
        detail_buttons.setSpacing(8)
        self.remove_member_button = QPushButton(self.tr("حذف عضو انتخابی"))
        self.remove_member_button.clicked.connect(self._remove_selected_member)
        detail_buttons.addWidget(self.remove_member_button)

        detail_buttons.addStretch(1)

        self.delete_group_button = QPushButton(self.tr("حذف گروه"))
        self.delete_group_button.clicked.connect(self._delete_group)
        detail_buttons.addWidget(self.delete_group_button)
        details_layout.addLayout(detail_buttons)

        content.addWidget(details_card, 3)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton(self.tr("بستن"))
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        root.addLayout(close_row)

        self._set_detail_enabled(False)
        self._load_groups()

    def _load_groups(self, selected_group_id: int | None = None) -> None:
        try:
            self._groups = self.inventory_service.list_product_groups()
        except InventoryFileError as exc:
            dialogs.show_error(self, self.tr("گروه بندی"), str(exc))
            return

        self.groups_table.setRowCount(len(self._groups))
        for row_idx, group in enumerate(self._groups):
            name_item = QTableWidgetItem(group.name)
            name_item.setData(Qt.UserRole, group.group_id)
            name_item.setTextAlignment(self._RIGHT_ALIGN)
            self.groups_table.setItem(row_idx, 0, name_item)

            count_item = QTableWidgetItem(str(len(group.members)))
            count_item.setTextAlignment(self._RIGHT_ALIGN)
            self.groups_table.setItem(row_idx, 1, count_item)

        target_group_id = selected_group_id
        if target_group_id is None and self._groups:
            target_group_id = self._groups[0].group_id

        if target_group_id is None:
            self._current_group_id = None
            self._populate_group_details(None)
            return

        for row_idx, group in enumerate(self._groups):
            if group.group_id == target_group_id:
                self.groups_table.selectRow(row_idx)
                self._populate_group_details(group)
                return

        self._current_group_id = None
        self._populate_group_details(None)

    def _populate_group_details(self, group: ProductGroup | None) -> None:
        self._current_group_id = group.group_id if group else None
        self._set_detail_enabled(group is not None)
        if group is None:
            self.details_title.setText(self.tr("جزئیات گروه"))
            self.group_name_input.clear()
            self.add_member_input.clear()
            self.members_table.setRowCount(0)
            return

        self.details_title.setText(
            self.tr("جزئیات گروه: {name}").format(name=group.name)
        )
        self.group_name_input.setText(group.name)
        self.add_member_input.clear()
        self.members_table.setRowCount(len(group.members))
        for row_idx, member in enumerate(group.members):
            item = QTableWidgetItem(member.product_name)
            item.setData(Qt.UserRole, member.product_id)
            item.setTextAlignment(self._RIGHT_ALIGN)
            self.members_table.setItem(row_idx, 0, item)

    def _set_detail_enabled(self, enabled: bool) -> None:
        self.group_name_input.setEnabled(enabled)
        self.rename_group_button.setEnabled(enabled)
        self.add_member_input.setEnabled(enabled)
        self.add_member_button.setEnabled(enabled)
        self.members_table.setEnabled(enabled)
        self.remove_member_button.setEnabled(enabled)
        self.delete_group_button.setEnabled(enabled)

    def _selected_group(self) -> ProductGroup | None:
        if self._current_group_id is None:
            return None
        for group in self._groups:
            if group.group_id == self._current_group_id:
                return group
        return None

    def _on_group_selection_changed(self) -> None:
        row = self.groups_table.currentRow()
        if row < 0 or row >= len(self._groups):
            self._populate_group_details(None)
            return
        self._populate_group_details(self._groups[row])

    def _create_group(self) -> None:
        name = self.new_group_input.text().strip()
        if not name:
            dialogs.show_error(
                self,
                self.tr("گروه بندی"),
                self.tr("نام گروه را وارد کنید."),
            )
            return
        try:
            group = self.inventory_service.create_product_group(name)
        except InventoryFileError as exc:
            dialogs.show_error(self, self.tr("گروه بندی"), str(exc))
            return
        self.new_group_input.clear()
        self._load_groups(selected_group_id=group.group_id)

    def _rename_group(self) -> None:
        group = self._selected_group()
        if group is None:
            return
        name = self.group_name_input.text().strip()
        if not name:
            dialogs.show_error(
                self,
                self.tr("گروه بندی"),
                self.tr("نام گروه را وارد کنید."),
            )
            return
        try:
            updated = self.inventory_service.update_product_group(
                group.group_id,
                name=name,
            )
        except InventoryFileError as exc:
            dialogs.show_error(self, self.tr("گروه بندی"), str(exc))
            return
        self._load_groups(selected_group_id=updated.group_id)

    def _add_member(self) -> None:
        group = self._selected_group()
        if group is None:
            return
        product_name = self.add_member_input.text().strip()
        if not product_name:
            dialogs.show_error(
                self,
                self.tr("گروه بندی"),
                self.tr("نام کالا را وارد کنید."),
            )
            return
        current_members = [member.product_name for member in group.members]
        if product_name in current_members:
            dialogs.show_error(
                self,
                self.tr("گروه بندی"),
                self.tr("این کالا قبلاً در گروه وجود دارد."),
            )
            return
        updated_members = current_members + [product_name]
        try:
            updated = self.inventory_service.update_product_group(
                group.group_id,
                members=updated_members,
            )
        except InventoryFileError as exc:
            dialogs.show_error(self, self.tr("گروه بندی"), str(exc))
            return
        self.add_member_input.clear()
        self._load_groups(selected_group_id=updated.group_id)

    def _remove_selected_member(self) -> None:
        group = self._selected_group()
        if group is None:
            return
        row = self.members_table.currentRow()
        if row < 0 or row >= len(group.members):
            dialogs.show_error(
                self,
                self.tr("گروه بندی"),
                self.tr("یک عضو را انتخاب کنید."),
            )
            return
        member_name = group.members[row].product_name
        updated_members = [
            member.product_name
            for idx, member in enumerate(group.members)
            if idx != row
        ]
        try:
            updated = self.inventory_service.update_product_group(
                group.group_id,
                members=updated_members,
            )
        except InventoryFileError as exc:
            dialogs.show_error(self, self.tr("گروه بندی"), str(exc))
            return
        self._load_groups(selected_group_id=updated.group_id)
        self.add_member_input.clear()
        self.add_member_input.setPlaceholderText(
            self.tr("عضو «{name}» حذف شد").format(name=member_name)
        )

    def _delete_group(self) -> None:
        group = self._selected_group()
        if group is None:
            return
        if not dialogs.ask_yes_no(
            self,
            self.tr("گروه بندی"),
            self.tr("گروه «{name}» حذف شود؟").format(name=group.name),
        ):
            return
        try:
            self.inventory_service.delete_product_group(group.group_id)
        except InventoryFileError as exc:
            dialogs.show_error(self, self.tr("گروه بندی"), str(exc))
            return
        self._load_groups()

    def _update_member_completer(self, text: str) -> None:
        product_names = self.inventory_service.get_product_names()
        matches = get_fuzzy_matches(text, product_names)
        completer = self.add_member_input.completer()

        if not matches:
            if completer:
                completer.popup().hide()
            return

        if completer is None:
            model = QStringListModel(matches)
            completer = QCompleter(model, self.add_member_input)
            completer.setCompletionMode(QCompleter.PopupCompletion)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            self.add_member_input.setCompleter(completer)
        else:
            model = completer.model()
            if isinstance(model, QStringListModel):
                model.setStringList(matches)
            else:
                completer.setModel(QStringListModel(matches))
        completer.complete()

    @staticmethod
    def _configure_line_edit_rtl(line_edit: QLineEdit) -> None:
        line_edit.setLayoutDirection(Qt.RightToLeft)
        line_edit.setAlignment(
            Qt.AlignRight | Qt.AlignAbsolute | Qt.AlignVCenter
        )
        line_edit.setCursorMoveStyle(Qt.VisualMoveStyle)
