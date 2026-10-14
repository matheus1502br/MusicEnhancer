"""Tabela personalizada de músicas com Drag & Drop e numeração tabular."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QMimeData, QModelIndex, QRect
from PySide6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontDatabase,
    QColor,
    QBrush,
)
from PySide6.QtWidgets import (
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
    QHBoxLayout,
    QCheckBox,
    QLabel,
)

if TYPE_CHECKING:
    from .main_window import MainWindow


class TabularNumericDelegate(QStyledItemDelegate):
    """Delegate que força alinhamento à direita e numeração tabular para colunas numéricas."""

    NUMERIC_COLUMNS = {2, 4, 5, 6}  # Duração, LUFS, True Peak, Bitrate (índices 0-based)

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        super().initStyleOption(option, index)
        if index.column() in self.NUMERIC_COLUMNS:
            option.displayAlignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            # Força fonte monoespaçada com tabular-nums via QFont
            font = QFont("Segoe UI Variable", 13)
            if not font.exactMatch():
                font = QFont("JetBrains Mono", 13)
            if not font.exactMatch():
                font = QFont("Consolas", 13)
            font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            option.font = font

    def paint(self, painter, option, index):
        # Coloração condicional para LUFS e True Peak
        if index.column() == 4:  # LUFS Atual
            try:
                value = float(index.data(Qt.ItemDataRole.DisplayRole) or "0")
                if value <= -14.0:
                    option.palette.setColor(option.palette.ColorRole.Text, QColor("#10B981"))  # Verde
                else:
                    option.palette.setColor(option.palette.ColorRole.Text, QColor("#FAFAFA"))
            except (ValueError, TypeError):
                pass
        elif index.column() == 5:  # True Peak
            try:
                value = float(index.data(Qt.ItemDataRole.DisplayRole) or "0")
                if value > -1.0:
                    option.palette.setColor(option.palette.ColorRole.Text, QColor("#F97316"))  # Laranja
                else:
                    option.palette.setColor(option.palette.ColorRole.Text, QColor("#FAFAFA"))
            except (ValueError, TypeError):
                pass
        super().paint(painter, option, index)


class CheckBoxHeader(QHeaderView):
    """Cabeçalho com checkbox 'Selecionar Todos' na coluna 0."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._checked = False
        self.setSectionsClickable(True)
        self.sectionClicked.connect(self._on_section_clicked)

    def _on_section_clicked(self, logical_index: int):
        if logical_index == 0:
            self._checked = not self._checked
            self.updateSection(0)
            table = self.parent()
            if isinstance(table, MusicTableWidget):
                table.set_all_rows_checked(self._checked)

    def paintSection(self, painter, rect, logical_index):
        super().paintSection(painter, rect, logical_index)
        if logical_index == 0:
            # Desenha checkbox no centro da seção
            from PySide6.QtWidgets import QStyleOptionButton, QStyle
            opt = QStyleOptionButton()
            opt.rect = QRect(
                rect.center().x() - 9,
                rect.center().y() - 9,
                18, 18
            )
            opt.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Active
            if self._checked:
                opt.state |= QStyle.StateFlag.State_On
            else:
                opt.state |= QStyle.StateFlag.State_Off
            self.style().drawControl(QStyle.ControlElement.CE_CheckBox, opt, painter, self)


