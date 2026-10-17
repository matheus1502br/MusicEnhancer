"""Testes de detecção de binários e execução de comandos do FFmpegEngine."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.ffmpeg_engine import FFmpegEngine, LoudnessMetrics


class TestFFmpegEngineBinaryDetection:
    """Verifica se o engine localiza ffmpeg/ffprobe corretamente."""

    def test_finds_binaries_in_utils_bin(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "utils" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "ffmpeg.exe").write_bytes(b"MZ")
        (bin_dir / "ffprobe.exe").write_bytes(b"MZ")

        with patch.object(Path, "resolve", return_value=tmp_path / "core" / "ffmpeg_engine.py"):
            engine = FFmpegEngine()

        assert engine.ffmpeg_path == bin_dir / "ffmpeg.exe"
        assert engine.ffprobe_path == bin_dir / "ffprobe.exe"

    def test_fallback_to_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Quando não há binários em utils/bin, deve usar o PATH."""
        # Garante que utils/bin não existe
        utils_bin = tmp_path / "utils" / "bin"
        if utils_bin.exists():
            import shutil
            shutil.rmtree(utils_bin)

        # Criar executáveis com o nome que o shutil.which espera
        fake_ffmpeg = tmp_path / "ffmpeg.exe"
        fake_ffprobe = tmp_path / "ffprobe.exe"
        fake_ffmpeg.write_bytes(b"MZ")
        fake_ffprobe.write_bytes(b"MZ")

        monkeypatch.setenv("PATH", str(tmp_path) + ";" + os.environ.get("PATH", ""))

        with patch.object(Path, "resolve", return_value=tmp_path / "core" / "ffmpeg_engine.py"):
            engine = FFmpegEngine()

        assert engine.ffmpeg_path.name.lower() == "ffmpeg.exe"
        assert engine.ffprobe_path.name.lower() == "ffprobe.exe"

    def test_raises_when_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Deve lançar FileNotFoundError se não encontrar em nenhum lugar."""
        monkeypatch.setenv("PATH", str(tmp_path))
        with patch.object(Path, "resolve", return_value=tmp_path / "core" / "ffmpeg_engine.py"):
            with pytest.raises(FileNotFoundError):
                FFmpegEngine()


class TestFFmpegEngineProbe:
    """Testa o wrapper de ffprobe."""

    def test_probe_returns_json(self, tmp_path: Path) -> None:
        engine = FFmpegEngine.__new__(FFmpegEngine)
        engine.ffprobe_path = Path("ffprobe")
        dummy_file = tmp_path / "dummy.mp3"
        dummy_file.write_bytes(b"ID3")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout='{"streams": [{"codec_type": "audio", "sample_rate": "44100"}], "format": {}}',
                stderr="",
                returncode=0,
            )
            data = engine.probe(dummy_file)
            assert data["streams"][0]["sample_rate"] == "44100"


class TestFFmpegEngineAnalyzeLoudness:
    """Testa o parser de métricas EBU R128."""

    def test_parse_standard_output(self, tmp_path: Path) -> None:
        engine = FFmpegEngine.__new__(FFmpegEngine)
        engine.ffmpeg_path = Path("ffmpeg")
        dummy_file = tmp_path / "dummy.mp3"
        dummy_file.write_bytes(b"ID3")
        sample_stderr = """
        [Parsed_ebur128_0 @ 000001] t: -16.5 LUFS
        [Parsed_ebur128_0 @ 000001] I: -16.5 LUFS
        [Parsed_ebur128_0 @ 000001] LRA: 5.0 LU
        [Parsed_ebur128_0 @ 000001] Threshold: -26.5 LUFS
        [Parsed_ebur128_0 @ 000001] Peak: -2.0 dBFS
        """
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stderr=sample_stderr, stdout="", returncode=0)
            metrics = engine.analyze_loudness(dummy_file)

        assert isinstance(metrics, LoudnessMetrics)
        assert metrics.input_i == -16.5
        assert metrics.input_tp == -2.0
        assert metrics.input_lra == 5.0
        assert metrics.input_thresh == -26.5

    def test_raises_on_missing_metrics(self, tmp_path: Path) -> None:
        engine = FFmpegEngine.__new__(FFmpegEngine)
        engine.ffmpeg_path = Path("ffmpeg")
        dummy_file = tmp_path / "dummy.mp3"
        dummy_file.write_bytes(b"ID3")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stderr="no metrics here", stdout="", returncode=0)
            with pytest.raises(RuntimeError):
                engine.analyze_loudness(dummy_file)


class TestFFmpegEngineNormalize:
    """Testa decisões de bypass vs normalização."""

    def test_bypass_decision(self, tmp_path: Path) -> None:
        engine = FFmpegEngine.__new__(FFmpegEngine)
        engine.ffmpeg_path = Path("ffmpeg")
        engine.ffprobe_path = Path("ffprobe")

        source = tmp_path / "src.mp3"
        dest = tmp_path / "dst.mp3"
        source.write_bytes(b"ID3")

        # Métricas dentro da faixa de bypass
        metrics = LoudnessMetrics(input_i=-14.0, input_tp=-1.5, input_lra=5.0, input_thresh=-24.0)

        with patch.object(engine, "analyze_loudness", return_value=metrics), \
             patch.object(engine, "probe", return_value={"streams": [{"codec_type": "audio", "sample_rate": "44100", "bit_rate": "256000", "bits_per_raw_sample": "16"}], "format": {}}), \
             patch("subprocess.run") as mock_run, \
             patch("core.metadata_handler.MetadataHandler.copy_all") as mock_copy:

            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            result = engine.normalize(source, dest)

        assert result.status == "bypass"
        # Verifica se comando de cópia foi chamado
        called_cmd = mock_run.call_args[0][0]
        assert "-c" in called_cmd and "copy" in called_cmd
        mock_copy.assert_called_once()

    def test_normalize_command_building_mp3(self, tmp_path: Path) -> None:
        engine = FFmpegEngine.__new__(FFmpegEngine)
        engine.ffmpeg_path = Path("ffmpeg")
        engine.ffprobe_path = Path("ffprobe")

        source = tmp_path / "src.mp3"
        dest = tmp_path / "dst.mp3"
        source.write_bytes(b"ID3")

        metrics = LoudnessMetrics(input_i=-20.0, input_tp=-3.0, input_lra=8.0, input_thresh=-30.0)

        with patch.object(engine, "analyze_loudness", return_value=metrics), \
             patch.object(engine, "probe", return_value={"streams": [{"codec_type": "audio", "sample_rate": "44100", "bit_rate": "320000", "bits_per_raw_sample": "16"}], "format": {}}), \
             patch("subprocess.run") as mock_run, \
             patch("core.metadata_handler.MetadataHandler.copy_all"):

            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            result = engine.normalize(source, dest)

        assert result.status == "normalized"
        called_cmd = mock_run.call_args[0][0]
        assert "loudnorm" in " ".join(called_cmd)
        assert "libmp3lame" in called_cmd
        assert "320k" in called_cmd  # bitrate clamp max 320k

    def test_normalize_custom_target_i_and_tp(self, tmp_path: Path) -> None:
        engine = FFmpegEngine.__new__(FFmpegEngine)
        engine.ffmpeg_path = Path("ffmpeg")
        engine.ffprobe_path = Path("ffprobe")

        source = tmp_path / "src.mp3"
        dest = tmp_path / "dst.mp3"
        source.write_bytes(b"ID3")

        metrics = LoudnessMetrics(input_i=-18.0, input_tp=-2.5, input_lra=8.0, input_thresh=-28.0)

        with patch.object(engine, "analyze_loudness", return_value=metrics), \
             patch.object(engine, "probe", return_value={"streams": [{"codec_type": "audio", "sample_rate": "44100", "bit_rate": "256000", "bits_per_raw_sample": "16"}], "format": {}}), \
             patch("subprocess.run") as mock_run, \
             patch("core.metadata_handler.MetadataHandler.copy_all"):

            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            result = engine.normalize(source, dest, target_i=-11.0, target_tp=-0.5, target_lra=10.0)

        assert result.status == "normalized"
        called_cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(called_cmd)
        assert "loudnorm=I=-11.0:TP=-0.5:LRA=10.0" in cmd_str

    def test_bypass_requires_matching_container(self, tmp_path: Path) -> None:
        """Mesmo com loudness dentro da faixa, extensão diferente impede stream copy."""
        engine = FFmpegEngine.__new__(FFmpegEngine)
        engine.ffmpeg_path = Path("ffmpeg")
        engine.ffprobe_path = Path("ffprobe")

        source = tmp_path / "src.wav"
        dest = tmp_path / "dst.mp3"
        source.write_bytes(b"RIFF")

        metrics = LoudnessMetrics(input_i=-14.0, input_tp=-1.5, input_lra=5.0, input_thresh=-24.0)

        with patch.object(engine, "analyze_loudness", return_value=metrics), \
             patch.object(engine, "probe", return_value={"streams": [{"codec_type": "audio", "sample_rate": "44100", "bit_rate": "1411200", "bits_per_raw_sample": "16"}], "format": {}}), \
             patch("subprocess.run") as mock_run, \
             patch("core.metadata_handler.MetadataHandler.copy_all"):

            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            result = engine.normalize(source, dest)

        # Não deve ser bypass porque WAV -> MP3 exige transcodificação
        assert result.status == "normalized"
        called_cmd = mock_run.call_args[0][0]
        assert "libmp3lame" in called_cmd

    def test_audio_bitrate_lossless_source_320k(self) -> None:
        """Fontes com bitrate > 1000k (ex: WAV 1411k) devem receber 320k em MP3."""
        assert FFmpegEngine._audio_bitrate(1411200) == "320k"
        assert FFmpegEngine._audio_bitrate(256000) == "256k"
        assert FFmpegEngine._audio_bitrate(128000) == "192k"  # clamp min 192k