"""Wrapper seguro de subprocessos para análise e normalização pelo FFmpeg."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LoudnessMetrics:
    """Valores EBU R128 necessários pelo segundo passe do ``loudnorm``."""

    input_i: float
    input_tp: float
    input_lra: float
    input_thresh: float


@dataclass(frozen=True)
class NormalizationResult:
    """Resultado do processamento de uma única faixa."""

    status: str  # "bypass" ou "normalized"
    input_metrics: LoudnessMetrics
    post_validation: tuple[bool, list[str]] | None


class FFmpegEngine:
    """Localiza FFmpeg, extrai EBU R128 e executa a normalização em dois passos."""

    TARGET_I = -14.0
    TARGET_TP = -1.0
    TARGET_LRA = 11

    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[1]
        bin_dir = root / "utils" / "bin"
        self.ffmpeg_path = self._find_binary(bin_dir / "ffmpeg.exe", "ffmpeg")
        self.ffprobe_path = self._find_binary(bin_dir / "ffprobe.exe", "ffprobe")

    @staticmethod
    def _find_binary(local: Path, command: str) -> Path:
        """Prioriza ``utils/bin`` e usa PATH apenas como fallback."""
        if local.is_file():
            return local
        fallback = shutil.which(command)
        if fallback:
            return Path(fallback)
        raise FileNotFoundError(
            f"Não foi encontrado {local.name} em '{local.parent}' nem no PATH. "
            "Instale uma build estática do FFmpeg ou adicione-a ao PATH."
        )

    def _run(self, command: list[str], *, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command, check=True, text=True, encoding="utf-8", errors="replace",
                capture_output=capture_output,
            )
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "sem saída do processo").strip()
            raise RuntimeError(f"FFmpeg falhou (código {exc.returncode}): {details}") from exc

    def probe(self, file_path: str | Path) -> dict[str, Any]:
        """Obtém dados completos do container e dos streams via ``ffprobe``."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo de áudio não encontrado: {path}")
        result = self._run([
            str(self.ffprobe_path), "-v", "error", "-show_format", "-show_streams",
            "-of", "json", str(path),
        ])
        return json.loads(result.stdout)

    def analyze_loudness(self, file_path: str | Path) -> LoudnessMetrics:
        """Mede loudness integrado, true peak, LRA e threshold com ``ebur128``."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo de áudio não encontrado: {path}")
        result = self._run([
            str(self.ffmpeg_path), "-hide_banner", "-nostats", "-i", str(path),
            "-filter_complex", "ebur128=peak=true", "-f", "null", "-",
        ])
        # O relatório final contém as quatro medições; o último match é deliberado.
        report = result.stderr
        patterns = {
            "input_i": r"I:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS",
            "input_tp": r"Peak:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*dBFS",
            "input_lra": r"LRA:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LU",
            "input_thresh": r"Threshold:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS",
        }
        values: dict[str, float] = {}
        for name, pattern in patterns.items():
            matches = re.findall(pattern, report, flags=re.IGNORECASE)
            if not matches:
                raise RuntimeError(f"Não foi possível ler '{name}' do relatório ebur128.\n{report}")
            value = float(matches[-1])
            if value == float("inf") or value == float("-inf"):
                raise RuntimeError("O áudio é silencioso ou não possui métricas EBU R128 utilizáveis.")
            values[name] = value
        return LoudnessMetrics(**values)

    @staticmethod
    def _is_lossless(path: Path) -> bool:
        return path.suffix.lower() in {".flac", ".wav"}

    @staticmethod
    def _audio_bitrate(bit_rate: int | None) -> str:
        """Converte bitrate fonte para MP3/AAC respeitando o intervalo obrigatório."""
        if bit_rate is None or bit_rate <= 0:
            return "256k"
        kbps = round(bit_rate / 1000)
        # Bitrates de VBR reportados de maneira anômala usam o padrão seguro.
        if kbps < 32 or kbps > 1000:
            return "256k"
        return f"{max(192, min(320, kbps))}k"

    def normalize(self, source: str | Path, destination: str | Path) -> NormalizationResult:
        """Executa bypass ou loudnorm e reinscreve metadados com Mutagen."""
        from .audio_analyzer import AudioAnalyzer
        from .metadata_handler import MetadataHandler

        source_path, output_path = Path(source), Path(destination)
        if source_path.resolve() == output_path.resolve():
            raise ValueError("A saída deve ser diferente do arquivo de origem.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        metrics = self.analyze_loudness(source_path)
        analyzer = AudioAnalyzer(self)
        source_info = analyzer.inspect(source_path)
        bypass = -14.5 <= metrics.input_i <= -13.5 and metrics.input_tp <= -1.0

        if bypass:
            command = [str(self.ffmpeg_path), "-y", "-i", str(source_path), "-map", "0", "-c", "copy", str(output_path)]
            self._run(command)
            # FFmpeg já transfere metadata na cópia, mas Mutagen garante tags/capas.
            MetadataHandler.copy_all(source_path, output_path)
            return NormalizationResult("bypass", metrics, None)

        filter_value = (
            f"loudnorm=I={self.TARGET_I:.1f}:TP={self.TARGET_TP:.1f}:LRA={self.TARGET_LRA}:"
            f"measured_I={metrics.input_i:.6f}:measured_TP={metrics.input_tp:.6f}:"
            f"measured_LRA={metrics.input_lra:.6f}:measured_thresh={metrics.input_thresh:.6f}:linear=true"
        )
        command = [str(self.ffmpeg_path), "-y", "-i", str(source_path), "-map", "0:a:0", "-af", filter_value]
        suffix = output_path.suffix.lower()
        if suffix == ".mp3":
            command += ["-c:a", "libmp3lame", "-b:a", self._audio_bitrate(source_info.bit_rate)]
        elif suffix in {".m4a", ".aac"}:
            command += ["-c:a", "aac", "-b:a", self._audio_bitrate(source_info.bit_rate)]
        elif suffix == ".wav":
            codec = "pcm_s24le" if source_info.bits_per_raw_sample == 24 else "pcm_s16le"
            command += ["-c:a", codec]
        elif suffix == ".flac":
            command += ["-c:a", "flac"]
            if source_info.bits_per_raw_sample == 24:
                command += ["-sample_fmt", "s32"]
        else:
            raise ValueError("Formato de saída não suportado nesta etapa: use MP3, AAC/M4A, FLAC ou WAV.")
        if source_info.sample_rate:
            command += ["-ar", str(source_info.sample_rate)]
        command.append(str(output_path))
        self._run(command)
        MetadataHandler.copy_all(source_path, output_path)
        validation = analyzer.validate_lossless_export(source_path, output_path) if self._is_lossless(source_path) else None
        return NormalizationResult("normalized", metrics, validation)
