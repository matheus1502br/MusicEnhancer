"""Leitura de métricas de áudio e validação técnica pós-exportação."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ffmpeg_engine import FFmpegEngine


@dataclass(frozen=True)
class AudioMetrics:
    """Métricas técnicas extraídas de uma faixa de áudio."""

    sample_rate: int | None
    bit_rate: int | None
    bits_per_raw_sample: int | None
    codec_name: str | None
    channels: int | None
    duration: float | None = None


class AudioAnalyzer:
    """Consulta características de streams usando o ``ffprobe`` do engine."""

    def __init__(self, engine: "FFmpegEngine") -> None:
        self.engine = engine

    def inspect(self, file_path: str | Path) -> AudioMetrics:
        """Retorna as propriedades relevantes do primeiro stream de áudio."""
        data = self.engine.probe(file_path)
        streams = data.get("streams", [])
        stream: dict[str, Any] | None = next(
            (item for item in streams if item.get("codec_type") == "audio"), None
        )
        if stream is None:
            raise ValueError(f"Nenhum stream de áudio encontrado em: {file_path}")

        def as_int(value: Any) -> int | None:
            try:
                return int(value) if value not in (None, "N/A", "") else None
            except (TypeError, ValueError):
                return None

        def as_float(value: Any) -> float | None:
            try:
                return float(value) if value not in (None, "N/A", "") else None
            except (TypeError, ValueError):
                return None

        # WAV frequentemente só preenche bits_per_sample; formatos codificados podem
        # não informar profundidade, caso em que a validação não é aplicável.
        bit_depth = as_int(stream.get("bits_per_raw_sample")) or as_int(
            stream.get("bits_per_sample")
        )
        duration = as_float(stream.get("duration")) or as_float(data.get("format", {}).get("duration"))

        return AudioMetrics(
            sample_rate=as_int(stream.get("sample_rate")),
            bit_rate=as_int(stream.get("bit_rate")) or as_int(data.get("format", {}).get("bit_rate")),
            bits_per_raw_sample=bit_depth,
            codec_name=stream.get("codec_name"),
            channels=as_int(stream.get("channels")),
            duration=duration,
        )

    def validate_lossless_export(
        self, source: str | Path, output: str | Path
    ) -> tuple[bool, list[str]]:
        """Confirma sample rate e bit-depth quando ambos os arquivos os informam."""
        original = self.inspect(source)
        generated = self.inspect(output)
        failures: list[str] = []
        if original.sample_rate != generated.sample_rate:
            failures.append(
                f"sample rate divergente ({original.sample_rate} != {generated.sample_rate})"
            )
        if (
            original.bits_per_raw_sample is not None
            and generated.bits_per_raw_sample is not None
            and original.bits_per_raw_sample != generated.bits_per_raw_sample
        ):
            failures.append(
                "bit-depth divergente "
                f"({original.bits_per_raw_sample} != {generated.bits_per_raw_sample})"
            )
        return not failures, failures
