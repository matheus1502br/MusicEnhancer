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
    sample_fmt: str | None = None
    channel_layout: str | None = None


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
            sample_fmt=stream.get("sample_fmt"),
            channel_layout=stream.get("channel_layout"),
        )

    def validate_export(
        self,
        source: str | Path,
        output: str | Path,
        *,
        lossless: bool = True,
        expected_sample_rate: int | None = None,
        expected_channels: int | None = None,
        expected_bit_depth: int | None = None,
    ) -> tuple[bool, list[str]]:
        """Confirma as propriedades técnicas da saída contra o esperado/origem.

        Taxa de amostragem e canais são comparados sempre que ambos os lados
        informam os valores. A profundidade de bits só é comparada para formatos
        sem perdas e quando a informação está disponível. A duração é comparada
        com tolerância para absorver o padding de codificadores como MP3/AAC.
        """
        original = self.inspect(source)
        generated = self.inspect(output)
        failures: list[str] = []

        expected_rate = (
            expected_sample_rate if expected_sample_rate is not None else original.sample_rate
        )
        if expected_rate is not None and generated.sample_rate is not None:
            if generated.sample_rate != expected_rate:
                failures.append(
                    f"sample rate divergente ({expected_rate} != {generated.sample_rate})"
                )

        expected_ch = expected_channels if expected_channels is not None else original.channels
        if expected_ch is not None and generated.channels is not None:
            if generated.channels != expected_ch:
                failures.append(
                    f"canais divergentes ({expected_ch} != {generated.channels})"
                )
            elif (
                expected_ch == original.channels
                and original.channel_layout
                and generated.channel_layout
                and original.channel_layout != generated.channel_layout
            ):
                failures.append(
                    "layout de canais divergente "
                    f"({original.channel_layout} != {generated.channel_layout})"
                )

        if lossless:
            expected_depth = (
                expected_bit_depth
                if expected_bit_depth is not None
                else original.bits_per_raw_sample
            )
            if expected_depth is not None and generated.bits_per_raw_sample is not None:
                if generated.bits_per_raw_sample != expected_depth:
                    failures.append(
                        "bit-depth divergente "
                        f"({expected_depth} != {generated.bits_per_raw_sample})"
                    )

        if original.duration and generated.duration:
            tolerance = max(0.5, original.duration * 0.02)
            if abs(generated.duration - original.duration) > tolerance:
                failures.append(
                    "duração divergente "
                    f"({original.duration:.3f}s != {generated.duration:.3f}s)"
                )

        return not failures, failures

    def validate_lossless_export(
        self, source: str | Path, output: str | Path
    ) -> tuple[bool, list[str]]:
        """Compatibilidade: valida apenas propriedades de formatos sem perdas."""
        return self.validate_export(source, output, lossless=True)
