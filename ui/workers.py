"""Trabalhadores assíncronos (QRunnable) para análise e normalização de áudio."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, Signal, Slot, QThreadPool

from core.ffmpeg_engine import FFmpegEngine, NormalizationResult
from core.audio_analyzer import AudioAnalyzer
from core.metadata_handler import MetadataHandler

if TYPE_CHECKING:
    from ui.main_window import MainWindow


# =====================================================================
# Sinais dos Workers (devem herdar de QObject)
# =====================================================================

class AnalysisSignals(QObject):
    """Sinais emitidos durante a análise de arquivos."""
    track_analyzed = Signal(int, dict)      # row_index, track_data
    track_failed = Signal(int, str)         # row_index, error_message
    finished = Signal()                     # análise completa
    cancelled = Signal()


class BatchSignals(QObject):
    """Sinais emitidos durante o processamento em lote."""
    track_started = Signal(int)             # row_index
    track_progress = Signal(int, int)       # row_index, progress_percent
    track_finished = Signal(int, NormalizationResult)  # row_index, result
    track_failed = Signal(int, str)         # row_index, error_message
    overall_progress = Signal(int)          # 0-100
    finished = Signal(bool, str)            # success, message
    cancelled = Signal()


# =====================================================================
# Worker de Análise Inicial
# =====================================================================

class AnalysisWorker(QRunnable):
    """
    Worker para analisar múltiplos arquivos de áudio em background.
    Preenche LUFS, True Peak, Duração, Bitrate, Sample Rate, Bit Depth na tabela.
    """

    def __init__(self, file_paths: list[str], start_row: int):
        super().__init__()
        self.file_paths = file_paths
        self.start_row = start_row
        self.signals = AnalysisSignals()
        self._cancelled = False
        self.engine = FFmpegEngine()
        self.analyzer = AudioAnalyzer(self.engine)
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        for i, file_path in enumerate(self.file_paths):
            if self._cancelled:
                self.signals.cancelled.emit()
                return

            row = self.start_row + i
            try:
                # Análise de loudness (passagem 1)
                loudness = self.engine.analyze_loudness(file_path)

                # Inspeção técnica (ffprobe)
                info = self.analyzer.inspect(file_path)

                # Determina status inicial
                bypass = -14.5 <= loudness.input_i <= -13.5 and loudness.input_tp <= -1.0
                status_key = "analyzed" if not bypass else "pending"
                status_text = "Analisado" if not bypass else "Pronto (Bypass)"

                track_data = {
                    "name": Path(file_path).name,
                    "path": file_path,
                    "duration": self._format_duration(info),
                    "format": info.codec_name or Path(file_path).suffix.lstrip(".").upper(),
                    "lufs": loudness.input_i,
                    "true_peak": loudness.input_tp,
                    "lra": loudness.input_lra,
                    "bitrate": self._format_bitrate(info.bit_rate),
                    "sample_rate": info.sample_rate,
                    "bit_depth": info.bits_per_raw_sample,
                    "status": status_text,
                    "status_key": status_key,
                }

                self.signals.track_analyzed.emit(row, track_data)

            except Exception as e:
                self.signals.track_failed.emit(row, str(e))

        self.signals.finished.emit()

    def _format_duration(self, info) -> str:
        # Duração estimada via bitrate e tamanho do arquivo (aproximado)
        # Para precisão real, precisaríamos do ffprobe -show_entries format=duration
        try:
            size = Path(info.path).stat().st_size if hasattr(info, 'path') else 0
            br = info.bit_rate or 0
            if br > 0 and size > 0:
                seconds = (size * 8) / br
                mins = int(seconds // 60)
                secs = int(seconds % 60)
                return f"{mins}:{secs:02d}"
        except Exception:
            pass
        return "—"

    def _format_bitrate(self, bit_rate: int | None) -> str:
        if bit_rate is None or bit_rate <= 0:
            return "—"
        kbps = bit_rate // 1000
        if kbps >= 1000:
            return f"{kbps / 1000:.1f} Mbps"
        return f"{kbps} kbps"


# =====================================================================
# Worker de Processamento em Lote (Normalização)
# =====================================================================

class BatchWorker(QRunnable):
    """
    Worker para processar normalização de múltiplas faixas selecionadas.
    Executa FFmpegEngine.normalize + MetadataHandler + atualização de manifesto.
    """

    def __init__(self, main_window: "MainWindow", selected_rows: list[int], settings: dict):
        super().__init__()
        self.main_window = main_window
        self.selected_rows = selected_rows
        self.settings = settings
        self.signals = BatchSignals()
        self._cancelled = False
        self.engine = FFmpegEngine()
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        total = len(self.selected_rows)
        if total == 0:
            self.signals.finished.emit(True, "Nenhuma faixa para processar")
            return

        output_folder = Path(self.settings["output_folder"])
        output_folder.mkdir(parents=True, exist_ok=True)

        manifest_path = output_folder / ".musicenhancer_manifest.json"
        manifest = self._load_manifest(manifest_path)

        success_count = 0
        error_messages = []

        for idx, row in enumerate(self.selected_rows):
            if self._cancelled:
                self.signals.cancelled.emit()
                return

            track_data = self.main_window.music_table.get_track_data(row)
            if not track_data:
                continue

            source_path = Path(track_data["path"])
            dest_path = output_folder / source_path.name

            # Evita sobrescrever arquivos existentes
            if dest_path.exists():
                base = dest_path.stem
                suffix = dest_path.suffix
                counter = 1
                while dest_path.exists():
                    dest_path = output_folder / f"{base}_{counter}{suffix}"
                    counter += 1

            self.signals.track_started.emit(row)

            try:
                result = self.engine.normalize(str(source_path), str(dest_path))
                self._update_manifest(manifest, source_path, dest_path, result)

                self.signals.track_finished.emit(row, result)
                success_count += 1

            except Exception as e:
                error_msg = f"{source_path.name}: {e}"
                error_messages.append(error_msg)
                self.signals.track_failed.emit(row, str(e))

            # Progresso geral
            overall = int(((idx + 1) / total) * 100)
            self.signals.overall_progress.emit(overall)

        # Salva manifesto
        try:
            self._save_manifest(manifest_path, manifest)
        except Exception as e:
            error_messages.append(f"Erro ao salvar manifesto: {e}")

        success = len(error_messages) == 0
        message = f"Concluído: {success_count}/{total} faixas processadas."
        if error_messages:
            message += " Erros: " + "; ".join(error_messages[:3])
            if len(error_messages) > 3:
                message += f" ... e mais {len(error_messages) - 3} erro(s)."

        self.signals.finished.emit(success, message)

    def _load_manifest(self, path: Path) -> dict:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"version": 1, "entries": {}}

    def _save_manifest(self, path: Path, manifest: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def _update_manifest(self, manifest: dict, source: Path, dest: Path, result: NormalizationResult) -> None:
        entry = {
            "source": str(source),
            "destination": str(dest),
            "status": result.status,
            "input_lufs": result.input_metrics.input_i,
            "input_true_peak": result.input_metrics.input_tp,
            "target_lufs": self.settings.get("target_loudness", -14.0),
            "target_true_peak": self.settings.get("target_true_peak", -1.0),
        }
        manifest["entries"][str(source)] = entry


# =====================================================================
# Worker de Escaneamento de Pasta (recursivo)
# =====================================================================

class FolderScanWorker(QRunnable):
    """Worker para escanear pasta recursivamente em busca de arquivos de áudio."""

    SUPPORTED_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".aac"}

    class Signals(QObject):
        files_found = Signal(list)      # lista de caminhos
        finished = Signal()
        error = Signal(str)

    def __init__(self, folder_path: str):
        super().__init__()
        self.folder_path = Path(folder_path)
        self.signals = self.Signals()
        self._cancelled = False
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        try:
            files = []
            for ext in self.SUPPORTED_EXTS:
                for file_path in self.folder_path.rglob(f"*{ext}"):
                    if self._cancelled:
                        self.signals.cancelled.emit()
                        return
                    if file_path.is_file():
                        files.append(str(file_path))
            self.signals.files_found.emit(files)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()


# =====================================================================
# Gerenciador de Thread Pool (Singleton)
# =====================================================================

class WorkerManager:
    """Gerencia o QThreadPool global e ciclo de vida dos workers."""

    _instance = None
    _pool: QThreadPool | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._pool = QThreadPool.globalInstance()
            cls._pool.setMaxThreadCount(2)  # Limita para não saturar CPU/Disco
        return cls._instance

    @classmethod
    def pool(cls) -> QThreadPool:
        if cls._pool is None:
            cls._pool = QThreadPool.globalInstance()
            cls._pool.setMaxThreadCount(2)
        return cls._pool

    @classmethod
    def start_analysis(cls, file_paths: list[str], start_row: int) -> AnalysisWorker:
        worker = AnalysisWorker(file_paths, start_row)
        cls.pool().start(worker)
        return worker

    @classmethod
    def start_batch(cls, main_window: "MainWindow", selected_rows: list[int], settings: dict) -> BatchWorker:
        worker = BatchWorker(main_window, selected_rows, settings)
        cls.pool().start(worker)
        return worker

    @classmethod
    def scan_folder(cls, folder_path: str) -> FolderScanWorker:
        worker = FolderScanWorker(folder_path)
        cls.pool().start(worker)
        return worker

    @classmethod
    def cancel_all(cls) -> None:
        cls.pool().clear()
        cls.pool().waitForDone()