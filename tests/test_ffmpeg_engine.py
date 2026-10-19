"""Testes de detecção de binários, medições e normalização do FFmpegEngine."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.audio_analyzer import AudioMetrics
from core.exceptions import (
    AudioValidationError,
    FFmpegExecutionError,
    LoudnessAnalysisError,
    UnsupportedAudioFormatError,
)
from core.ffmpeg_engine import (
    BYPASS_TOLERANCE_LU,
    FFmpegEngine,
    LoudnessMetrics,
    should_bypass,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine() -> FFmpegEngine:
    """Cria um engine sem tocar no sistema de arquivos/binários."""
    engine = FFmpegEngine.__new__(FFmpegEngine)
    engine.ffmpeg_path = Path("ffmpeg")
    engine.ffprobe_path = Path("ffprobe")
    return engine


def probe_payload(**overrides) -> dict:
    """Payload mínimo de ffprobe com um stream de áudio estéreo."""
    stream = {
        "codec_type": "audio",
        "codec_name": "pcm_s16le",
        "sample_rate": "44100",
        "bit_rate": "1411200",
        "bits_per_raw_sample": "16",
        "channels": "2",
        "channel_layout": "stereo",
        "sample_fmt": "s16",
    }
    stream.update(overrides)
    return {"streams": [stream], "format": {}}


def loudnorm_report(**overrides) -> str:
    data = {
        "input_i": "-16.32",
        "input_tp": "-2.10",
        "input_lra": "5.00",
        "input_thresh": "-26.32",
        "target_offset": "0.12",
    }
    data.update(overrides)
    return "[Parsed_loudnorm_0 @ 000001] \n" + json.dumps(data, indent="\t")


def fake_run_creates_output(command, **kwargs):
    """Simula o subprocesso criando o arquivo de saída esperado."""
    Path(command[-1]).write_bytes(b"audio-output")
    return MagicMock(stdout="", stderr="", returncode=0)


# ---------------------------------------------------------------------------
# Detecção de binários
# ---------------------------------------------------------------------------

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
        engine = make_engine()
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

    def test_probe_invalid_json_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        dummy_file = tmp_path / "dummy.mp3"
        dummy_file.write_bytes(b"ID3")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="not json", stderr="", returncode=0)
            with pytest.raises(FFmpegExecutionError):
                engine.probe(dummy_file)

    def test_probe_missing_file_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        with pytest.raises(FileNotFoundError):
            engine.probe(tmp_path / "missing.mp3")


class TestFFmpegEngineRun:
    """Tratamento de falhas do subprocesso do FFmpeg."""

    def test_wraps_called_process_error(self) -> None:
        engine = make_engine()
        error = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="boom")
        with patch("subprocess.run", side_effect=error):
            with pytest.raises(FFmpegExecutionError, match="boom"):
                engine._run(["ffmpeg"])

    def test_wraps_missing_binary(self) -> None:
        engine = make_engine()
        with patch("subprocess.run", side_effect=FileNotFoundError("no ffmpeg")):
            with pytest.raises(FFmpegExecutionError):
                engine._run(["ffmpeg"])


# ---------------------------------------------------------------------------
# Medições EBU R128
# ---------------------------------------------------------------------------

class TestFFmpegEngineAnalyzeLoudness:
    """Testa o parser de métricas EBU R128 (ebur128)."""

    def test_parse_standard_output(self, tmp_path: Path) -> None:
        engine = make_engine()
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
        engine = make_engine()
        dummy_file = tmp_path / "dummy.mp3"
        dummy_file.write_bytes(b"ID3")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stderr="no metrics here", stdout="", returncode=0)
            with pytest.raises(RuntimeError):
                engine.analyze_loudness(dummy_file)

    def test_raises_on_infinite_metrics(self, tmp_path: Path) -> None:
        """Áudio silencioso gera -inf e deve ser rejeitado."""
        engine = make_engine()
        dummy_file = tmp_path / "dummy.mp3"
        dummy_file.write_bytes(b"ID3")
        stderr = "I: -inf LUFS\nLRA: 0.0 LU\nThreshold: -inf LUFS\nPeak: -inf dBFS\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stderr=stderr, stdout="", returncode=0)
            with pytest.raises(LoudnessAnalysisError):
                engine.analyze_loudness(dummy_file)

    def test_raises_on_out_of_range_loudness(self, tmp_path: Path) -> None:
        engine = make_engine()
        dummy_file = tmp_path / "dummy.mp3"
        dummy_file.write_bytes(b"ID3")
        stderr = "I: 5.0 LUFS\nLRA: 0.0 LU\nThreshold: -2.0 LUFS\nPeak: 1.0 dBFS\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stderr=stderr, stdout="", returncode=0)
            with pytest.raises(LoudnessAnalysisError):
                engine.analyze_loudness(dummy_file)


class TestFFmpegEngineAnalyzeLoudnorm:
    """Testa o primeiro passe do loudnorm com ``print_format=json``."""

    def test_parses_json_report(self, tmp_path: Path) -> None:
        engine = make_engine()
        dummy_file = tmp_path / "dummy.wav"
        dummy_file.write_bytes(b"RIFF")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stderr=loudnorm_report(), stdout="", returncode=0)
            metrics = engine.analyze_loudnorm(
                dummy_file, target_i=-14.0, target_tp=-1.0, target_lra=11.0
            )

        assert metrics.input_i == pytest.approx(-16.32)
        assert metrics.input_tp == pytest.approx(-2.10)
        assert metrics.input_lra == pytest.approx(5.0)
        assert metrics.input_thresh == pytest.approx(-26.32)
        assert metrics.target_offset == pytest.approx(0.12)

        called = mock_run.call_args[0][0]
        joined = " ".join(called)
        assert "print_format=json" in joined
        assert "loudnorm=I=-14.0:TP=-1.0:LRA=11.0" in joined
        assert "-f null" in joined

    def test_uses_last_json_block(self, tmp_path: Path) -> None:
        engine = make_engine()
        dummy_file = tmp_path / "dummy.wav"
        dummy_file.write_bytes(b"RIFF")
        first = loudnorm_report(input_i="-30.00")
        second = loudnorm_report(input_i="-16.50")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stderr=first + "\n" + second, stdout="", returncode=0
            )
            metrics = engine.analyze_loudnorm(
                dummy_file, target_i=-14.0, target_tp=-1.0, target_lra=11.0
            )
        assert metrics.input_i == pytest.approx(-16.50)

    def test_missing_key_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        dummy_file = tmp_path / "dummy.wav"
        dummy_file.write_bytes(b"RIFF")
        report = loudnorm_report()
        data = json.loads(report.split("\n", 1)[1])
        del data["input_thresh"]
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stderr=json.dumps(data), stdout="", returncode=0)
            with pytest.raises(LoudnessAnalysisError, match="input_thresh"):
                engine.analyze_loudnorm(dummy_file, target_i=-14.0, target_tp=-1.0, target_lra=11.0)

    def test_non_finite_value_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        dummy_file = tmp_path / "dummy.wav"
        dummy_file.write_bytes(b"RIFF")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stderr=loudnorm_report(input_i="-inf"), stdout="", returncode=0
            )
            with pytest.raises(LoudnessAnalysisError):
                engine.analyze_loudnorm(dummy_file, target_i=-14.0, target_tp=-1.0, target_lra=11.0)

    def test_invalid_offset_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        dummy_file = tmp_path / "dummy.wav"
        dummy_file.write_bytes(b"RIFF")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stderr=loudnorm_report(target_offset="abc"), stdout="", returncode=0
            )
            with pytest.raises(LoudnessAnalysisError, match="target_offset"):
                engine.analyze_loudnorm(dummy_file, target_i=-14.0, target_tp=-1.0, target_lra=11.0)

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        dummy_file = tmp_path / "dummy.wav"
        dummy_file.write_bytes(b"RIFF")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stderr='{"input_i": }', stdout="", returncode=0)
            with pytest.raises(LoudnessAnalysisError):
                engine.analyze_loudnorm(dummy_file, target_i=-14.0, target_tp=-1.0, target_lra=11.0)

    def test_no_json_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        dummy_file = tmp_path / "dummy.wav"
        dummy_file.write_bytes(b"RIFF")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stderr="sem relatorio", stdout="", returncode=0)
            with pytest.raises(LoudnessAnalysisError):
                engine.analyze_loudnorm(dummy_file, target_i=-14.0, target_tp=-1.0, target_lra=11.0)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"target_i": -3.0, "target_tp": -1.0, "target_lra": 11.0},
            {"target_i": -14.0, "target_tp": -12.0, "target_lra": 11.0},
            {"target_i": -14.0, "target_tp": -1.0, "target_lra": 0.0},
        ],
    )
    def test_rejects_targets_outside_loudnorm_range(self, tmp_path: Path, kwargs: dict) -> None:
        engine = make_engine()
        dummy_file = tmp_path / "dummy.wav"
        dummy_file.write_bytes(b"RIFF")
        with pytest.raises(ValueError):
            engine.analyze_loudnorm(dummy_file, **kwargs)


# ---------------------------------------------------------------------------
# Decisão de bypass
# ---------------------------------------------------------------------------

class TestBypassDecision:
    """Bypass deve respeitar os alvos configurados pelo usuário."""

    def test_default_targets_bypass(self) -> None:
        metrics = LoudnessMetrics(-14.0, -1.5, 5.0, -24.0)
        assert should_bypass(metrics, target_i=-14.0, target_tp=-1.0) is True

    def test_custom_target_changes_decision(self) -> None:
        metrics = LoudnessMetrics(-14.0, -1.5, 5.0, -24.0)
        assert should_bypass(metrics, target_i=-11.0, target_tp=-1.0) is False

    def test_true_peak_above_target_blocks_bypass(self) -> None:
        metrics = LoudnessMetrics(-14.0, -0.5, 5.0, -24.0)
        assert should_bypass(metrics, target_i=-14.0, target_tp=-1.0) is False

    def test_tolerance_boundaries(self) -> None:
        inside = LoudnessMetrics(-14.0 + BYPASS_TOLERANCE_LU, -1.0, 5.0, -24.0)
        outside = LoudnessMetrics(-14.0 + BYPASS_TOLERANCE_LU + 0.01, -1.0, 5.0, -24.0)
        assert should_bypass(inside, target_i=-14.0, target_tp=-1.0) is True
        assert should_bypass(outside, target_i=-14.0, target_tp=-1.0) is False

    def test_different_container_blocks_bypass(self) -> None:
        metrics = LoudnessMetrics(-14.0, -1.5, 5.0, -24.0)
        assert should_bypass(
            metrics, target_i=-14.0, target_tp=-1.0, same_container=False
        ) is False


# ---------------------------------------------------------------------------
# Construção de comandos e codecs
# ---------------------------------------------------------------------------

class TestNormalizationCommandBuilding:
    """Verifica o comando gerado conforme alvos, formato e propriedades fonte."""

    def _run_normalize(self, tmp_path: Path, *, source_name: str, dest_name: str,
                       metrics: LoudnessMetrics, payload: dict, generated_payload: dict | None = None,
                       **targets):
        engine = make_engine()
        source = tmp_path / source_name
        dest = tmp_path / dest_name
        source.write_bytes(b"RIFF")
        if generated_payload is None:
            probe_mock = patch.object(engine, "probe", return_value=payload)
        else:
            def side_effect(path):
                return generated_payload if ".part" in str(path) else payload

            probe_mock = patch.object(engine, "probe", side_effect=side_effect)
        with patch.object(engine, "analyze_loudnorm", return_value=metrics), \
             probe_mock, \
             patch("subprocess.run", side_effect=fake_run_creates_output) as mock_run, \
             patch("core.metadata_handler.MetadataHandler.copy_all"):
            result = engine.normalize(source, dest, **targets)
        return result, mock_run, dest

    def test_mp3_command_preserves_rate_and_channels(self, tmp_path: Path) -> None:
        metrics = LoudnessMetrics(-20.0, -3.0, 5.0, -30.0)
        result, mock_run, _ = self._run_normalize(
            tmp_path, source_name="src.mp3", dest_name="dst.mp3",
            metrics=metrics, payload=probe_payload(codec_name="mp3", sample_fmt="fltp", bit_rate="320000"),
        )
        assert result.status == "normalized"
        command = mock_run.call_args[0][0]
        joined = " ".join(command)
        assert "libmp3lame" in command
        assert "320k" in command
        assert "-ar 44100" in joined
        assert "-ac 2" in joined
        assert "-channel_layout stereo" in joined
        assert "measured_I=-20.000000" in joined
        assert "offset=" in joined

    def test_custom_targets_are_applied(self, tmp_path: Path) -> None:
        metrics = LoudnessMetrics(-18.0, -2.5, 8.0, -28.0)
        result, mock_run, _ = self._run_normalize(
            tmp_path, source_name="src.mp3", dest_name="dst.mp3",
            metrics=metrics, payload=probe_payload(codec_name="mp3", sample_fmt="fltp"),
            target_i=-11.0, target_tp=-0.5, target_lra=10.0,
        )
        assert result.status == "normalized"
        joined = " ".join(mock_run.call_args[0][0])
        assert "loudnorm=I=-11.0:TP=-0.5:LRA=10.0" in joined

    def test_custom_target_enables_bypass(self, tmp_path: Path) -> None:
        metrics = LoudnessMetrics(-11.0, -1.2, 5.0, -21.0)
        result, mock_run, _ = self._run_normalize(
            tmp_path, source_name="src.mp3", dest_name="dst.mp3",
            metrics=metrics, payload=probe_payload(codec_name="mp3", sample_fmt="fltp"),
            target_i=-11.0, target_tp=-1.0, target_lra=11.0,
        )
        assert result.status == "bypass"
        command = mock_run.call_args[0][0]
        assert "-c" in command and "copy" in command
        assert result.normalization_type == "bypass"

    def test_dynamic_normalization_when_gain_would_break_true_peak(self, tmp_path: Path) -> None:
        metrics = LoudnessMetrics(-30.0, -1.0, 5.0, -40.0)
        result, mock_run, _ = self._run_normalize(
            tmp_path, source_name="src.wav", dest_name="out.wav",
            metrics=metrics, payload=probe_payload(),
            target_i=-14.0, target_tp=-1.5, target_lra=11.0,
        )
        joined = " ".join(mock_run.call_args[0][0])
        assert result.normalization_type == "dynamic"
        assert "linear=false" in joined

    def test_linear_normalization_when_feasible(self, tmp_path: Path) -> None:
        metrics = LoudnessMetrics(-20.0, -25.0, 4.0, -30.0)
        result, mock_run, _ = self._run_normalize(
            tmp_path, source_name="src.wav", dest_name="out.wav",
            metrics=metrics, payload=probe_payload(),
            target_i=-14.0, target_tp=-1.0, target_lra=11.0,
        )
        joined = " ".join(mock_run.call_args[0][0])
        assert result.normalization_type == "linear"
        assert "linear=true" in joined

    def test_dynamic_when_input_lra_exceeds_target(self, tmp_path: Path) -> None:
        metrics = LoudnessMetrics(-20.0, -25.0, 15.0, -30.0)
        result, mock_run, _ = self._run_normalize(
            tmp_path, source_name="src.wav", dest_name="out.wav",
            metrics=metrics, payload=probe_payload(),
            target_i=-14.0, target_tp=-1.0, target_lra=11.0,
        )
        assert result.normalization_type == "dynamic"
        assert "linear=false" in " ".join(mock_run.call_args[0][0])

    def test_second_pass_report_overrides_prediction(self, tmp_path: Path) -> None:
        engine = make_engine()
        source = tmp_path / "src.wav"
        dest = tmp_path / "out.wav"
        source.write_bytes(b"RIFF")
        metrics = LoudnessMetrics(-20.0, -25.0, 4.0, -30.0)

        def run(command, **kwargs):
            Path(command[-1]).write_bytes(b"audio")
            return MagicMock(
                stdout="",
                stderr=json.dumps({"normalization_type": "dynamic"}),
                returncode=0,
            )

        with patch.object(engine, "analyze_loudnorm", return_value=metrics), \
             patch.object(engine, "probe", return_value=probe_payload()), \
             patch("subprocess.run", side_effect=run), \
             patch("core.metadata_handler.MetadataHandler.copy_all"):
            result = engine.normalize(source, dest)

        assert result.normalization_type == "dynamic"

    @pytest.mark.parametrize(
        "payload, expected_codec",
        [
            (probe_payload(codec_name="pcm_s16le", bits_per_raw_sample="16", sample_fmt="s16"), "pcm_s16le"),
            (probe_payload(codec_name="pcm_s24le", bits_per_raw_sample="24", sample_fmt="s32"), "pcm_s24le"),
            (probe_payload(codec_name="pcm_s32le", bits_per_raw_sample="32", sample_fmt="s32"), "pcm_s32le"),
            (probe_payload(codec_name="pcm_f32le", bits_per_raw_sample="32", sample_fmt="flt"), "pcm_f32le"),
        ],
    )
    def test_wav_codec_selection(self, tmp_path: Path, payload: dict, expected_codec: str) -> None:
        metrics = LoudnessMetrics(-20.0, -3.0, 5.0, -30.0)
        result, mock_run, _ = self._run_normalize(
            tmp_path, source_name="src.wav", dest_name="out.wav",
            metrics=metrics, payload=payload,
        )
        assert result.status == "normalized"
        command = mock_run.call_args[0][0]
        assert command[command.index("-c:a") + 1] == expected_codec

    def test_flac_24_bits_uses_s32_with_depth(self, tmp_path: Path) -> None:
        metrics = LoudnessMetrics(-20.0, -3.0, 5.0, -30.0)
        _, mock_run, _ = self._run_normalize(
            tmp_path, source_name="src.wav", dest_name="out.flac",
            metrics=metrics,
            payload=probe_payload(codec_name="pcm_s24le", bits_per_raw_sample="24", sample_fmt="s32"),
        )
        command = mock_run.call_args[0][0]
        assert command[command.index("-sample_fmt") + 1] == "s32"
        assert command[command.index("-bits_per_raw_sample") + 1] == "24"

    def test_flac_16_bits_uses_s16(self, tmp_path: Path) -> None:
        metrics = LoudnessMetrics(-20.0, -3.0, 5.0, -30.0)
        _, mock_run, _ = self._run_normalize(
            tmp_path, source_name="src.wav", dest_name="out.flac",
            metrics=metrics,
            payload=probe_payload(codec_name="pcm_s16le", bits_per_raw_sample="16", sample_fmt="s16"),
        )
        command = mock_run.call_args[0][0]
        assert command[command.index("-sample_fmt") + 1] == "s16"
        assert command[command.index("-bits_per_raw_sample") + 1] == "16"

    def test_flac_from_32bit_source_warns_about_cap(self, tmp_path: Path) -> None:
        metrics = LoudnessMetrics(-20.0, -3.0, 5.0, -30.0)
        result, _, _ = self._run_normalize(
            tmp_path, source_name="src.wav", dest_name="out.flac",
            metrics=metrics,
            payload=probe_payload(codec_name="pcm_s32le", bits_per_raw_sample="32", sample_fmt="s32"),
            generated_payload=probe_payload(
                codec_name="flac", bits_per_raw_sample="24", sample_fmt="s32"
            ),
        )
        assert any("24 bits" in warning for warning in result.warnings)

    def test_mp3_downmix_warns_and_limits_channels(self, tmp_path: Path) -> None:
        metrics = LoudnessMetrics(-20.0, -3.0, 5.0, -30.0)
        result, mock_run, _ = self._run_normalize(
            tmp_path, source_name="src.wav", dest_name="out.mp3",
            metrics=metrics,
            payload=probe_payload(codec_name="pcm_s16le", channels="6", channel_layout="5.1"),
            generated_payload=probe_payload(codec_name="mp3", sample_fmt="fltp"),
        )
        command = mock_run.call_args[0][0]
        assert command[command.index("-ac") + 1] == "2"
        assert any("estéreo" in warning for warning in result.warnings)

    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        source = tmp_path / "src.wav"
        source.write_bytes(b"RIFF")
        with pytest.raises(UnsupportedAudioFormatError):
            engine.normalize(source, tmp_path / "out.ogg")

    def test_invalid_target_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        source = tmp_path / "src.wav"
        source.write_bytes(b"RIFF")
        with pytest.raises(ValueError):
            engine.normalize(source, tmp_path / "out.wav", target_tp=-15.0)


class TestWavCodecHelpers:
    """Seleção de codecs WAV a partir das métricas inspecionadas."""

    @pytest.mark.parametrize(
        "metrics, expected",
        [
            (AudioMetrics(44100, None, 16, "pcm_s16le", 2, sample_fmt="s16"), "pcm_s16le"),
            (AudioMetrics(48000, None, 24, "pcm_s24le", 2, sample_fmt="s32"), "pcm_s24le"),
            (AudioMetrics(48000, None, 32, "pcm_s32le", 2, sample_fmt="s32"), "pcm_s32le"),
            (AudioMetrics(48000, None, 32, "pcm_f32le", 2, sample_fmt="flt"), "pcm_f32le"),
            (AudioMetrics(48000, None, 64, "pcm_f64le", 2, sample_fmt="dbl"), "pcm_f64le"),
            (AudioMetrics(48000, None, 24, "flac", 2, sample_fmt="s32"), "pcm_s24le"),
            (AudioMetrics(44100, None, 16, "flac", 2, sample_fmt="s16"), "pcm_s16le"),
            (AudioMetrics(44100, 320000, None, "mp3", 2, sample_fmt="fltp"), "pcm_s16le"),
        ],
    )
    def test_select_wav_codec(self, metrics: AudioMetrics, expected: str) -> None:
        assert FFmpegEngine._select_wav_codec(metrics) == expected

    @pytest.mark.parametrize(
        "metrics, expected_depth",
        [
            (AudioMetrics(44100, None, 16, "pcm_s16le", 2), 16),
            (AudioMetrics(48000, None, 24, "pcm_s24le", 2), 24),
            (AudioMetrics(48000, None, 32, "pcm_s32le", 2), 24),
            (AudioMetrics(48000, None, 32, "pcm_f32le", 2, sample_fmt="flt"), 24),
        ],
    )
    def test_select_flac_bit_depth(self, metrics: AudioMetrics, expected_depth: int) -> None:
        assert FFmpegEngine._select_flac_bit_depth(metrics) == expected_depth


# ---------------------------------------------------------------------------
# Integridade, metadados e erros
# ---------------------------------------------------------------------------

class TestNormalizationIntegrity:
    """Garantias de atomicidade, validação e metadados não críticos."""

    def _prepare(self, tmp_path: Path, dest_name: str = "out.wav"):
        engine = make_engine()
        source = tmp_path / "src.wav"
        source.write_bytes(b"RIFF")
        dest = tmp_path / dest_name
        metrics = LoudnessMetrics(-20.0, -3.0, 5.0, -30.0)
        return engine, source, dest, metrics

    def test_ffmpeg_failure_leaves_no_temp_and_no_output(self, tmp_path: Path) -> None:
        engine, source, dest, metrics = self._prepare(tmp_path)
        error = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="boom")
        with patch.object(engine, "analyze_loudnorm", return_value=metrics), \
             patch.object(engine, "probe", return_value=probe_payload()), \
             patch("subprocess.run", side_effect=error):
            with pytest.raises(FFmpegExecutionError):
                engine.normalize(source, dest)
        assert not dest.exists()
        assert list(tmp_path.glob("*.part*")) == []

    def test_failure_preserves_existing_destination(self, tmp_path: Path) -> None:
        engine, source, dest, metrics = self._prepare(tmp_path)
        dest.write_bytes(b"ORIGINAL")
        error = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="boom")
        with patch.object(engine, "analyze_loudnorm", return_value=metrics), \
             patch.object(engine, "probe", return_value=probe_payload()), \
             patch("subprocess.run", side_effect=error):
            with pytest.raises(FFmpegExecutionError):
                engine.normalize(source, dest)
        assert dest.read_bytes() == b"ORIGINAL"

    def test_validation_failure_discards_temp_and_keeps_destination(self, tmp_path: Path) -> None:
        engine, source, dest, metrics = self._prepare(tmp_path)
        dest.write_bytes(b"ORIGINAL")
        with patch.object(engine, "analyze_loudnorm", return_value=metrics), \
             patch.object(engine, "probe", return_value=probe_payload()), \
             patch("subprocess.run", side_effect=fake_run_creates_output), \
             patch("core.metadata_handler.MetadataHandler.copy_all"), \
             patch(
                 "core.audio_analyzer.AudioAnalyzer.validate_export",
                 return_value=(False, ["sample rate divergente (48000 != 44100)"]),
             ):
            with pytest.raises(AudioValidationError):
                engine.normalize(source, dest)
        assert dest.read_bytes() == b"ORIGINAL"
        assert list(tmp_path.glob("*.part*")) == []

    def test_metadata_failure_is_non_critical(self, tmp_path: Path) -> None:
        engine, source, dest, metrics = self._prepare(tmp_path)
        with patch.object(engine, "analyze_loudnorm", return_value=metrics), \
             patch.object(engine, "probe", return_value=probe_payload()), \
             patch("subprocess.run", side_effect=fake_run_creates_output), \
             patch("core.metadata_handler.MetadataHandler.copy_all", side_effect=RuntimeError("tags")):
            result = engine.normalize(source, dest)
        assert result.status == "normalized"
        assert result.metadata_preserved is False
        assert any("metadados" in warning for warning in result.warnings)
        assert dest.exists()

    def test_bypass_also_reports_metadata_failure(self, tmp_path: Path) -> None:
        engine = make_engine()
        source = tmp_path / "src.mp3"
        source.write_bytes(b"ID3")
        dest = tmp_path / "out.mp3"
        metrics = LoudnessMetrics(-14.0, -1.5, 5.0, -24.0)
        with patch.object(engine, "analyze_loudnorm", return_value=metrics), \
             patch.object(engine, "probe", return_value=probe_payload(codec_name="mp3", sample_fmt="fltp")), \
             patch("subprocess.run", side_effect=fake_run_creates_output), \
             patch("core.metadata_handler.MetadataHandler.copy_all", side_effect=RuntimeError("tags")):
            result = engine.normalize(source, dest)
        assert result.status == "bypass"
        assert result.metadata_preserved is False
        assert result.warnings

    def test_missing_source_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        with pytest.raises(FileNotFoundError):
            engine.normalize(tmp_path / "missing.wav", tmp_path / "out.wav")

    def test_empty_source_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        source = tmp_path / "empty.wav"
        source.write_bytes(b"")
        with pytest.raises(ValueError):
            engine.normalize(source, tmp_path / "out.wav")

    def test_same_source_and_destination_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        source = tmp_path / "src.wav"
        source.write_bytes(b"RIFF")
        with pytest.raises(ValueError):
            engine.normalize(source, source)

    def test_no_audio_stream_raises(self, tmp_path: Path) -> None:
        engine = make_engine()
        source = tmp_path / "src.mp4"
        source.write_bytes(b"\x00\x00")
        with patch.object(
            engine, "probe", return_value={"streams": [{"codec_type": "video"}], "format": {}}
        ):
            with pytest.raises(ValueError, match="Nenhum stream de áudio"):
                engine.normalize(source, tmp_path / "out.mp3")

    def test_validation_always_reports_properties(self, tmp_path: Path) -> None:
        engine = make_engine()
        source = tmp_path / "src.mp3"
        source.write_bytes(b"ID3")
        dest = tmp_path / "out.mp3"
        metrics = LoudnessMetrics(-20.0, -3.0, 5.0, -30.0)
        with patch.object(engine, "analyze_loudnorm", return_value=metrics), \
             patch.object(engine, "probe", return_value=probe_payload(codec_name="mp3", sample_fmt="fltp")), \
             patch("subprocess.run", side_effect=fake_run_creates_output), \
             patch("core.metadata_handler.MetadataHandler.copy_all"):
            result = engine.normalize(source, dest)
        assert result.post_validation is not None
        assert result.post_validation[0] is True