class MusicTableWidget(QTableWidget):
    """Tabela de músicas com Drag & Drop, numeração tabular e badges de status."""

    SUPPORTED_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".aac"}

    # Índices das colunas
    COL_CHECK = 0
    COL_NAME = 1
    COL_DURATION = 2
    COL_FORMAT = 3
    COL_LUFS = 4
    COL_TRUE_PEAK = 5
    COL_BITRATE = 6
    COL_STATUS = 7

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_table()
        self._setup_drag_drop()
        self._setup_delegate()

    def _setup_table(self) -> None:
        # Configuração básica
        self.setColumnCount(8)
        self.setHorizontalHeaderLabels([
            "",           # Checkbox
            "Nome da Faixa",
            "Duração",
            "Formato",
            "LUFS Atual",
            "True Peak",
            "Bitrate",
            "Status",
        ])

        # Header customizado com checkbox na coluna 0
        self._custom_header = CheckBoxHeader(Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(self._custom_header)

        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self.COL_CHECK, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_DURATION, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_FORMAT, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_LUFS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_TRUE_PEAK, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_BITRATE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeMode.Fixed)

        self.setColumnWidth(self.COL_CHECK, 48)
        self.setColumnWidth(self.COL_STATUS, 140)
        header.setMinimumSectionSize(0)  # Default
        header.resizeSection(self.COL_DURATION, 75)
        header.resizeSection(self.COL_FORMAT, 65)
        header.resizeSection(self.COL_LUFS, 85)
        header.resizeSection(self.COL_TRUE_PEAK, 85)
        header.resizeSection(self.COL_BITRATE, 95)
        header.resizeSection(self.COL_STATUS, 140)

        # Comportamento
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(44)
        self.setSortingEnabled(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Fonte base
        font = QFont("Segoe UI Variable", 13)
        if not font.exactMatch():
            font = QFont("Segoe UI", 13)
        self.setFont(font)

    def _setup_drag_drop(self) -> None:
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def _setup_delegate(self) -> None:
        self.setItemDelegate(TabularNumericDelegate(self))

    # ------------------------------------------------------------------
    # Drag & Drop
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            valid = any(
                url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in self.SUPPORTED_EXTS
                for url in urls
            )
            if valid:
                event.acceptProposedAction()
                self.viewport().setProperty("dragActive", True)
                self.viewport().style().unpolish(self.viewport())
                self.viewport().style().polish(self.viewport())
                return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.viewport().setProperty("dragActive", False)
        self.viewport().style().unpolish(self.viewport())
        self.viewport().style().polish(self.viewport())
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.viewport().setProperty("dragActive", False)
        self.viewport().style().unpolish(self.viewport())
        self.viewport().style().polish(self.viewport())

        if not event.mimeData().hasUrls():
            event.ignore()
            return

        files = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.suffix.lower() in self.SUPPORTED_EXTS:
                    files.append(str(path))

        if files:
            event.acceptProposedAction()
            self.files_dropped.emit(files)
        else:
            event.ignore()

    # ------------------------------------------------------------------
    # API Pública
    # ------------------------------------------------------------------
    def add_track(self, track_data: dict) -> int:
        """Adiciona uma faixa à tabela. Retorna o índice da linha."""
        row = self.rowCount()
        self.insertRow(row)

        # Coluna 0: Checkbox
        chk_widget = QWidget()
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.setContentsMargins(0, 0, 0, 0)
        chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        checkbox = QCheckBox()
        checkbox.setProperty("row", row)
        checkbox.stateChanged.connect(self._on_checkbox_changed)
        chk_layout.addWidget(checkbox)
        self.setCellWidget(row, self.COL_CHECK, chk_widget)

        # Coluna 1: Nome
        name_item = QTableWidgetItem(track_data.get("name", "—"))
        name_item.setData(Qt.ItemDataRole.UserRole, track_data.get("path", ""))
        name_item.setToolTip(track_data.get("path", ""))
        self.setItem(row, self.COL_NAME, name_item)

        # Coluna 2: Duração (tabular)
        dur_item = QTableWidgetItem(track_data.get("duration", "—"))
        dur_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, self.COL_DURATION, dur_item)

        # Coluna 3: Formato
        fmt_item = QTableWidgetItem(track_data.get("format", "—").upper())
        fmt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, self.COL_FORMAT, fmt_item)

        # Coluna 4: LUFS Atual
        lufs_item = QTableWidgetItem(f"{track_data.get('lufs', 0):.1f}")
        lufs_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lufs_item.setData(Qt.ItemDataRole.UserRole, track_data.get("lufs", 0))
        self.setItem(row, self.COL_LUFS, lufs_item)

        # Coluna 5: True Peak
        tp_item = QTableWidgetItem(f"{track_data.get('true_peak', 0):.1f}")
        tp_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tp_item.setData(Qt.ItemDataRole.UserRole, track_data.get("true_peak", 0))
        self.setItem(row, self.COL_TRUE_PEAK, tp_item)

        # Coluna 6: Bitrate
        br_item = QTableWidgetItem(track_data.get("bitrate", "—"))
        br_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, self.COL_BITRATE, br_item)

        # Coluna 7: Status Badge
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(8, 4, 8, 4)
        status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge = QLabel(track_data.get("status", "Pendente"))
        badge.setProperty("badge", True)
        badge.setProperty("status", track_data.get("status_key", "pending"))
        status_layout.addWidget(badge)
        self.setCellWidget(row, self.COL_STATUS, status_widget)

        return row

    def set_all_rows_checked(self, checked: bool) -> None:
        for row in range(self.rowCount()):
            widget = self.cellWidget(row, self.COL_CHECK)
            if widget:
                checkbox = widget.findChild(QCheckBox)
                if checkbox:
                    checkbox.blockSignals(True)
                    checkbox.setChecked(checked)
                    checkbox.blockSignals(False)

    def get_selected_rows(self) -> list[int]:
        """Retorna índices das linhas com checkbox marcado."""
        rows = []
        for row in range(self.rowCount()):
            widget = self.cellWidget(row, self.COL_CHECK)
            if widget:
                checkbox = widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    rows.append(row)
        return rows

    def get_track_data(self, row: int) -> dict | None:
        """Retorna os dados da faixa na linha especificada."""
        if row < 0 or row >= self.rowCount():
            return None
        name_item = self.item(row, self.COL_NAME)
        if not name_item:
            return None
        return {
            "name": name_item.text(),
            "path": name_item.data(Qt.ItemDataRole.UserRole),
            "duration": self.item(row, self.COL_DURATION).text() if self.item(row, self.COL_DURATION) else "—",
            "format": self.item(row, self.COL_FORMAT).text() if self.item(row, self.COL_FORMAT) else "—",
            "lufs": self.item(row, self.COL_LUFS).data(Qt.ItemDataRole.UserRole) if self.item(row, self.COL_LUFS) else 0.0,
            "true_peak": self.item(row, self.COL_TRUE_PEAK).data(Qt.ItemDataRole.UserRole) if self.item(row, self.COL_TRUE_PEAK) else 0.0,
            "bitrate": self.item(row, self.COL_BITRATE).text() if self.item(row, self.COL_BITRATE) else "—",
            "status": self._get_status_text(row),
            "status_key": self._get_status_key(row),
        }

    def _get_status_text(self, row: int) -> str:
        widget = self.cellWidget(row, self.COL_STATUS)
        if widget:
            badge = widget.findChild(QLabel)
            if badge:
                return badge.text()
        return "—"

    def _get_status_key(self, row: int) -> str:
        widget = self.cellWidget(row, self.COL_STATUS)
        if widget:
            badge = widget.findChild(QLabel)
            if badge:
                return badge.property("status") or "pending"
        return "pending"

    def update_row_status(self, row: int, status_key: str, status_text: str | None = None) -> None:
        """Atualiza o badge de status de uma linha."""
        widget = self.cellWidget(row, self.COL_STATUS)
        if widget:
            badge = widget.findChild(QLabel)
            if badge:
                badge.setProperty("status", status_key)
                badge.setText(status_text or status_key.replace("_", " ").title())
                badge.style().unpolish(badge)
                badge.style().polish(badge)

    def _on_checkbox_changed(self, state: int) -> None:
        checkbox = self.sender()
        if isinstance(checkbox, QCheckBox):
            row = checkbox.property("row")
            if row is not None:
                self.row_selection_changed.emit(row, bool(state))

    # ------------------------------------------------------------------
    # Sinais personalizados (usando property para evitar import circular)
    # ------------------------------------------------------------------
    from PySide6.QtCore import Signal
    files_dropped = Signal(list)
    row_selection_changed = Signal(int, bool)


