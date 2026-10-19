"""Trabalhadores assíncronos (QRunnable) para análise e normalização de áudio."""

from __future__ import annotations

import json
import logging
import os
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, Signal, Slot, QThreadPool

from core.ffmpeg_engine import (
    FFmpegEngine,
    NormalizationResult,
    LoudnessMetrics,
    should_bypass,
)
from core.audio_analyzer import AudioAnalyzer
from core.metadata_handler import MetadataHandler
from core.settings import DEFAULT_CONFIG

if TYPE_CHECKING:
    from ui.main_window import MainWindow


logger = logging.getLogger(__name__)


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
    overall_progress = Signal(int, int)     # current, total
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

    def __init__(self, file_paths: list[str], start_row: int, targets: dict | None = None):
        super().__init__()
        self.file_paths = file_paths
        self.start_row = start_row
        self.signals = AnalysisSignals()
        self._cancelled = False
        self.engine = FFmpegEngine()
        self.analyzer = AudioAnalyzer(self.engine)
        self.setAutoDelete(True)

        # Alvos informados pela interface; cai para os padrões do núcleo.
        targets = targets or {}
        self.target_i = float(targets.get("target_loudness", DEFAULT_CONFIG["target_loudness"]))
        self.target_tp = float(targets.get("target_true_peak", DEFAULT_CONFIG["target_true_peak"]))

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
                # Validação prévia do arquivo
                path = Path(file_path)
                if not path.exists():
                    raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
                if not path.is_file():
                    raise ValueError(f"Caminho não é um arquivo: {file_path}")
                if path.stat().st_size == 0:
                    raise ValueError(f"Arquivo vazio (0 bytes): {file_path}")

                # Análise de loudness (passagem 1)
                loudness = self.engine.analyze_loudness(file_path)

                # Inspeção técnica (ffprobe)
                info = self.analyzer.inspect(file_path)

                # Determina status inicial correto respeitando os alvos do usuário
                bypass = should_bypass(
                    loudness,
                    target_i=self.target_i,
                    target_tp=self.target_tp,
                    same_container=True,
                )
                status_key = "bypass" if bypass else "analyzed"
                status_text = "Pronto (Bypass)" if bypass else "Analisado"

                track_data = {
                    "name": path.name,
                    "path": str(path),
                    "duration": self._format_duration(info, path),
                    "format": info.codec_name or path.suffix.lstrip(".").upper(),
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

            except FileNotFoundError as e:
                self.signals.track_failed.emit(row, f"Arquivo não encontrado: {e}")
            except PermissionError as e:
                self.signals.track_failed.emit(row, f"Sem permissão de leitura: {e}")
            except ValueError as e:
                self.signals.track_failed.emit(row, f"Arquivo inválido: {e}")
            except RuntimeError as e:
                self.signals.track_failed.emit(row, f"Erro no FFmpeg: {e}")
            except Exception as e:
                # Log detalhado para debug
                traceback.print_exc()
                self.signals.track_failed.emit(row, f"Erro inesperado: {type(e).__name__}: {e}")

        self.signals.finished.emit()

    def _format_duration(self, info, path: Path) -> str:
        """Obtém duração real a partir das métricas inspecionadas."""
        if getattr(info, "duration", None) is not None:
            seconds = float(info.duration)
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}:{secs:02d}"

        # Fallback: estimativa via bitrate/tamanho
        try:
            size = path.stat().st_size
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

    def __init__(self, tracks: list[dict], settings: dict):
        super().__init__()
        self.tracks = tracks
        self.settings = settings
        self.signals = BatchSignals()
        self._cancelled = False
        self.engine = FFmpegEngine()
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        total = len(self.tracks)
        if total == 0:
            self.signals.finished.emit(True, "Nenhuma faixa para processar")
            return

        output_folder = Path(self.settings["output_folder"])
        try:
            output_folder.mkdir(parents=True, exist_ok=True)
            # Testa permissão de escrita
            test_file = output_folder / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
        except PermissionError as e:
            self.signals.finished.emit(False, f"Sem permissão de escrita na pasta de saída: {e}")
            return
        except Exception as e:
            self.signals.finished.emit(False, f"Erro ao acessar pasta de saída: {e}")
            return

        manifest_path = output_folder / ".musicenhancer_manifest.json"
        manifest = self._load_manifest(manifest_path)

        success_count = 0
        error_messages = []
        warning_messages = []

        # Obtém preferências de sobrescrita
        overwrite_choice = self.settings.get("overwrite_choice", "rename")
        overwrite_apply_all = self.settings.get("overwrite_apply_all", False)

        target_lufs = self.settings.get("target_loudness", DEFAULT_CONFIG["target_loudness"])
        target_tp = self.settings.get("target_true_peak", DEFAULT_CONFIG["target_true_peak"])
        target_lra = self.settings.get("target_lra", DEFAULT_CONFIG["target_lra"])

        for idx, track_data in enumerate(self.tracks):
            if self._cancelled:
                self.signals.cancelled.emit()
                return

            row = track_data.get("row", idx)
            source_str = track_data.get("path")
            if not source_str:
                error_messages.append(f"Linha {row}: dados da faixa não encontrados")
                self.signals.track_failed.emit(row, "Dados da faixa não encontrados")
                continue

            source_path = Path(source_str)
            dest_path = output_folder / source_path.name

            # Verifica se já foi processado (bypass via manifesto)
            manifest_key = str(source_path)
            if manifest_key in manifest.get("entries", {}):
                existing = manifest["entries"][manifest_key]
                # Se o arquivo de destino existe e parâmetros são iguais, pula
                if Path(existing.get("destination", "")).exists():
                    if (existing.get("target_lufs") == target_lufs and
                        existing.get("target_true_peak") == target_tp and
                        existing.get("target_lra") == target_lra):
                        self.signals.track_finished.emit(row, NormalizationResult(
                            status="bypass",
                            input_metrics=LoudnessMetrics(
                                input_i=float(existing.get('input_lufs', 0.0)),
                                input_tp=float(existing.get('input_true_peak', 0.0)),
                                input_lra=0.0,
                                input_thresh=0.0,
                            ),
                            post_validation=None,
                            normalization_type="bypass",
                            metadata_preserved=bool(existing.get("metadata_preserved", True)),
                        ))
                        success_count += 1
                        self.signals.overall_progress.emit(idx + 1, total)
                        continue

            # Trata arquivos existentes baseado na escolha do usuário
            if dest_path.exists():
                if overwrite_choice == "skip":
                    # Pula este arquivo
                    self.signals.track_finished.emit(row, NormalizationResult(
                        status="skipped",
                        input_metrics=LoudnessMetrics(
                            input_i=0.0, input_tp=0.0, input_lra=0.0, input_thresh=0.0
                        ),
                        post_validation=None
                    ))
                    success_count += 1
                    self.signals.overall_progress.emit(idx + 1, total)
                    continue
                elif overwrite_choice == "rename":
                    # Renomeia com sufixo numérico
                    base = dest_path.stem
                    suffix = dest_path.suffix
                    counter = 1
                    while dest_path.exists():
                        dest_path = output_folder / f"{base}_{counter}{suffix}"
                        counter += 1
                # Se overwrite_choice == "replace", sobrescreve (comportamento padrão)

            self.signals.track_started.emit(row)

            try:
                result = self.engine.normalize(
                    str(source_path),
                    str(dest_path),
                    target_i=target_lufs,
                    target_tp=target_tp,
                    target_lra=target_lra,
                )
                self._update_manifest(manifest, source_path, dest_path, result)
                if result.warnings:
                    for warning in result.warnings:
                        warning_messages.append(f"{source_path.name}: {warning}")
                    logger.warning(
                        "Avisos ao processar '%s': %s",
                        source_path.name,
                        "; ".join(result.warnings),
                    )

                self.signals.track_finished.emit(row, result)
                success_count += 1

            except FileNotFoundError:
                error_msg = f"{source_path.name}: Arquivo de origem não encontrado"
                error_messages.append(error_msg)
                self.signals.track_failed.emit(row, error_msg)
            except PermissionError:
                error_msg = f"{source_path.name}: Sem permissão para ler/escrever"
                error_messages.append(error_msg)
                self.signals.track_failed.emit(row, error_msg)
            except ValueError as e:
                error_msg = f"{source_path.name}: Arquivo ou parâmetro inválido ({e})"
                error_messages.append(error_msg)
                self.signals.track_failed.emit(row, error_msg)
            except RuntimeError as e:
                error_msg = f"{source_path.name}: {e}"
                error_messages.append(error_msg)
                self.signals.track_failed.emit(row, str(e))
            except Exception as e:
                traceback.print_exc()
                error_msg = f"{source_path.name}: Erro inesperado ({type(e).__name__})"
                error_messages.append(error_msg)
                self.signals.track_failed.emit(row, error_msg)

            # Progresso geral
            self.signals.overall_progress.emit(idx + 1, total)

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
        if warning_messages:
            message += " Avisos: " + "; ".join(warning_messages[:3])
            if len(warning_messages) > 3:
                message += f" ... e mais {len(warning_messages) - 3} aviso(s)."

        self.signals.finished.emit(success, message)

    def _load_manifest(self, path: Path) -> dict:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {"version": 1, "entries": {}}
            except Exception:
                return {"version": 1, "entries": {}}
        return {"version": 1, "entries": {}}

    def _save_manifest(self, path: Path, manifest: dict) -> None:
        # Escrita atômica: escreve em temp e renomeia
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        temp_path.replace(path)

    def _update_manifest(self, manifest: dict, source: Path, dest: Path, result: NormalizationResult) -> None:
        entry = {
            "source": str(source),
            "destination": str(dest),
            "status": result.status,
            "normalization_type": result.normalization_type,
            "metadata_preserved": result.metadata_preserved,
            "input_lufs": result.input_metrics.input_i,
            "input_true_peak": result.input_metrics.input_tp,
            "target_lufs": self.settings.get("target_loudness", DEFAULT_CONFIG["target_loudness"]),
            "target_true_peak": self.settings.get("target_true_peak", DEFAULT_CONFIG["target_true_peak"]),
            "target_lra": self.settings.get("target_lra", DEFAULT_CONFIG["target_lra"]),
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
        cancelled = Signal()

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
            if not self.folder_path.exists():
                self.signals.error.emit(f"Pasta não encontrada: {self.folder_path}")
                return
            if not self.folder_path.is_dir():
                self.signals.error.emit(f"Caminho não é uma pasta: {self.folder_path}")
                return

            files = []
            for ext in self.SUPPORTED_EXTS:
                for file_path in self.folder_path.rglob(f"*{ext}"):
                    if self._cancelled:
                        self.signals.cancelled.emit()
                        return
                    if file_path.is_file() and file_path.stat().st_size > 0:
                        files.append(str(file_path))
            self.signals.files_found.emit(files)
        except PermissionError as e:
            self.signals.error.emit(f"Sem permissão para acessar a pasta: {e}")
        except Exception as e:
            traceback.print_exc()
            self.signals.error.emit(f"Erro ao escanear: {type(e).__name__}: {e}")
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
            # Ajusta paralelismo baseado em CPU (mínimo 2, máximo 4 para não saturar I/O)
            threads = max(2, min(4, (os.cpu_count() or 2) // 2))
            cls._pool.setMaxThreadCount(threads)
        return cls._instance

    @classmethod
    def pool(cls) -> QThreadPool:
        if cls._pool is None:
            cls._pool = QThreadPool.globalInstance()
            threads = max(2, min(4, (os.cpu_count() or 2) // 2))
            cls._pool.setMaxThreadCount(threads)
        return cls._pool

    @classmethod
    def start_analysis(cls, file_paths: list[str], start_row: int, targets: dict | None = None) -> AnalysisWorker:
        worker = AnalysisWorker(file_paths, start_row, targets)
        cls.pool().start(worker)
        return worker

    @classmethod
    def start_batch(cls, tracks: list[dict], settings: dict) -> BatchWorker:
        worker = BatchWorker(tracks, settings)
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
        cls.pool().waitForDone(3000)  # Aguarda até 3s para finalizar