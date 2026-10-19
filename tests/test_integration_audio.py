"""Testes de integração com arquivos sintéticos gerados localmente pelo FFmpeg.

Não dependem de internet nem de músicas pessoais. São ignorados quando o
FFmpeg não está disponível no ambiente.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from core.audio_analyzer import AudioAnalyzer
from core.exceptions import AudioProcessingError, LoudnessAnalysisError
from core.ffmpeg_engine import FFmpegEngine


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None and not Path("utils/bin/ffmpeg.exe").is_file(),
    reason="FFmpeg não está disponível para os testes de integração",
)


@pytest.fixture(scope="module")
def engine() -> FFmpegEngine:
    return FFmpegEngine()


def generate_sine(
    engine: FFmpegEngine,
    destination: Path,
    *,
    codec: str,
    sample_rate: int = 48000,
    channels: int = 2,
    duration: float = 0.6,
    metadata: dict[str, str] | None = None,
) -> Path:
    command = [
        str(engine.ffmpeg_path), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}:sample_rate={sample_rate}",
        "-ac", str(channels), "-c:a", codec,
    ]
    for key, value in (metadata or {}).items():
        command += ["-metadata", f"{key}={value}"]
    command.append(str(destination))
    subprocess.run(command, check=True, capture_output=True)
    return destination


def inspect(engine: FFmpegEngine, path: Path):
    return AudioAnalyzer(engine).inspect(path)


class TestRealNormalizationProperties:
    """Confere as propriedades reais dos arquivos exportados."""

    def test_preserves_24bit_wav(self, engine: FFmpegEngine, tmp_path: Path) -> None:
        source = generate_sine(engine, tmp_path / "src24.wav", codec="pcm_s24le")
        destination = tmp_path / "out24.wav"

        result = engine.normalize(
            source, destination, target_i=-16.0, target_tp=-2.0, target_lra=11.0
        )

        assert result.status == "normalized"
        info = inspect(engine, destination)
        assert info.codec_name == "pcm_s24le"
        assert info.sample_rate == 48000
        assert info.channels == 2
        assert info.bits_per_raw_sample == 24
        assert list(tmp_path.glob("*.part*")) == []

    def test_preserves_32bit_integer_wav(self, engine: FFmpegEngine, tmp_path: Path) -> None:
        source = generate_sine(engine, tmp_path / "src32.wav", codec="pcm_s32le")
        destination = tmp_path / "out32.wav"

        engine.normalize(source, destination, target_i=-16.0, target_tp=-2.0)

        info = inspect(engine, destination)
        assert info.codec_name == "pcm_s32le"
        assert info.bits_per_raw_sample == 32

    def test_preserves_32bit_float_wav(self, engine: FFmpegEngine, tmp_path: Path) -> None:
        source = generate_sine(engine, tmp_path / "srcf32.wav", codec="pcm_f32le")
        destination = tmp_path / "outf32.wav"

        engine.normalize(source, destination, target_i=-16.0, target_tp=-2.0)

        info = inspect(engine, destination)
        assert info.codec_name == "pcm_f32le"
        assert info.sample_rate == 48000

    def test_preserves_16bit_wav_to_flac(self, engine: FFmpegEngine, tmp_path: Path) -> None:
        source = generate_sine(engine, tmp_path / "src16.wav", codec="pcm_s16le")
        destination = tmp_path / "out16.flac"

        engine.normalize(source, destination, target_i=-16.0, target_tp=-2.0)

        info = inspect(engine, destination)
        assert info.codec_name == "flac"
        assert info.bits_per_raw_sample == 16
        assert info.channels == 2

    def test_preserves_24bit_wav_to_flac(self, engine: FFmpegEngine, tmp_path: Path) -> None:
        source = generate_sine(engine, tmp_path / "src24.wav", codec="pcm_s24le")
        destination = tmp_path / "out24.flac"

        engine.normalize(source, destination, target_i=-16.0, target_tp=-2.0)

        info = inspect(engine, destination)
        assert info.codec_name == "flac"
        assert info.bits_per_raw_sample == 24

    def test_preserves_sample_rate_and_channels(self, engine: FFmpegEngine, tmp_path: Path) -> None:
        source = generate_sine(
            engine, tmp_path / "src_mono.wav", codec="pcm_s16le", sample_rate=44100, channels=1
        )
        destination = tmp_path / "out_mono.flac"

        engine.normalize(source, destination, target_i=-16.0, target_tp=-2.0)

        info = inspect(engine, destination)
        assert info.sample_rate == 44100
        assert info.channels == 1

    def test_output_loudness_matches_custom_target(self, engine: FFmpegEngine, tmp_path: Path) -> None:
        source = generate_sine(engine, tmp_path / "src.wav", codec="pcm_s16le")
        destination = tmp_path / "out.wav"

        result = engine.normalize(
            source, destination, target_i=-18.0, target_tp=-2.0, target_lra=11.0
        )

        measured = engine.analyze_loudness(destination)
        assert abs(measured.input_i - (-18.0)) <= 1.0
        assert measured.input_tp <= -2.0 + 0.5
        assert result.normalization_type in {"linear", "dynamic"}

    def test_bypass_copies_without_reencoding(self, engine: FFmpegEngine, tmp_path: Path) -> None:
        source = generate_sine(engine, tmp_path / "src.wav", codec="pcm_s16le")
        measured = engine.analyze_loudnorm(
            source, target_i=-16.0, target_tp=-2.0, target_lra=11.0
        )
        destination = tmp_path / "copy.wav"

        result = engine.normalize(
            source,
            destination,
            target_i=measured.input_i,
            target_tp=-1.0,
            target_lra=11.0,
        )

        assert result.status == "bypass"
        assert destination.is_file()
        info = inspect(engine, destination)
        assert info.sample_rate == 48000
        assert info.channels == 2


class TestRealMetadataAndErrors:
    """Metadados reais e tratamento de arquivos inválidos."""

    def test_preserves_flac_tags(self, engine: FFmpegEngine, tmp_path: Path) -> None:
        mutagen = pytest.importorskip("mutagen")
        source = generate_sine(
            engine,
            tmp_path / "tagged.flac",
            codec="flac",
            metadata={"title": "Titulo Teste", "artist": "Artista Teste"},
        )
        destination = tmp_path / "tagged_out.flac"

        result = engine.normalize(source, destination, target_i=-16.0, target_tp=-2.0)

        assert result.metadata_preserved is True
        audio = mutagen.File(destination)
        assert audio is not None
        assert audio["title"] == ["Titulo Teste"]
        assert audio["artist"] == ["Artista Teste"]

    def test_silent_audio_is_rejected(self, engine: FFmpegEngine, tmp_path: Path) -> None:
        source = tmp_path / "silence.wav"
        subprocess.run([
            str(engine.ffmpeg_path), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "0.5",
            "-c:a", "pcm_s16le", str(source),
        ], check=True, capture_output=True)

        with pytest.raises(LoudnessAnalysisError):
            engine.normalize(source, tmp_path / "out.wav")

    def test_corrupted_file_is_rejected(self, engine: FFmpegEngine, tmp_path: Path) -> None:
        source = tmp_path / "corrupted.wav"
        source.write_bytes(b"this is not an audio file" * 10)

        with pytest.raises(AudioProcessingError):
            engine.normalize(source, tmp_path / "out.wav")

    def test_failed_track_leaves_no_residue(self, engine: FFmpegEngine, tmp_path: Path) -> None:
        source = tmp_path / "corrupted.wav"
        source.write_bytes(b"not audio" * 10)
        destination = tmp_path / "out.wav"

        with pytest.raises(AudioProcessingError):
            engine.normalize(source, destination)

        assert not destination.exists()
        assert list(tmp_path.glob("*.part*")) == []