# ----------------------------------------------------------------------
# Dados de exemplo (Mock) para validação visual
# ----------------------------------------------------------------------
MOCK_TRACKS = [
    {
        "name": "Midnight Drive.mp3",
        "path": "/Music/Electronic/Midnight Drive.mp3",
        "duration": "3:42",
        "format": "mp3",
        "lufs": -16.2,
        "true_peak": -1.8,
        "bitrate": "320 kbps",
        "status": "Analisado",
        "status_key": "analyzed",
    },
    {
        "name": "Neon Dreams.flac",
        "path": "/Music/Synthwave/Neon Dreams.flac",
        "duration": "4:18",
        "format": "flac",
        "lufs": -11.5,
        "true_peak": -0.3,
        "bitrate": "1411 kbps",
        "status": "Alerta Peak",
        "status_key": "peak_warn",
    },
    {
        "name": "Analog Heartbeat.wav",
        "path": "/Music/Ambient/Analog Heartbeat.wav",
        "duration": "5:03",
        "format": "wav",
        "lufs": -19.8,
        "true_peak": -2.4,
        "bitrate": "2116 kbps",
        "status": "Concluído",
        "status_key": "completed",
    },
    {
        "name": "Digital Rain.m4a",
        "path": "/Music/Chill/Digital Rain.m4a",
        "duration": "2:56",
        "format": "m4a",
        "lufs": -13.7,
        "true_peak": -0.8,
        "bitrate": "256 kbps",
        "status": "Pendente",
        "status_key": "pending",
    },
]