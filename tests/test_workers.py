"""Testes dos workers de análise e processamento em lote."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6")

from core.ffmpeg_engine import LoudnessMetrics, NormalizationResult
from ui.workers import AnalysisWorker, BatchWorker


def metrics(i: float = -20.0, tp: float = -3.0) -> LoudnessMetrics:
    return LoudnessMetrics(input_i=i, input_tp=tp, input_lra=5.0, input_thresh=i - 10.0)


def probe_payload() -> dict:
    return {
        "streams": [{
            "codec_type": "audio",
            "codec_name": "mp3",
            "sample_rate": "44100",
            "bit_rate": "320000",
            "channels": "2",
            "channel_layout": "stereo",
            "sample_fmt": "fltp",
        }],
        "format": {},
    }


class TestAnalysisWorker:
    """A análise inicial deve respeitar os alvos informados pela interface."""

    def _make_worker(self, tmp_path: Path, targets: dict) -> tuple[AnalysisWorker, MagicMock, list, list]:
        audio = tmp_path / "track.mp3"
        audio.write_bytes(b"ID3")
        with patch("ui.workers.FFmpegEngine") as engine_cls:
            engine = MagicMock()
            engine_cls.return_value = engine
            worker = AnalysisWorker([str(audio)], 0, targets)
        analyzed: list = []
        failed: list = []
        worker.signals.track_analyzed.connect(lambda row, data: analyzed.append((row, data)))
        worker.signals.track_failed.connect(lambda row, error: failed.append((row, error)))
        return worker, engine, analyzed, failed

    def test_custom_target_marks_as_analyzed(self, tmp_path: Path) -> None:
        worker, engine, analyzed, failed = self._make_worker(
            tmp_path, {"target_loudness": -11.0, "target_true_peak": -1.0}
        )
        engine.analyze_loudness.return_value = metrics(i=-14.0, tp=-1.5)
        engine.probe.return_value = probe_payload()

        worker.run()

        assert failed == []
        assert analyzed[0][1]["status_key"] == "analyzed"

    def test_default_target_marks_as_bypass(self, tmp_path: Path) -> None:
        worker, engine, analyzed, failed = self._make_worker(
            tmp_path, {"target_loudness": -14.0, "target_true_peak": -1.0}
        )
        engine.analyze_loudness.return_value = metrics(i=-14.0, tp=-1.5)
        engine.probe.return_value = probe_payload()

        worker.run()

        assert failed == []
        assert analyzed[0][1]["status_key"] == "bypass"

    def test_missing_file_failure_does_not_stop_other_tracks(self, tmp_path: Path) -> None:
        good = tmp_path / "good.mp3"
        good.write_bytes(b"ID3")
        with patch("ui.workers.FFmpegEngine") as engine_cls:
            engine = MagicMock()
            engine_cls.return_value = engine
            worker = AnalysisWorker([str(tmp_path / "missing.mp3"), str(good)], 0, {})
        analyzed: list = []
        failed: list = []
        worker.signals.track_analyzed.connect(lambda row, data: analyzed.append(row))
        worker.signals.track_failed.connect(lambda row, error: failed.append(row))
        engine.analyze_loudness.return_value = metrics()
        engine.probe.return_value = probe_payload()

        worker.run()

        assert failed == [0]
        assert analyzed == [1]


class TestBatchWorker:
    """Processamento em lote deve continuar após falhas isoladas."""

    def _make_worker(self, tmp_path: Path, tracks: list[dict], settings: dict) -> BatchWorker:
        with patch("ui.workers.FFmpegEngine") as engine_cls:
            engine = MagicMock()
            engine_cls.return_value = engine
            worker = BatchWorker(tracks, settings)
        worker.engine = engine
        return worker

    def _settings(self, tmp_path: Path, **overrides) -> dict:
        settings = {
            "output_folder": str(tmp_path / "out"),
            "overwrite_choice": "replace",
            "overwrite_apply_all": True,
            "target_loudness": -14.0,
            "target_true_peak": -1.0,
            "target_lra": 11.0,
        }
        settings.update(overrides)
        return settings

    def test_continues_after_track_failure(self, tmp_path: Path) -> None:
        tracks = [
            {"row": 0, "path": str(tmp_path / "a.mp3")},
            {"row": 1, "path": str(tmp_path / "b.mp3")},
        ]
        worker = self._make_worker(tmp_path, tracks, self._settings(tmp_path))
        finished: list = []
        failed: list = []
        completed: list = []
        worker.signals.track_failed.connect(lambda row, error: failed.append(row))
        worker.signals.track_finished.connect(lambda row, result: completed.append(row))
        worker.signals.finished.connect(lambda success, message: finished.append((success, message)))

        worker.engine.normalize.side_effect = [
            RuntimeError("arquivo corrompido"),
            NormalizationResult("normalized", metrics(), (True, [])),
        ]

        worker.run()

        assert failed == [0]
        assert completed == [1]
        success, message = finished[0]
        assert success is False
        assert "1/2" in message

    def test_passes_targets_to_engine(self, tmp_path: Path) -> None:
        tracks = [{"row": 0, "path": str(tmp_path / "a.mp3")}]
        settings = self._settings(tmp_path, target_loudness=-11.0, target_true_peak=-0.5, target_lra=10.0)
        worker = self._make_worker(tmp_path, tracks, settings)
        worker.engine.normalize.return_value = NormalizationResult(
            "normalized", metrics(), (True, [])
        )

        worker.run()

        call = worker.engine.normalize.call_args
        assert call.kwargs["target_i"] == -11.0
        assert call.kwargs["target_tp"] == -0.5
        assert call.kwargs["target_lra"] == 10.0

    def test_metadata_warning_is_reported_but_success_kept(self, tmp_path: Path) -> None:
        tracks = [{"row": 0, "path": str(tmp_path / "a.mp3")}]
        worker = self._make_worker(tmp_path, tracks, self._settings(tmp_path))
        finished: list = []
        worker.signals.finished.connect(lambda success, message: finished.append((success, message)))
        worker.engine.normalize.return_value = NormalizationResult(
            "normalized",
            metrics(),
            (True, []),
            metadata_preserved=False,
            warnings=("Falha não crítica ao copiar metadados: tags",),
        )

        worker.run()

        success, message = finished[0]
        assert success is True
        assert "Avisos" in message

    def test_writes_manifest_after_batch(self, tmp_path: Path) -> None:
        tracks = [{"row": 0, "path": str(tmp_path / "a.mp3")}]
        worker = self._make_worker(tmp_path, tracks, self._settings(tmp_path))
        worker.engine.normalize.return_value = NormalizationResult(
            "normalized", metrics(), (True, [])
        )

        worker.run()

        manifest = (tmp_path / "out" / ".musicenhancer_manifest.json")
        assert manifest.is_file()
        assert "a.mp3" in manifest.read_text(encoding="utf-8")

    def test_manifest_reuse_requires_matching_lra(self, tmp_path: Path) -> None:
        output_folder = tmp_path / "out"
        output_folder.mkdir()
        source = tmp_path / "a.mp3"
        source.write_bytes(b"ID3")
        existing = output_folder / "a.mp3"
        existing.write_bytes(b"audio")
        manifest = output_folder / ".musicenhancer_manifest.json"
        manifest.write_text(
            '{"version": 1, "entries": {"%s": {"destination": "%s", "target_lufs": -14.0, '
            '"target_true_peak": -1.0, "target_lra": 7.0, "input_lufs": -14.0, '
            '"input_true_peak": -1.5}}}'
            % (str(source).replace("\\", "\\\\"), str(existing).replace("\\", "\\\\")),
            encoding="utf-8",
        )
        tracks = [{"row": 0, "path": str(source)}]
        worker = self._make_worker(tmp_path, tracks, self._settings(tmp_path))
        worker.engine.normalize.return_value = NormalizationResult(
            "normalized", metrics(), (True, [])
        )

        worker.run()

        # LRA diferente deve forçar novo processamento.
        worker.engine.normalize.assert_called_once()
