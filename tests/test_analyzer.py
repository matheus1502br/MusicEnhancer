"""Testes do AudioAnalyzer: inspeção e validação pós-exportação."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.audio_analyzer import AudioAnalyzer, AudioMetrics
from core.ffmpeg_engine import FFmpegEngine


class TestAudioAnalyzerInspect:
    """Extração de metadados técnicos via ffprobe."""

    def test_inspect_populates_dataclass(self) -> None:
        engine = MagicMock(spec=FFmpegEngine)
        engine.probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "sample_rate": "48000",
                    "bit_rate": "256000",
                    "bits_per_raw_sample": "24",
                    "codec_name": "flac",
                    "channels": "2",
                }
            ],
            "format": {"bit_rate": "256000"},
        }
        analyzer = AudioAnalyzer(engine)
        metrics = analyzer.inspect("dummy.flac")

        assert isinstance(metrics, AudioMetrics)
        assert metrics.sample_rate == 48000
        assert metrics.bit_rate == 256000
        assert metrics.bits_per_raw_sample == 24
        assert metrics.codec_name == "flac"
        assert metrics.channels == 2

    def test_inspect_falls_back_to_format_bitrate(self) -> None:
        engine = MagicMock(spec=FFmpegEngine)
        engine.probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "sample_rate": "44100",
                    "codec_name": "mp3",
                    "channels": "2",
                }
            ],
            "format": {"bit_rate": "320000"},
        }
        analyzer = AudioAnalyzer(engine)
        metrics = analyzer.inspect("dummy.mp3")
        assert metrics.bit_rate == 320000

    def test_inspect_raises_when_no_audio_stream(self) -> None:
        engine = MagicMock(spec=FFmpegEngine)
        engine.probe.return_value = {"streams": [{"codec_type": "video"}]}
        analyzer = AudioAnalyzer(engine)
        with pytest.raises(ValueError, match="Nenhum stream de áudio"):
            analyzer.inspect("dummy.mp4")


class TestAudioAnalyzerValidateLosslessExport:
    """Validação de sample rate e bit-depth em formatos sem perdas."""

    def test_validation_pass(self) -> None:
        engine = MagicMock(spec=FFmpegEngine)

        def probe_side_effect(path):
            if "original" in str(path):
                return {
                    "streams": [{"codec_type": "audio", "sample_rate": "48000", "bits_per_raw_sample": "24"}],
                    "format": {},
                }
            return {
                "streams": [{"codec_type": "audio", "sample_rate": "48000", "bits_per_raw_sample": "24"}],
                "format": {},
            }

        engine.probe.side_effect = probe_side_effect
        analyzer = AudioAnalyzer(engine)
        ok, failures = analyzer.validate_lossless_export("original.flac", "output.flac")
        assert ok is True
        assert failures == []

    def test_validation_fail_sample_rate(self) -> None:
        engine = MagicMock(spec=FFmpegEngine)

        def probe_side_effect(path):
            if "original" in str(path):
                return {"streams": [{"codec_type": "audio", "sample_rate": "48000", "bits_per_raw_sample": "24"}], "format": {}}
            return {"streams": [{"codec_type": "audio", "sample_rate": "44100", "bits_per_raw_sample": "24"}], "format": {}}

        engine.probe.side_effect = probe_side_effect
        analyzer = AudioAnalyzer(engine)
        ok, failures = analyzer.validate_lossless_export("original.flac", "output.flac")
        assert ok is False
        assert any("sample rate divergente" in f for f in failures)

    def test_validation_fail_bit_depth(self) -> None:
        engine = MagicMock(spec=FFmpegEngine)

        def probe_side_effect(path):
            if "original" in str(path):
                return {"streams": [{"codec_type": "audio", "sample_rate": "48000", "bits_per_raw_sample": "24"}], "format": {}}
            return {"streams": [{"codec_type": "audio", "sample_rate": "48000", "bits_per_raw_sample": "16"}], "format": {}}

        engine.probe.side_effect = probe_side_effect
        analyzer = AudioAnalyzer(engine)
        ok, failures = analyzer.validate_lossless_export("original.flac", "output.flac")
        assert ok is False
        assert any("bit-depth divergente" in f for f in failures)

    def test_validation_skips_when_bit_depth_missing(self) -> None:
        """Se um dos arquivos não informa bit-depth, não falha por isso."""
        engine = MagicMock(spec=FFmpegEngine)

        def probe_side_effect(path):
            if "original" in str(path):
                return {"streams": [{"codec_type": "audio", "sample_rate": "48000", "bits_per_raw_sample": "24"}], "format": {}}
            return {"streams": [{"codec_type": "audio", "sample_rate": "48000"}], "format": {}}

        engine.probe.side_effect = probe_side_effect
        analyzer = AudioAnalyzer(engine)
        ok, failures = analyzer.validate_lossless_export("original.flac", "output.flac")
        assert ok is True  # sample rate ok, bit-depth não comparado
        assert failures == []