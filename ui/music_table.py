"""Tabela personalizada de músicas com Drag & Drop e numeração tabular."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QMimeData, QModelIndex, QRect, QSize
from PySide6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontDatabase,
    QColor,
    QBrush,
    QPainter,
    QPixmap,
    QIcon,
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
    QVBoxLayout,
    QSizePolicy,
)

if TYPE_CHECKING:
    from .main_window import MainWindow

from .constants import UIStrings, SUPPORTED_AUDIO_EXTS, FORMAT_DISPLAY_NAME


class TabularNumericDelegate(QStyledItemDelegate):
    """Delegate que força alinhamento à direita e numeração tabular para colunas numéricas."""

    NUMERIC_COLUMNS = {2, 4, 5, 6}  # Duração, LUFS, Pico Real, Taxa de Bits (índices 0-based)

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
        elif index.column() == 5:  # Pico Real
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


class EmptyStateWidget(QWidget):
    """Widget de estado vazio exibido quando a tabela não tem linhas."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("emptyStateWidget")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # Ícone (SVG inline como QLabel com pixmap)
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # SVG simples de música/arquivo
        icon_svg = """
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 3L2 7V17L12 21L22 17V7L12 3Z" stroke="#52525B" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M12 3V21" stroke="#52525B" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M5 12H19" stroke="#52525B" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        """
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtCore import QByteArray
        renderer = QSvgRenderer(QByteArray(icon_svg.encode('utf-8')))
        renderer.render(painter)
        painter.end()
        icon_label.setPixmap(pixmap)
        layout.addWidget(icon_label)

        # Título
        title = QLabel(UIStrings.EMPTY_STATE_TITLE)
        title.setProperty("heading", True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Mensagem
        message = QLabel(UIStrings.EMPTY_STATE_MESSAGE)
        message.setProperty("muted", True)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)
        layout.addWidget(message)


