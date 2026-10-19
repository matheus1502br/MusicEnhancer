"""Janela Principal do MusicEnhancer — Layout responsivo com Splitter."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, Slot, QSettings, QStandardPaths
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QToolBar,
    QFileDialog,
    QMessageBox,
    QStatusBar,
    QProgressBar,
    QLabel,
    QPushButton,
    QLineEdit,
    QSizePolicy,
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QComboBox,
    QVBoxLayout as QVBoxLayoutWidget,
)

if __package__ is None or __package__ == "":
    import sys
    from pathlib import Path
    _proj_root = str(Path(__file__).resolve().parents[1])
    if _proj_root not in sys.path:
        sys.path.insert(0, _proj_root)
    from ui.music_table import MusicTableWidget, MOCK_TRACKS
    from ui.inspector_panel import InspectorPanel
    from ui.styles import get_stylesheet
    from ui.workers import WorkerManager, AnalysisWorker, BatchWorker, FolderScanWorker
    from ui.constants import UIStrings, SettingsKeys, Shortcuts, Defaults, SUPPORTED_AUDIO_EXTS
else:
    from .music_table import MusicTableWidget, MOCK_TRACKS
    from .inspector_panel import InspectorPanel
    from .styles import get_stylesheet
    from .workers import WorkerManager, AnalysisWorker, BatchWorker, FolderScanWorker
    from .constants import UIStrings, SettingsKeys, Shortcuts, Defaults, SUPPORTED_AUDIO_EXTS

if TYPE_CHECKING:
    from ui.workers import NormalizationResult


class OverwriteDialog(QDialog):
    """Diálogo de confirmação para arquivos já existentes na pasta de destino."""

    def __init__(self, count: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(UIStrings.DLG_CONFIRM_OVERWRITE_TITLE)
        self.setModal(True)
        self.setMinimumWidth(480)
        self._choice = UIStrings.DLG_OVERWRITE_REPLACE_ALL
        self._apply_all = False
        self._setup_ui(count)

    def _setup_ui(self, count: int) -> None:
        layout = QVBoxLayoutWidget(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Mensagem
        msg = QLabel(UIStrings.DLG_CONFIRM_OVERWRITE_MSG.format(count=count))
        msg.setWordWrap(True)
        msg.setProperty("heading", True)
        layout.addWidget(msg)

        # Opções de rádio (usando checkboxes estilo rádio)
        self.rb_replace = QCheckBox(UIStrings.DLG_OVERWRITE_REPLACE_ALL)
        self.rb_skip = QCheckBox(UIStrings.DLG_OVERWRITE_SKIP)
        self.rb_rename = QCheckBox(UIStrings.DLG_OVERWRITE_RENAME)

        self.rb_replace.setChecked(True)
        self.rb_replace.toggled.connect(lambda c: self._on_option_toggled(c, "replace"))
        self.rb_skip.toggled.connect(lambda c: self._on_option_toggled(c, "skip"))
        self.rb_rename.toggled.connect(lambda c: self._on_option_toggled(c, "rename"))

        layout.addWidget(self.rb_replace)
        layout.addWidget(self.rb_skip)
        layout.addWidget(self.rb_rename)

        # Checkbox "Aplicar a todos"
        self.chk_apply_all = QCheckBox(UIStrings.DLG_OVERWRITE_APPLY_ALL)
        self.chk_apply_all.setToolTip("Lembrar esta escolha para os próximos arquivos deste lote")
        layout.addWidget(self.chk_apply_all)

        # Botões
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_option_toggled(self, checked: bool, choice: str) -> None:
        if checked:
            self._choice = choice
            # Desmarca os outros
            for rb in (self.rb_replace, self.rb_skip, self.rb_rename):
                if rb.text() != self._get_text_for_choice(choice):
                    rb.blockSignals(True)
                    rb.setChecked(False)
                    rb.blockSignals(False)

    def _get_text_for_choice(self, choice: str) -> str:
        return {
            "replace": UIStrings.DLG_OVERWRITE_REPLACE_ALL,
            "skip": UIStrings.DLG_OVERWRITE_SKIP,
            "rename": UIStrings.DLG_OVERWRITE_RENAME,
        }[choice]

    @property
    def choice(self) -> str:
        return self._choice

    @property
    def apply_all(self) -> bool:
        return self.chk_apply_all.isChecked()


class MainWindow(QMainWindow):
    """Janela principal da aplicação."""

    # Sinais para futura integração com backend
    batch_start_requested = Signal(dict)      # configurações do lote
    batch_cancel_requested = Signal()
    files_add_requested = Signal(list)        # lista de caminhos
    folder_add_requested = Signal(str)        # caminho da pasta
    output_folder_changed = Signal(str)

    def __init__(self, config: dict | None = None):
        super().__init__()
        self.setWindowTitle(UIStrings.WINDOW_TITLE)
        self.resize(Defaults.WINDOW_DEFAULT_WIDTH, Defaults.WINDOW_DEFAULT_HEIGHT)
        self.setMinimumSize(Defaults.WINDOW_MIN_WIDTH, Defaults.WINDOW_MIN_HEIGHT)

        self._output_folder = ""
        self._analysis_worker: AnalysisWorker | None = None
        self._batch_worker: BatchWorker | None = None
        self._folder_scan_worker: FolderScanWorker | None = None

        # Configurações do núcleo
        from core.settings import load_config
        self._config = config if config is not None else load_config()

        # QSettings
        self._settings = QSettings("MusicEnhancer", "MusicEnhancer")

        # Estado do diálogo de sobrescrita
        self._overwrite_choice = None
        self._overwrite_apply_all = False

        self._setup_ui()
        self._setup_shortcuts()
        self._restore_settings()
        self._connect_signals()
        self._load_mock_data()
        self._apply_styles()

    def _setup_shortcuts(self) -> None:
        """Configura atalhos de teclado globais."""
        # Ctrl+O: Adicionar Arquivos
        shortcut_add_files = QShortcut(Shortcuts.ADD_FILES, self)
        shortcut_add_files.activated.connect(self._on_add_files)

        # Ctrl+Shift+O: Adicionar Pasta
        shortcut_add_folder = QShortcut(Shortcuts.ADD_FOLDER, self)
        shortcut_add_folder.activated.connect(self._on_add_folder)

        # Delete / Backspace: Remover seleção
        shortcut_remove = QShortcut(Shortcuts.REMOVE_SELECTED, self)
        shortcut_remove.activated.connect(self._remove_selected_tracks)
        shortcut_remove_alt = QShortcut(Shortcuts.REMOVE_SELECTED_ALT, self)
        shortcut_remove_alt.activated.connect(self._remove_selected_tracks)

        # Ctrl+Enter: Iniciar Lote
        shortcut_start = QShortcut(Shortcuts.START_BATCH, self)
        shortcut_start.activated.connect(self._on_start_batch)
        shortcut_start_alt = QShortcut(Shortcuts.START_BATCH_ALT, self)
        shortcut_start_alt.activated.connect(self._on_start_batch)

        # Esc: Cancelar
        shortcut_cancel = QShortcut(Shortcuts.CANCEL_BATCH, self)
        shortcut_cancel.activated.connect(self._cancel_all_workers)

    def _restore_settings(self) -> None:
        """Restaura configurações salvas."""
        # Geometria da janela
        geometry = self._settings.value(SettingsKeys.WINDOW_GEOMETRY)
        if geometry:
            self.restoreGeometry(geometry)

        state = self._settings.value(SettingsKeys.WINDOW_STATE)
        if state:
            self.restoreState(state)
        if self.isMinimized():
            self.showNormal()

        # Splitter
        splitter_state = self._settings.value(SettingsKeys.SPLITTER_STATE)
        if splitter_state and hasattr(self, 'splitter'):
            self.splitter.restoreState(splitter_state)

        # Header da tabela
        header_state = self._settings.value(SettingsKeys.TABLE_HEADER_STATE)
        if header_state:
            self.music_table.horizontalHeader().restoreState(header_state)

        # Pasta de saída
        default_out = self._config.get("output_folder", "")
        output_folder = self._settings.value(SettingsKeys.OUTPUT_FOLDER, default_out)
        if output_folder and os.path.isdir(output_folder):
            self._output_folder = output_folder
            self.txt_output_folder.setText(output_folder)

        # Preset atual
        default_preset = self._config.get("current_preset", UIStrings.INSPECTOR_PRESETS[0])
        preset = self._settings.value(SettingsKeys.CURRENT_PRESET, default_preset)
        self.toolbar_preset.blockSignals(True)
        idx = self.toolbar_preset.findText(preset)
        if idx >= 0:
            self.toolbar_preset.setCurrentIndex(idx)
        self.toolbar_preset.blockSignals(False)
        self.inspector.set_preset(preset)

        # Painel avançado expandido
        default_advanced = self._config.get("advanced_expanded", False)
        advanced_expanded = self._settings.value(SettingsKeys.ADVANCED_EXPANDED, default_advanced, type=bool)
        self.inspector.advanced_group.setChecked(advanced_expanded)

        # Valores avançados
        default_lufs = self._config.get("target_loudness", Defaults.TARGET_LOUDNESS_STREAMING)
        default_tp = self._config.get("target_true_peak", Defaults.TARGET_TRUE_PEAK_DEFAULT)
        target_loudness = self._settings.value(SettingsKeys.TARGET_LOUDNESS, default_lufs, type=float)
        target_tp = self._settings.value(SettingsKeys.TARGET_TRUE_PEAK, default_tp, type=float)
        self.inspector.target_loudness.setValue(target_loudness)
        self.inspector.target_true_peak.setValue(target_tp)

        # Escolha de sobrescrita
        default_ow = self._config.get("overwrite_choice", "rename")
        default_ow_all = self._config.get("overwrite_apply_all", False)
        self._overwrite_choice = self._settings.value(SettingsKeys.OVERWRITE_CHOICE, default_ow)
        self._overwrite_apply_all = self._settings.value(SettingsKeys.OVERWRITE_APPLY_ALL, default_ow_all, type=bool)

    def _save_settings(self) -> None:
        """Salva configurações atuais."""
        self._settings.setValue(SettingsKeys.WINDOW_GEOMETRY, self.saveGeometry())
        self._settings.setValue(SettingsKeys.WINDOW_STATE, self.saveState())
        if hasattr(self, 'splitter'):
            self._settings.setValue(SettingsKeys.SPLITTER_STATE, self.splitter.saveState())
        self._settings.setValue(SettingsKeys.TABLE_HEADER_STATE, self.music_table.horizontalHeader().saveState())
        if self._output_folder:
            self._settings.setValue(SettingsKeys.OUTPUT_FOLDER, self._output_folder)
        self._settings.setValue(SettingsKeys.CURRENT_PRESET, self.toolbar_preset.currentText())
        self._settings.setValue(SettingsKeys.ADVANCED_EXPANDED, self.inspector.advanced_group.isChecked())
        self._settings.setValue(SettingsKeys.TARGET_LOUDNESS, self.inspector.target_loudness.value())
        self._settings.setValue(SettingsKeys.TARGET_TRUE_PEAK, self.inspector.target_true_peak.value())
        if self._overwrite_choice:
            self._settings.setValue(SettingsKeys.OVERWRITE_CHOICE, self._overwrite_choice)
        self._settings.setValue(SettingsKeys.OVERWRITE_APPLY_ALL, self._overwrite_apply_all)

        # Persiste também no arquivo de configuração do core
        from core.settings import save_config
        self._config["output_folder"] = self._output_folder
        self._config["current_preset"] = self.toolbar_preset.currentText()
        self._config["advanced_expanded"] = self.inspector.advanced_group.isChecked()
        self._config["target_loudness"] = self.inspector.target_loudness.value()
        self._config["target_true_peak"] = self.inspector.target_true_peak.value()
        self._config["overwrite_choice"] = self._overwrite_choice
        self._config["overwrite_apply_all"] = self._overwrite_apply_all
        save_config(self._config)

    def closeEvent(self, event) -> None:
        self._save_settings()
        super().closeEvent(event)

    def _connect_signals(self) -> None:
        """Conecta sinais da UI aos workers."""
        self.files_add_requested.connect(self._start_analysis)
        self.folder_add_requested.connect(self._start_folder_scan)
        self.batch_start_requested.connect(self._start_batch_processing)
        self.batch_cancel_requested.connect(self._cancel_all_workers)

        # Sinais da toolbar
        self.toolbar_preset.currentTextChanged.connect(self._on_toolbar_preset_changed)

    def _setup_ui(self) -> None:
        # Widget central
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # ===============================================================
        # TOOLBAR SUPERIOR
        # ===============================================================
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(toolbar.iconSize())
        toolbar.setStyleSheet("QToolBar { border: none; background: transparent; spacing: 8px; padding: 4px; }")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        # Botão Adicionar Arquivos
        self.btn_add_files = QPushButton(UIStrings.BTN_ADD_FILES)
        self.btn_add_files.setProperty("flat", True)
        self.btn_add_files.setToolTip(UIStrings.TOOLTIP_ADD_FILES)
        self.btn_add_files.clicked.connect(self._on_add_files)
        toolbar.addWidget(self.btn_add_files)

        # Botão Adicionar Pasta
        self.btn_add_folder = QPushButton(UIStrings.BTN_ADD_FOLDER)
        self.btn_add_folder.setProperty("flat", True)
        self.btn_add_folder.setToolTip(UIStrings.TOOLTIP_ADD_FOLDER)
        self.btn_add_folder.clicked.connect(self._on_add_folder)
        toolbar.addWidget(self.btn_add_folder)

        toolbar.addSeparator()

        # Preset Selector (replicado do inspector para acesso rápido)
        preset_lbl = QLabel(UIStrings.LBL_PRESET)
        preset_lbl.setProperty("subheading", True)
        toolbar.addWidget(preset_lbl)

        self.toolbar_preset = QComboBox()
        self.toolbar_preset.addItems(UIStrings.INSPECTOR_PRESETS)
        self.toolbar_preset.setCurrentIndex(0)
        self.toolbar_preset.setFixedWidth(280)
        self.toolbar_preset.setToolTip(UIStrings.TOOLTIP_PRESET)
        toolbar.addWidget(self.toolbar_preset)

        toolbar.addSeparator()

        # Contador de seleção
        self.lbl_selection_count = QLabel(UIStrings.LBL_SELECTION_COUNT.format(selected=0, total=0))
        self.lbl_selection_count.setProperty("muted", True)
        toolbar.addWidget(self.lbl_selection_count)

        # Spacer flexível
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # ===============================================================
        # SPLITTER CENTRAL (Tabela | Inspector)
        # ===============================================================
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
        main_layout.addWidget(self.splitter, 1)

        # --- Tabela de Músicas (Topo) ---
        self.music_table = MusicTableWidget()
        self.music_table.setMinimumHeight(Defaults.TABLE_MIN_HEIGHT)
        self.music_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.music_table.files_dropped.connect(self.files_add_requested.emit)
        self.music_table.row_selection_changed.connect(self._on_row_selection_changed)
        self.splitter.addWidget(self.music_table)

        # --- Painel Inspetor (Base) ---
        self.inspector = InspectorPanel()
        self.inspector.setMaximumHeight(Defaults.INSPECTOR_MAX_HEIGHT)
        self.inspector.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.inspector.preset_changed.connect(self._on_preset_changed)
        self.inspector.target_loudness_changed.connect(lambda v: None)  # placeholder
        self.inspector.target_true_peak_changed.connect(lambda v: None)  # placeholder
        self.splitter.addWidget(self.inspector)

        # Proporção inicial: tabela 3x maior que inspetor (75/25)
        self.splitter.setSizes(Defaults.SPLITTER_SIZES)
        self.splitter.setStretchFactor(0, Defaults.SPLITTER_STRETCH_TABLE)
        self.splitter.setStretchFactor(1, Defaults.SPLITTER_STRETCH_INSPECTOR)

        # ===============================================================
        # RODAPÉ (Footer) — Duas linhas para melhor hierarquia
        # ===============================================================
        footer = QWidget()
        footer.setObjectName("footer")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(10)

        # --- Linha 1: Pasta de Saída ---
        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(12)

        out_lbl = QLabel(UIStrings.FOOTER_OUTPUT_LABEL)
        out_lbl.setProperty("subheading", True)
        out_lbl.setMinimumWidth(50)
        output_layout.addWidget(out_lbl)

        self.txt_output_folder = QLineEdit()
        self.txt_output_folder.setReadOnly(True)
        self.txt_output_folder.setPlaceholderText(UIStrings.FOOTER_OUTPUT_PLACEHOLDER)
        self.txt_output_folder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        output_layout.addWidget(self.txt_output_folder, 1)

        self.btn_browse_output = QPushButton(UIStrings.FOOTER_BROWSE_BTN)
        self.btn_browse_output.clicked.connect(self._on_browse_output)
        output_layout.addWidget(self.btn_browse_output)

        footer_layout.addWidget(output_row)

        # --- Linha 2: Progresso + Ações ---
        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(16)

        prog_lbl = QLabel(UIStrings.FOOTER_PROGRESS_LABEL)
        prog_lbl.setProperty("subheading", True)
        prog_lbl.setMinimumWidth(65)
        action_layout.addWidget(prog_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat(UIStrings.FOOTER_PROGRESS_FORMAT.format(current=0, total=0))
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.progress_bar.setMinimumWidth(300)
        action_layout.addWidget(self.progress_bar, 1)

        # Botão Cancelar
        self.btn_cancel = QPushButton(UIStrings.FOOTER_CANCEL_BTN)
        self.btn_cancel.setProperty("danger", True)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setMinimumWidth(140)
        self.btn_cancel.setMinimumHeight(36)
        self.btn_cancel.clicked.connect(self.batch_cancel_requested.emit)
        action_layout.addWidget(self.btn_cancel)

        # Botão Principal — INICIAR LOTE
        self.btn_start_batch = QPushButton(UIStrings.FOOTER_START_BATCH_BTN)
        self.btn_start_batch.setProperty("primary", True)
        self.btn_start_batch.setMinimumWidth(180)
        self.btn_start_batch.setMinimumHeight(38)
        self.btn_start_batch.setToolTip(UIStrings.FOOTER_START_BATCH_TOOLTIP)
        self.btn_start_batch.clicked.connect(self._on_start_batch)
        action_layout.addWidget(self.btn_start_batch)

        footer_layout.addWidget(action_row)
        main_layout.addWidget(footer)

        # Status bar nativa do Qt
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("""
            QStatusBar { background: #18181B; color: #A1A1AA; border-top: 1px solid #3F3F46; }
            QStatusBar::item { border: none; }
        """)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(UIStrings.STATUSBAR_READY)

    def _apply_styles(self) -> None:
        self.setStyleSheet(get_stylesheet())

    def _load_mock_data(self) -> None:
        """Carrega dados de exemplo para validação visual se MUSIC_ENHANCER_MOCK=1."""
        if os.environ.get("MUSIC_ENHANCER_MOCK") == "1":
            for track in MOCK_TRACKS:
                self.music_table.add_track(track)
            self._update_selection_count()

    # ------------------------------------------------------------------
    # Slots / Handlers
    # ------------------------------------------------------------------
    def _on_add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            UIStrings.DLG_ADD_FILES_TITLE,
            self._output_folder or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation),
            UIStrings.DLG_ADD_FILES_FILTER,
        )
        if files:
            self.files_add_requested.emit(files)

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            UIStrings.DLG_ADD_FOLDER_TITLE,
            self._output_folder or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation),
        )
        if folder:
            self.folder_add_requested.emit(folder)

    def _remove_selected_tracks(self) -> None:
        """Remove as faixas selecionadas da tabela (atalho Delete/Backspace)."""
        removed = self.music_table.remove_selected_rows()
        if removed:
            self._update_selection_count()
            self.status_bar.showMessage(f"{removed} faixa(s) removida(s).", 3000)

    def _start_folder_scan(self, folder_path: str) -> None:
        """Inicia escaneamento assíncrono de pasta."""
        self.status_bar.showMessage(UIStrings.MSG_SCANNING.format(path=folder_path))
        self._folder_scan_worker = WorkerManager.scan_folder(folder_path)
        self._folder_scan_worker.signals.files_found.connect(self._on_folder_files_found)
        self._folder_scan_worker.signals.error.connect(self._on_folder_scan_error)
        self._folder_scan_worker.signals.finished.connect(lambda: self.status_bar.showMessage(UIStrings.MSG_SCAN_DONE, 3000))

    def _on_folder_files_found(self, files: list[str]) -> None:
        """Callback quando arquivos são encontrados no escaneamento de pasta."""
        if files:
            self.files_add_requested.emit(files)
        else:
            self.status_bar.showMessage(UIStrings.MSG_SCAN_NO_FILES, 5000)

    def _on_folder_scan_error(self, error: str) -> None:
        self.status_bar.showMessage(f"Erro ao escanear pasta: {error}", 5000)

    def _start_analysis(self, file_paths: list[str]) -> None:
        """Inicia análise assíncrona dos arquivos adicionados."""
        if not file_paths:
            return

        # Adiciona placeholders na tabela primeiro
        start_row = self.music_table.rowCount()
        for file_path in file_paths:
            self.music_table.add_track({
                "name": Path(file_path).name,
                "path": file_path,
                "duration": "—",
                "format": Path(file_path).suffix.lstrip(".").upper(),
                "lufs": 0.0,
                "true_peak": 0.0,
                "bitrate": "—",
                "status": "Analisando…",
                "status_key": "pending",
            })

        self.status_bar.showMessage(UIStrings.MSG_ANALYZING.format(count=len(file_paths)))
        self._analysis_worker = WorkerManager.start_analysis(file_paths, start_row)
        self._analysis_worker.signals.track_analyzed.connect(self._on_track_analyzed)
        self._analysis_worker.signals.track_failed.connect(self._on_track_analysis_failed)
        self._analysis_worker.signals.finished.connect(self._on_analysis_finished)
        self._analysis_worker.signals.cancelled.connect(lambda: self.status_bar.showMessage(UIStrings.MSG_ANALYSIS_CANCELLED, 3000))

    @Slot(int, dict)
    def _on_track_analyzed(self, row: int, track_data: dict) -> None:
        """Atualiza a tabela com os dados analisados."""
        self.music_table.setRowHeight(row, Defaults.TABLE_ROW_HEIGHT)
        # Atualiza células existentes
        self.music_table.setItem(row, self.music_table.COL_DURATION, self._create_table_item(track_data["duration"], align_right=True))
        self.music_table.setItem(row, self.music_table.COL_FORMAT, self._create_table_item(track_data["format"], align_center=True))
        self.music_table.setItem(row, self.music_table.COL_LUFS, self._create_table_item(f"{track_data['lufs']:.1f}", align_right=True, user_data=track_data["lufs"]))
        self.music_table.setItem(row, self.music_table.COL_TRUE_PEAK, self._create_table_item(f"{track_data['true_peak']:.1f}", align_right=True, user_data=track_data["true_peak"]))
        self.music_table.setItem(row, self.music_table.COL_BITRATE, self._create_table_item(track_data["bitrate"], align_right=True))
        # Atualiza status badge
        self.music_table.update_row_status(row, track_data["status_key"], track_data["status"])

        # Se for a linha selecionada, atualiza inspector
        if row == self.music_table.currentRow():
            self.inspector.set_track_data(track_data)

    def _on_track_analysis_failed(self, row: int, error: str) -> None:
        self.music_table.update_row_status(row, "error", f"Erro: {error[:40]}")
        self.status_bar.showMessage(f"Erro ao analisar: {error}", 5000)

    def _on_analysis_finished(self) -> None:
        self.status_bar.showMessage(UIStrings.MSG_ANALYSIS_DONE, 3000)
        self._analysis_worker = None

    def _check_disk_space(self, output_folder: str, selected_rows: list[int]) -> tuple[bool, int, int]:
        """Verifica espaço em disco. Retorna (ok, free_mb, needed_mb)."""
        try:
            total_size = 0
            for row in selected_rows:
                track_data = self.music_table.get_track_data(row)
                if track_data and track_data.get("path"):
                    source_path = Path(track_data["path"])
                    if source_path.exists():
                        total_size += source_path.stat().st_size

            # Estima 1.5x para saída (FLAC/WAV podem crescer, MP3 comprime)
            estimated_needed = int(total_size * 1.5 / (1024 * 1024))  # MB

            stat = shutil.disk_usage(output_folder)
            free_mb = stat.free // (1024 * 1024)

            return free_mb >= estimated_needed, free_mb, estimated_needed
        except Exception:
            return True, 0, 0  # Em caso de erro, permite prosseguir

    def _on_start_batch(self) -> None:
        selected_rows = self.music_table.get_selected_rows()
        if not selected_rows:
            QMessageBox.information(
                self,
                UIStrings.DLG_NO_SELECTION_TITLE,
                UIStrings.DLG_NO_SELECTION_MSG,
            )
            return

        if not self._output_folder:
            QMessageBox.warning(
                self,
                UIStrings.DLG_NO_OUTPUT_FOLDER_TITLE,
                UIStrings.DLG_NO_OUTPUT_FOLDER_MSG,
            )
            return

        # Verifica permissão de escrita
        if not os.access(self._output_folder, os.W_OK):
            QMessageBox.critical(
                self,
                UIStrings.DLG_WRITE_PERMISSION_TITLE,
                UIStrings.DLG_WRITE_PERMISSION_MSG.format(path=self._output_folder),
            )
            return

        # Verifica espaço em disco
        space_ok, free_mb, needed_mb = self._check_disk_space(self._output_folder, selected_rows)
        if not space_ok:
            QMessageBox.critical(
                self,
                UIStrings.DLG_DISK_SPACE_TITLE,
                UIStrings.DLG_DISK_SPACE_MSG.format(free=free_mb, needed=needed_mb),
            )
            return

        # Verifica conflitos de arquivos existentes
        conflicts = []
        for row in selected_rows:
            track_data = self.music_table.get_track_data(row)
            if track_data and track_data.get("path"):
                source_path = Path(track_data["path"])
                dest_path = Path(self._output_folder) / source_path.name
                if dest_path.exists():
                    conflicts.append((row, source_path.name, dest_path))

        if conflicts and not (self._overwrite_apply_all and self._overwrite_choice):
            dialog = OverwriteDialog(len(conflicts), self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self._overwrite_choice = dialog.choice
                self._overwrite_apply_all = dialog.apply_all
            else:
                return  # Usuário cancelou

        # Passa a escolha de sobrescrita para as configurações
        settings = self.inspector.get_current_settings()
        settings["selected_rows"] = selected_rows
        settings["output_folder"] = self._output_folder
        settings["overwrite_choice"] = self._overwrite_choice
        settings["overwrite_apply_all"] = self._overwrite_apply_all

        self.batch_start_requested.emit(settings)
        self._set_batch_running(True)

    def _on_toolbar_preset_changed(self, preset_name: str) -> None:
        """Sincroniza toolbar preset com inspector."""
        self.inspector.set_preset(preset_name)

    def _on_browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Saída", self._output_folder)
        if folder:
            self._output_folder = folder
            self.txt_output_folder.setText(folder)
            self.output_folder_changed.emit(folder)

    def _on_row_selection_changed(self, row: int, checked: bool) -> None:
        self._update_selection_count()
        if checked:
            track_data = self.music_table.get_track_data(row)
            if track_data:
                self.inspector.set_track_data(track_data)
        else:
            # Se nenhuma outra estiver selecionada, limpa
            if not self.music_table.get_selected_rows():
                self.inspector.clear_selection()

    def _on_preset_changed(self, preset_name: str) -> None:
        # Sincroniza toolbar com inspector
        self.toolbar_preset.blockSignals(True)
        self.toolbar_preset.setCurrentText(preset_name)
        self.toolbar_preset.blockSignals(False)

    def _update_selection_count(self) -> None:
        total = self.music_table.rowCount()
        selected = len(self.music_table.get_selected_rows())
        self.lbl_selection_count.setText(UIStrings.LBL_SELECTION_COUNT.format(selected=selected, total=total))

    def _set_batch_running(self, running: bool) -> None:
        self.btn_start_batch.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        self.btn_add_files.setEnabled(not running)
        self.btn_add_folder.setEnabled(not running)
        self.music_table.setEnabled(not running)
        self.toolbar_preset.setEnabled(not running)
        self.inspector.setEnabled(not running)
        if running:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat(UIStrings.FOOTER_PROGRESS_FORMAT.format(current=0, total=0))
            self.status_bar.showMessage(UIStrings.MSG_BATCH_STARTED)
        else:
            self.status_bar.showMessage(UIStrings.MSG_READY)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _create_table_item(self, text: str, align_right: bool = False, align_center: bool = False, user_data=None):
        from PySide6.QtWidgets import QTableWidgetItem
        from PySide6.QtCore import Qt
        item = QTableWidgetItem(str(text))
        if align_right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        elif align_center:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        if user_data is not None:
            item.setData(Qt.ItemDataRole.UserRole, user_data)
        return item

    # ------------------------------------------------------------------
    # API Pública para integração futura
    # ------------------------------------------------------------------
    def add_tracks(self, tracks: list[dict]) -> None:
        """Adiciona múltiplas faixas à tabela (chamado pelo backend)."""
        for track in tracks:
            self.music_table.add_track(track)
        self._update_selection_count()

    def update_track_progress(self, row: int, progress: int, status_key: str, status_text: str) -> None:
        """Atualiza progresso e status de uma faixa específica."""
        self.music_table.update_row_status(row, status_key, status_text)
        if row == self.music_table.currentRow():
            # Atualiza inspector se for a faixa selecionada
            track_data = self.music_table.get_track_data(row)
            if track_data:
                self.inspector.set_track_data(track_data)

    def set_overall_progress(self, current: int, total: int) -> None:
        """Atualiza progresso geral com formato legível."""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(UIStrings.FOOTER_PROGRESS_FORMAT.format(current=current, total=total))

    def batch_finished(self, success: bool, message: str = "") -> None:
        self._set_batch_running(False)
        if success:
            self.status_bar.showMessage(message or UIStrings.MSG_BATCH_DONE.format(success=1, total=1), 5000)
        else:
            self.status_bar.showMessage(message or UIStrings.MSG_BATCH_DONE_ERRORS.format(success=0, total=1, errors=""), 5000)
            QMessageBox.critical(self, "Erro no Lote", message or "Ocorreu um erro durante o processamento.")

    def _start_batch_processing(self, settings: dict) -> None:
        """Inicia processamento em lote assíncrono."""
        selected_rows = settings.pop("selected_rows", [])
        if not selected_rows:
            return

        tracks_to_process = []
        for row in selected_rows:
            track_data = self.music_table.get_track_data(row)
            if track_data and track_data.get("path"):
                track_data["row"] = row
                tracks_to_process.append(track_data)

        if not tracks_to_process:
            return

        self._batch_worker = WorkerManager.start_batch(tracks_to_process, settings)
        self._batch_worker.signals.track_started.connect(lambda row: self.music_table.update_row_status(row, "pending", "Processando…"))
        self._batch_worker.signals.track_finished.connect(self._on_track_batch_finished)
        self._batch_worker.signals.track_failed.connect(self._on_track_batch_failed)
        self._batch_worker.signals.overall_progress.connect(self.set_overall_progress)
        self._batch_worker.signals.finished.connect(self._on_batch_finished)
        self._batch_worker.signals.cancelled.connect(lambda: self.status_bar.showMessage(UIStrings.MSG_BATCH_CANCELLED, 3000))

    def _on_batch_finished(self, success: bool, message: str) -> None:
        """Callback quando o lote termina."""
        self.batch_finished(success, message)

    def _on_track_batch_finished(self, row: int, result: "NormalizationResult") -> None:
        if result.status == "bypass":
            status_key = "bypass"
            status_text = UIStrings.STATUS_TEXT.get("bypass", "Copiado (Bypass)")
        elif result.status == "skipped":
            status_key = "pending"
            status_text = "Ignorado"
        else:
            status_key = "completed"
            status_text = UIStrings.STATUS_TEXT.get("completed", "Concluído")
        self.music_table.update_row_status(row, status_key, status_text)

    def _on_track_batch_failed(self, row: int, error: str) -> None:
        self.music_table.update_row_status(row, "error", f"Erro: {error[:30]}")

    def _cancel_all_workers(self) -> None:
        if self._analysis_worker:
            self._analysis_worker.cancel()
        if self._batch_worker:
            self._batch_worker.cancel()
        if self._folder_scan_worker:
            self._folder_scan_worker.cancel()
        WorkerManager.cancel_all()
        self.batch_finished(False, UIStrings.MSG_BATCH_CANCELLED)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    root_dir = str(Path(__file__).resolve().parents[1])
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

    from main import main
    sys.exit(main())