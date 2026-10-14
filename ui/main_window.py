"""Janela Principal do MusicEnhancer — Layout responsivo com Splitter."""

from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, Signal, Slot
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
)

from .music_table import MusicTableWidget, MOCK_TRACKS
from .inspector_panel import InspectorPanel
from .styles import get_stylesheet
from .workers import WorkerManager, AnalysisWorker, BatchWorker, FolderScanWorker


class MainWindow(QMainWindow):
    """Janela principal da aplicação."""

    # Sinais para futura integração com backend
    batch_start_requested = Signal(dict)      # configurações do lote
    batch_cancel_requested = Signal()
    files_add_requested = Signal(list)        # lista de caminhos
    folder_add_requested = Signal(str)        # caminho da pasta
    output_folder_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MusicEnhancer")
        self.resize(1024, 680)
        self.setMinimumSize(900, 600)

        self._output_folder = ""
        self._analysis_worker: AnalysisWorker | None = None
        self._batch_worker: BatchWorker | None = None
        self._folder_scan_worker: FolderScanWorker | None = None

        self._setup_ui()
        self._connect_signals()
        self._load_mock_data()
        self._apply_styles()

    def _connect_signals(self) -> None:
        """Conecta sinais da UI aos workers."""
        self.files_add_requested.connect(self._start_analysis)
        self.folder_add_requested.connect(self._start_folder_scan)
        self.batch_start_requested.connect(self._start_batch_processing)
        self.batch_cancel_requested.connect(self._cancel_all_workers)

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
        self.btn_add_files = QPushButton("+ Adicionar Arquivos")
        self.btn_add_files.setProperty("flat", True)
        self.btn_add_files.setToolTip("Adicionar arquivos de áudio individuais (Ctrl+O)")
        self.btn_add_files.clicked.connect(self._on_add_files)
        toolbar.addWidget(self.btn_add_files)

        # Botão Adicionar Pasta
        self.btn_add_folder = QPushButton("+ Adicionar Pasta")
        self.btn_add_folder.setProperty("flat", True)
        self.btn_add_folder.setToolTip("Adicionar todos os arquivos de uma pasta recursivamente")
        self.btn_add_folder.clicked.connect(self._on_add_folder)
        toolbar.addWidget(self.btn_add_folder)

        toolbar.addSeparator()

        # Preset Selector (replicado do inspector para acesso rápido)
        preset_lbl = QLabel("Preset:")
        preset_lbl.setProperty("subheading", True)
        toolbar.addWidget(preset_lbl)

        self.toolbar_preset = QComboBox()
        self.toolbar_preset.addItems([
            "Streaming (-14 LUFS, -1.0 dBTP)",
            "Carro / Festa (-11 LUFS, -1.0 dBTP)",
            "Preservado / Arquivo (-18 LUFS, -1.5 dBTP)",
            "Personalizado…",
        ])
        self.toolbar_preset.setCurrentIndex(0)
        self.toolbar_preset.setFixedWidth(280)
        toolbar.addWidget(self.toolbar_preset)

        toolbar.addSeparator()

        # Contador de seleção
        self.lbl_selection_count = QLabel("0 de 0 selecionadas")
        self.lbl_selection_count.setProperty("muted", True)
        toolbar.addWidget(self.lbl_selection_count)

        # Spacer flexível usando QWidgetAction
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # ===============================================================
        # SPLITTER CENTRAL (Tabela | Inspector)
        # ===============================================================
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        main_layout.addWidget(splitter, 1)

        # --- Tabela de Músicas (Topo) ---
        self.music_table = MusicTableWidget()
        self.music_table.files_dropped.connect(self.files_add_requested.emit)
        self.music_table.row_selection_changed.connect(self._on_row_selection_changed)
        splitter.addWidget(self.music_table)

        # --- Painel Inspetor (Base) ---
        self.inspector = InspectorPanel()
        self.inspector.preset_changed.connect(self._on_preset_changed)
        self.inspector.target_loudness_changed.connect(lambda v: None)  # placeholder
        self.inspector.target_true_peak_changed.connect(lambda v: None)  # placeholder
        splitter.addWidget(self.inspector)

        # Proporção inicial 70/30
        splitter.setSizes([480, 200])

        # ===============================================================
        # BARRA DE STATUS INFERIOR (Footer)
        # ===============================================================
        footer = QWidget()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 10, 12, 10)
        footer_layout.setSpacing(20)

        # Pasta de Saída
        out_lbl = QLabel("Saída:")
        out_lbl.setProperty("subheading", True)
        out_lbl.setMinimumWidth(40)
        footer_layout.addWidget(out_lbl)

        self.txt_output_folder = QLineEdit()
        self.txt_output_folder.setReadOnly(True)
        self.txt_output_folder.setPlaceholderText("Selecione a pasta de saída…")
        self.txt_output_folder.setMinimumWidth(350)
        self.txt_output_folder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        footer_layout.addWidget(self.txt_output_folder, 1)

        self.btn_browse_output = QPushButton("Procurar…")
        self.btn_browse_output.clicked.connect(self._on_browse_output)
        footer_layout.addWidget(self.btn_browse_output)

        # Separador visual
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("background-color: #3F3F46; border: none; width: 1px;")
        footer_layout.addWidget(sep)

        # Progress Bar
        prog_lbl = QLabel("Progresso:")
        prog_lbl.setProperty("subheading", True)
        prog_lbl.setMinimumWidth(65)
        footer_layout.addWidget(prog_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(260)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%  (%v/%m)")
        footer_layout.addWidget(self.progress_bar)

        # Separador
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("background-color: #3F3F46; border: none; width: 1px;")
        footer_layout.addWidget(sep2)

        # Botão Cancelar
        self.btn_cancel = QPushButton("Cancelar Operação")
        self.btn_cancel.setProperty("danger", True)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setMinimumWidth(140)
        self.btn_cancel.clicked.connect(self.batch_cancel_requested.emit)
        footer_layout.addWidget(self.btn_cancel)

        # Botão Principal — INICIAR LOTE
        self.btn_start_batch = QPushButton("INICIAR LOTE")
        self.btn_start_batch.setProperty("primary", True)
        self.btn_start_batch.setMinimumWidth(180)
        self.btn_start_batch.setMinimumHeight(38)
        self.btn_start_batch.clicked.connect(self._on_start_batch)
        footer_layout.addWidget(self.btn_start_batch)

        main_layout.addWidget(footer)

        # Status bar nativa do Qt (para mensagens temporárias)
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("""
            QStatusBar { background: #18181B; color: #A1A1AA; border-top: 1px solid #3F3F46; }
            QStatusBar::item { border: none; }
        """)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Pronto. Arraste arquivos ou use 'Adicionar Arquivos'.")

    def _apply_styles(self) -> None:
        self.setStyleSheet(get_stylesheet())

    def _load_mock_data(self) -> None:
        """Carrega dados de exemplo para validação visual."""
        for track in MOCK_TRACKS:
            self.music_table.add_track(track)
        self._update_selection_count()

    # ------------------------------------------------------------------
    # Slots / Handlers
    # ------------------------------------------------------------------
    def _on_add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Adicionar Arquivos de Áudio",
            "",
            "Áudio (*.mp3 *.flac *.wav *.m4a *.aac);;Todos (*.*)"
        )
        if files:
            self.files_add_requested.emit(files)

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Adicionar Pasta")
        if folder:
            self.folder_add_requested.emit(folder)

    def _start_folder_scan(self, folder_path: str) -> None:
        """Inicia escaneamento assíncrono de pasta."""
        self.status_bar.showMessage(f"Escaneando pasta: {folder_path}…")
        self._folder_scan_worker = WorkerManager.scan_folder(folder_path)
        self._folder_scan_worker.signals.files_found.connect(self._on_folder_files_found)
        self._folder_scan_worker.signals.error.connect(self._on_folder_scan_error)
        self._folder_scan_worker.signals.finished.connect(lambda: self.status_bar.showMessage("Escaneamento concluído.", 3000))

    def _on_folder_files_found(self, files: list[str]) -> None:
        """Callback quando arquivos são encontrados no escaneamento de pasta."""
        if files:
            self.files_add_requested.emit(files)
        else:
            self.status_bar.showMessage("Nenhum arquivo de áudio suportado encontrado na pasta.", 5000)

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

        self.status_bar.showMessage(f"Analisando {len(file_paths)} arquivo(s)…")
        self._analysis_worker = WorkerManager.start_analysis(file_paths, start_row)
        self._analysis_worker.signals.track_analyzed.connect(self._on_track_analyzed)
        self._analysis_worker.signals.track_failed.connect(self._on_track_analysis_failed)
        self._analysis_worker.signals.finished.connect(self._on_analysis_finished)
        self._analysis_worker.signals.cancelled.connect(lambda: self.status_bar.showMessage("Análise cancelada.", 3000))

    @Slot(int, dict)
    def _on_track_analyzed(self, row: int, track_data: dict) -> None:
        """Atualiza a tabela com os dados analisados."""
        self.music_table.setRowHeight(row, 44)
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
        self.status_bar.showMessage("Análise concluída.", 3000)
        self._analysis_worker = None

    def _start_batch_processing(self, settings: dict) -> None:
        """Inicia processamento em lote assíncrono."""
        selected_rows = settings.pop("selected_rows", [])
        if not selected_rows:
            return

        self._batch_worker = WorkerManager.start_batch(self, selected_rows, settings)
        self._batch_worker.signals.track_started.connect(lambda row: self.music_table.update_row_status(row, "pending", "Processando…"))
        self._batch_worker.signals.track_finished.connect(self._on_track_batch_finished)
        self._batch_worker.signals.track_failed.connect(self._on_track_batch_failed)
        self._batch_worker.signals.overall_progress.connect(self.set_overall_progress)
        self._batch_worker.signals.finished.connect(self.batch_finished)
        self._batch_worker.signals.cancelled.connect(lambda: self.status_bar.showMessage("Lote cancelado pelo usuário.", 3000))

    def _on_track_batch_finished(self, row: int, result) -> None:
        status_key = "completed" if result.status == "normalized" else "completed"
        status_text = "Concluído" if result.status == "normalized" else "Bypass (Copiado)"
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
        self.batch_finished(False, "Operação cancelada pelo usuário.")

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

    def _on_browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Saída")
        if folder:
            self._output_folder = folder
            self.txt_output_folder.setText(folder)
            self.output_folder_changed.emit(folder)

    def _on_start_batch(self) -> None:
        selected_rows = self.music_table.get_selected_rows()
        if not selected_rows:
            QMessageBox.information(
                self,
                "Nenhuma faixa selecionada",
                "Marque ao menos uma faixa na tabela para iniciar o processamento em lote."
            )
            return

        if not self._output_folder:
            QMessageBox.warning(
                self,
                "Pasta de saída não definida",
                "Selecione a pasta de saída antes de iniciar o lote."
            )
            return

        settings = self.inspector.get_current_settings()
        settings["selected_rows"] = selected_rows
        settings["output_folder"] = self._output_folder

        self.batch_start_requested.emit(settings)
        self._set_batch_running(True)

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
        self.lbl_selection_count.setText(f"{selected} de {total} selecionadas")

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
            self.status_bar.showMessage("Processando lote…")
        else:
            self.status_bar.showMessage("Lote finalizado.")

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

    def set_overall_progress(self, value: int) -> None:
        self.progress_bar.setValue(value)

    def batch_finished(self, success: bool, message: str = "") -> None:
        self._set_batch_running(False)
        if success:
            self.status_bar.showMessage(message or "Normalização concluída com sucesso.", 5000)
        else:
            self.status_bar.showMessage(message or "Erro durante a normalização.", 5000)
            QMessageBox.critical(self, "Erro no Lote", message or "Ocorreu um erro durante o processamento.")


# Import tardio para evitar circular
from PySide6.QtWidgets import QComboBox, QFrame