class MusicTableWidget(QTableWidget):
    """Tabela de músicas com Drag & Drop, numeração tabular e badges de status."""

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
        self._empty_state_widget = EmptyStateWidget(self)
        self._empty_state_widget.hide()
        self._setup_table()
        self._setup_drag_drop()
        self._setup_delegate()
        self._update_empty_state_visibility()

    def _setup_table(self) -> None:
        # Configuração básica
        self.setColumnCount(8)
        self.setHorizontalHeaderLabels(UIStrings.TABLE_HEADERS)

        # Header customizado com checkbox na coluna 0
        self._custom_header = CheckBoxHeader(Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(self._custom_header)

        # Tooltips nos cabeçalhos
        for col, tooltip in UIStrings.TABLE_HEADER_TOOLTIPS.items():
            self.horizontalHeader().setToolTip(tooltip)

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
        header.setMinimumSectionSize(0)
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

        # Conecta sinal de redimensionamento para persistir estado
        header.sectionResized.connect(self._on_header_resized)

    def _on_header_resized(self, logical_index: int, old_size: int, new_size: int) -> None:
        # O estado será salvo via QSettings no MainWindow
        pass

    def _setup_drag_drop(self) -> None:
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def _setup_delegate(self) -> None:
        self.setItemDelegate(TabularNumericDelegate(self))

    def _update_empty_state_visibility(self) -> None:
        """Mostra/oculta o widget de estado vazio baseado no número de linhas."""
        is_empty = self.rowCount() == 0
        self._empty_state_widget.setVisible(is_empty)
        if is_empty:
            self._empty_state_widget.resize(self.viewport().size())
            self._empty_state_widget.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._empty_state_widget.resize(self.viewport().size())

    # ------------------------------------------------------------------
    # Drag & Drop
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            valid = any(
                url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in SUPPORTED_AUDIO_EXTS
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
                if path.suffix.lower() in SUPPORTED_AUDIO_EXTS:
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
        self._update_empty_state_visibility()

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

        # Coluna 5: Pico Real (dBTP)
        tp_item = QTableWidgetItem(f"{track_data.get('true_peak', 0):.1f}")
        tp_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tp_item.setData(Qt.ItemDataRole.UserRole, track_data.get("true_peak", 0))
        self.setItem(row, self.COL_TRUE_PEAK, tp_item)

        # Coluna 6: Taxa de Bits
        br_item = QTableWidgetItem(track_data.get("bitrate", "—"))
        br_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, self.COL_BITRATE, br_item)

        # Coluna 7: Status Badge
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(8, 4, 8, 4)
        status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_key = track_data.get("status_key", "pending")
        status_text = track_data.get("status", UIStrings.STATUS_TEXT.get(status_key, "Pendente"))
        badge = QLabel(status_text)
        badge.setProperty("badge", True)
        badge.setProperty("status", status_key)
        badge.setToolTip(UIStrings.STATUS_TOOLTIPS.get(status_key, ""))
        status_layout.addWidget(badge)
        self.setCellWidget(row, self.COL_STATUS, status_widget)

        return row

    def remove_selected_rows(self) -> int:
        """Remove todas as linhas selecionadas. Retorna a quantidade removida."""
        selected_rows = self.get_selected_rows()
        # Remove de trás para frente para não alterar índices
        for row in sorted(selected_rows, reverse=True):
            self.removeRow(row)
        self._update_empty_state_visibility()
        self._custom_header._checked = False
        self._custom_header.updateSection(0)
        return len(selected_rows)

    def set_all_rows_checked(self, checked: bool) -> None:
        for row in range(self.rowCount()):
            widget = self.cellWidget(row, self.COL_CHECK)
            if widget:
                checkbox = widget.findChild(QCheckBox)
                if checkbox:
                    checkbox.blockSignals(True)
                    checkbox.setChecked(checked)
                    checkbox.blockSignals(False)
        self._custom_header._checked = checked

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
                display_text = status_text or UIStrings.STATUS_TEXT.get(status_key, status_key.replace("_", " ").title())
                badge.setText(display_text)
                badge.setToolTip(UIStrings.STATUS_TOOLTIPS.get(status_key, ""))
                badge.style().unpolish(badge)
                badge.style().polish(badge)

    def _on_checkbox_changed(self, state: int) -> None:
        checkbox = self.sender()
        if isinstance(checkbox, QCheckBox):
            row = checkbox.property("row")
            if row is not None:
                self.row_selection_changed.emit(row, bool(state))

    # ------------------------------------------------------------------
    # Sinais personalizados
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
        "format": "MP3",
        "lufs": -16.2,
        "true_peak": -1.8,
        "bitrate": "320 kbps",
        "status": UIStrings.STATUS_TEXT["analyzed"],
        "status_key": "analyzed",
    },
    {
        "name": "Neon Dreams.flac",
        "path": "/Music/Synthwave/Neon Dreams.flac",
        "duration": "4:18",
        "format": "FLAC",
        "lufs": -11.5,
        "true_peak": -0.3,
        "bitrate": "1411 kbps",
        "status": UIStrings.STATUS_TEXT["peak_warn"],
        "status_key": "peak_warn",
    },
    {
        "name": "Analog Heartbeat.wav",
        "path": "/Music/Ambient/Analog Heartbeat.wav",
        "duration": "5:03",
        "format": "WAV",
        "lufs": -19.8,
        "true_peak": -2.4,
        "bitrate": "2116 kbps",
        "status": UIStrings.STATUS_TEXT["completed"],
        "status_key": "completed",
    },
    {
        "name": "Digital Rain.m4a",
        "path": "/Music/Chill/Digital Rain.m4a",
        "duration": "2:56",
        "format": "M4A",
        "lufs": -13.7,
        "true_peak": -0.8,
        "bitrate": "256 kbps",
        "status": UIStrings.STATUS_TEXT["pending"],
        "status_key": "pending",
    },
]