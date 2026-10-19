"""Wrapper seguro de subprocessos para análise e normalização pelo FFmpeg."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import (
    AudioValidationError,
    FFmpegExecutionError,
    LoudnessAnalysisError,
    UnsupportedAudioFormatError,
)
from .settings import DEFAULT_CONFIG

logger = logging.getLogger(__name__)

# Tolerância de loudness integrado usada na decisão de bypass (em LU).
BYPASS_TOLERANCE_LU = 0.5

# Intervalos aceitos pelo filtro loudnorm do FFmpeg.
_LOUDNORM_LIMITS: dict[str, tuple[float, float]] = {
    "I": (-70.0, -5.0),
    "TP": (-9.0, 0.0),
    "LRA": (1.0, 50.0),
}


@dataclass(frozen=True)
class LoudnessMetrics:
    """Valores EBU R128 necessários pelo segundo passe do ``loudnorm``."""

    input_i: float
    input_tp: float
    input_lra: float
    input_thresh: float
    target_offset: float = 0.0


@dataclass(frozen=True)
class NormalizationResult:
    """Resultado do processamento de uma única faixa."""

    status: str  # "bypass", "normalized" ou "skipped"
    input_metrics: LoudnessMetrics
    post_validation: tuple[bool, list[str]] | None
    normalization_type: str = "linear"
    metadata_preserved: bool = True
    warnings: tuple[str, ...] = ()


def should_bypass(
    metrics: LoudnessMetrics,
    *,
    target_i: float,
    target_tp: float,
    same_container: bool = True,
    tolerance: float = BYPASS_TOLERANCE_LU,
) -> bool:
    """Decide se a cópia sem re-encode atende aos alvos informados.

    O bypass só é válido quando o contêiner de destino é o mesmo da origem,
    o loudness integrado está dentro da tolerância do alvo e o true peak não
    ultrapassa o limite configurado. O LRA não é usado como condição de bypass
    porque o ``loudnorm`` não amplia a faixa dinâmica de uma faixa.
    """

    return (
        same_container
        and abs(metrics.input_i - target_i) <= tolerance
        and metrics.input_tp <= target_tp
    )


class FFmpegEngine:
    """Localiza FFmpeg, extrai EBU R128 e executa a normalização em dois passos."""

    TARGET_I = float(DEFAULT_CONFIG["target_loudness"])
    TARGET_TP = float(DEFAULT_CONFIG["target_true_peak"])
    TARGET_LRA = float(DEFAULT_CONFIG["target_lra"])

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
        logger.debug("Executando subprocesso: %s", " ".join(command))
        try:
            return subprocess.run(
                command, check=True, text=True, encoding="utf-8", errors="replace",
                capture_output=capture_output,
            )
        except FileNotFoundError as exc:
            raise FFmpegExecutionError(
                f"Executável do FFmpeg não encontrado: {command[0]}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "sem saída do processo").strip()
            logger.error("Falha no subprocesso (código %d): %s", exc.returncode, details)
            raise FFmpegExecutionError(
                f"FFmpeg falhou (código {exc.returncode}): {details}"
            ) from exc
        except OSError as exc:
            raise FFmpegExecutionError(
                f"Não foi possível executar o FFmpeg: {exc}"
            ) from exc

    def probe(self, file_path: str | Path) -> dict[str, Any]:
        """Obtém dados completos do container e dos streams via ``ffprobe``."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo de áudio não encontrado: {path}")
        result = self._run([
            str(self.ffprobe_path), "-v", "error", "-show_format", "-show_streams",
            "-of", "json", str(path),
        ])
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise FFmpegExecutionError(
                f"O ffprobe retornou dados inválidos para '{path.name}'."
            ) from exc
        if not isinstance(data, dict):
            raise FFmpegExecutionError(
                f"O ffprobe retornou uma estrutura inesperada para '{path.name}'."
            )
        return data

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
                raise LoudnessAnalysisError(
                    f"Não foi possível ler '{name}' do relatório ebur128.\n{report}"
                )
            try:
                values[name] = float(matches[-1])
            except ValueError as exc:
                raise LoudnessAnalysisError(
                    f"Valor inválido para '{name}' no relatório ebur128: {matches[-1]!r}"
                ) from exc
        metrics = LoudnessMetrics(**values)
        self._validate_metrics(metrics, source="ebur128")
        return metrics

    def analyze_loudnorm(
        self,
        file_path: str | Path,
        *,
        target_i: float,
        target_tp: float,
        target_lra: float,
    ) -> LoudnessMetrics:
        """Executa o primeiro passe do ``loudnorm`` e lê o relatório JSON.

        As métricas retornadas são exatamente as esperadas por
        ``measured_I``/``measured_TP``/``measured_LRA``/``measured_thresh`` no
        segundo passe, incluindo o ``target_offset`` recomendado pelo filtro.
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo de áudio não encontrado: {path}")
        self._validate_targets(target_i, target_tp, target_lra)

        filter_value = (
            f"loudnorm=I={target_i:.1f}:TP={target_tp:.1f}:LRA={target_lra:.1f}:"
            "print_format=json"
        )
        result = self._run([
            str(self.ffmpeg_path), "-hide_banner", "-nostats", "-i", str(path),
            "-af", filter_value, "-f", "null", "-",
        ])
        data = self._extract_last_json(result.stderr)
        required = ("input_i", "input_tp", "input_lra", "input_thresh")
        values: dict[str, float] = {}
        for key in required:
            raw = data.get(key)
            try:
                values[key] = float(raw)
            except (TypeError, ValueError) as exc:
                raise LoudnessAnalysisError(
                    f"Métrica '{key}' ausente ou inválida no relatório loudnorm: {raw!r}"
                ) from exc

        raw_offset = data.get("target_offset", 0.0)
        try:
            target_offset = float(raw_offset)
        except (TypeError, ValueError) as exc:
            raise LoudnessAnalysisError(
                f"target_offset inválido no relatório loudnorm: {raw_offset!r}"
            ) from exc

        metrics = LoudnessMetrics(**values, target_offset=target_offset)
        self._validate_metrics(metrics, source="loudnorm")
        return metrics

    @staticmethod
    def _extract_last_json(text: str) -> dict[str, Any]:
        """Extrai o último objeto JSON simples impresso pelo ``loudnorm``."""
        matches = re.findall(r"\{[^{}]*\}", text or "", flags=re.DOTALL)
        if not matches:
            raise LoudnessAnalysisError(
                "O loudnorm não retornou o relatório JSON esperado.\n" + (text or "")
            )
        try:
            data = json.loads(matches[-1])
        except json.JSONDecodeError as exc:
            raise LoudnessAnalysisError(
                "O relatório JSON retornado pelo loudnorm é inválido."
            ) from exc
        if not isinstance(data, dict):
            raise LoudnessAnalysisError(
                "O relatório retornado pelo loudnorm não é um objeto JSON."
            )
        return data

    @staticmethod
    def _validate_metrics(metrics: LoudnessMetrics, *, source: str) -> None:
        """Rejeita métricas não finitas ou fora dos intervalos do ``loudnorm``."""
        values = {
            "input_i": metrics.input_i,
            "input_tp": metrics.input_tp,
            "input_lra": metrics.input_lra,
            "input_thresh": metrics.input_thresh,
        }
        for name, value in values.items():
            if not math.isfinite(value):
                raise LoudnessAnalysisError(
                    f"Métrica '{name}' não finita no relatório {source}. "
                    "O arquivo pode estar silencioso ou corrompido."
                )
        if not -99.0 <= metrics.input_i <= 0.0:
            raise LoudnessAnalysisError(
                f"Loudness integrado inválido no relatório {source}: {metrics.input_i}"
            )
        if not -99.0 <= metrics.input_tp <= 99.0:
            raise LoudnessAnalysisError(
                f"True peak inválido no relatório {source}: {metrics.input_tp}"
            )
        if not 0.0 <= metrics.input_lra <= 99.0:
            raise LoudnessAnalysisError(
                f"LRA inválido no relatório {source}: {metrics.input_lra}"
            )
        if not -99.0 <= metrics.input_thresh <= 0.0:
            raise LoudnessAnalysisError(
                f"Threshold inválido no relatório {source}: {metrics.input_thresh}"
            )

    @staticmethod
    def _validate_targets(target_i: float, target_tp: float, target_lra: float) -> None:
        """Garante que os alvos cabem nos intervalos aceitos pelo loudnorm."""
        targets = {
            "loudness integrado": ("I", target_i),
            "true peak": ("TP", target_tp),
            "LRA": ("LRA", target_lra),
        }
        for label, (key, value) in targets.items():
            if not math.isfinite(value):
                raise ValueError(f"Alvo de {label} inválido: {value!r}")
            minimum, maximum = _LOUDNORM_LIMITS[key]
            if not minimum <= value <= maximum:
                raise ValueError(
                    f"Alvo de {label} fora do intervalo suportado pelo loudnorm "
                    f"({minimum:g} a {maximum:g}): {value:g}"
                )

    @staticmethod
    def _is_lossless(path: str | Path) -> bool:
        return Path(path).suffix.lower() in {".flac", ".wav"}

    @staticmethod
    def _audio_bitrate(bit_rate: int | None) -> str:
        """Converte bitrate fonte para MP3/AAC respeitando o intervalo obrigatório."""
        if bit_rate is None or bit_rate <= 0:
            return "256k"
        kbps = round(bit_rate / 1000)
        # Fontes sem perdas ou bitrates muito altos (>1000 kbps, como FLAC/WAV) usam qualidade máxima (320k)
        if kbps > 1000:
            return "320k"
        # Bitrates muito baixos ou anômalos usam padrão seguro
        if kbps < 32:
            return "256k"
        return f"{max(192, min(320, kbps))}k"

    @staticmethod
    def _select_wav_codec(info: Any) -> str:
        """Escolhe o codec WAV preservando profundidade e representação das amostras."""
        codec = (getattr(info, "codec_name", None) or "").lower()
        direct = {
            "pcm_u8": "pcm_u8",
            "pcm_s8": "pcm_s8",
            "pcm_s16le": "pcm_s16le",
            "pcm_s24le": "pcm_s24le",
            "pcm_s32le": "pcm_s32le",
            "pcm_f32le": "pcm_f32le",
            "pcm_f64le": "pcm_f64le",
        }
        if codec in direct:
            return direct[codec]

        sample_fmt = (getattr(info, "sample_fmt", None) or "").lower()
        depth = getattr(info, "bits_per_raw_sample", None)
        if codec in {"flac", "alac", "wavpack", "ape", "tta", "truehd", "mlp"}:
            if sample_fmt in {"flt", "fltp"}:
                return "pcm_f32le"
            if sample_fmt == "dbl":
                return "pcm_f64le"
            if depth == 24:
                return "pcm_s24le"
            if depth == 32:
                return "pcm_s32le"
            return "pcm_s16le"

        # Fontes compactadas não têm profundidade PCM própria; 16 bits é o
        # padrão seguro para decodificação em WAV.
        return "pcm_s16le"

    @staticmethod
    def _wav_codec_bit_depth(codec: str) -> int:
        return {
            "pcm_u8": 8,
            "pcm_s8": 8,
            "pcm_s16le": 16,
            "pcm_s24le": 24,
            "pcm_s32le": 32,
            "pcm_f32le": 32,
            "pcm_f64le": 64,
        }.get(codec, 16)

    @staticmethod
    def _select_flac_bit_depth(info: Any) -> int:
        """FLAC aceita até 24 bits; profundidades menores são preservadas."""
        depth = getattr(info, "bits_per_raw_sample", None)
        sample_fmt = (getattr(info, "sample_fmt", None) or "").lower()
        if depth is None:
            if sample_fmt in {"s32", "flt", "fltp", "dbl"}:
                return 24
            return 16
        return 16 if depth <= 16 else 24

    @staticmethod
    def _linear_normalization_possible(
        metrics: LoudnessMetrics,
        *,
        target_i: float,
        target_tp: float,
        target_lra: float,
    ) -> bool:
        """Estima se o loudnorm conseguirá aplicar ganho linear sem exceder TP/LRA."""
        gain = target_i + metrics.target_offset - metrics.input_i
        if metrics.input_lra > target_lra + 1e-6:
            return False
        if metrics.input_tp + gain > target_tp + 1e-6:
            return False
        return True

    @staticmethod
    def _temporary_path(destination: Path) -> Path:
        """Cria um caminho temporário no mesmo diretório, com a extensão final."""
        token = uuid.uuid4().hex
        return destination.parent / f".{destination.stem}.{token}.part{destination.suffix}"

    @staticmethod
    def _ensure_output(path: Path) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            raise AudioValidationError(
                f"O FFmpeg não gerou uma saída válida: {path.name}"
            )

    @staticmethod
    def _copy_metadata(source: Path, destination: Path) -> tuple[bool, str | None]:
        """Copia metadados sem invalidar um áudio já normalizado com sucesso."""
        from .metadata_handler import MetadataHandler

        try:
            MetadataHandler.copy_all(source, destination)
        except Exception as meta_exc:  # Mutagen pode lançar erros variados por formato.
            message = f"Falha não crítica ao copiar metadados: {meta_exc}"
            logger.warning("%s (%s)", message, source.name)
            return False, message
        return True, None

    def _codec_arguments(
        self,
        info: Any,
        suffix: str,
        *,
        warnings: list[str],
    ) -> tuple[list[str], int | None, int | None]:
        """Monta os argumentos de codec e as propriedades esperadas na validação."""
        channels = getattr(info, "channels", None)
        bit_depth = getattr(info, "bits_per_raw_sample", None)

        if suffix == ".mp3":
            arguments = ["-c:a", "libmp3lame", "-b:a", self._audio_bitrate(getattr(info, "bit_rate", None))]
            expected_channels = channels
            if channels is not None and channels > 2:
                expected_channels = 2
                warnings.append(
                    "MP3 não suporta mais de 2 canais; a saída foi convertida para estéreo."
                )
            return arguments, expected_channels, None

        if suffix in {".m4a", ".aac"}:
            arguments = ["-c:a", "aac", "-b:a", self._audio_bitrate(getattr(info, "bit_rate", None))]
            return arguments, channels, None

        if suffix == ".wav":
            codec = self._select_wav_codec(info)
            return ["-c:a", codec], channels, self._wav_codec_bit_depth(codec)

        if suffix == ".flac":
            depth = self._select_flac_bit_depth(info)
            sample_fmt = "s16" if depth <= 16 else "s32"
            source_depth = bit_depth or 0
            is_float_source = (
                (getattr(info, "codec_name", None) or "").lower().startswith("pcm_")
                and (getattr(info, "sample_fmt", None) or "").lower() in {"flt", "fltp", "dbl"}
            )
            if source_depth > 24 or is_float_source:
                warnings.append(
                    "FLAC suporta no máximo 24 bits; a profundidade foi limitada a 24 bits "
                    "por exigência técnica do formato."
                )
            return (
                ["-c:a", "flac", "-sample_fmt", sample_fmt, "-bits_per_raw_sample", str(depth)],
                channels,
                depth,
            )

        raise UnsupportedAudioFormatError(
            "Formato de saída não suportado nesta etapa: use MP3, AAC/M4A, FLAC ou WAV."
        )

    def normalize(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        target_i: float | None = None,
        target_tp: float | None = None,
        target_lra: float | None = None,
    ) -> NormalizationResult:
        """Executa bypass ou loudnorm em dois passos e valida a saída antes de publicá-la."""
        from .audio_analyzer import AudioAnalyzer

        source_path, output_path = Path(source), Path(destination)
        if source_path.resolve() == output_path.resolve():
            raise ValueError("A saída deve ser diferente do arquivo de origem.")
        if not source_path.is_file():
            raise FileNotFoundError(f"Arquivo de áudio não encontrado: {source_path}")
        if source_path.stat().st_size == 0:
            raise ValueError(f"Arquivo de áudio vazio: {source_path}")

        target_i_val = self.TARGET_I if target_i is None else target_i
        target_tp_val = self.TARGET_TP if target_tp is None else target_tp
        target_lra_val = self.TARGET_LRA if target_lra is None else target_lra
        self._validate_targets(target_i_val, target_tp_val, target_lra_val)

        suffix = output_path.suffix.lower()
        if suffix not in {".mp3", ".m4a", ".aac", ".wav", ".flac"}:
            raise UnsupportedAudioFormatError(
                "Formato de saída não suportado nesta etapa: use MP3, AAC/M4A, FLAC ou WAV."
            )

        analyzer = AudioAnalyzer(self)
        # Valida a existência de stream de áudio antes de iniciar as passagens.
        source_info = analyzer.inspect(source_path)
        metrics = self.analyze_loudnorm(
            source_path,
            target_i=target_i_val,
            target_tp=target_tp_val,
            target_lra=target_lra_val,
        )

        logger.info(
            "Métricas de origem (%s): I=%.2f LUFS, TP=%.2f dBTP, LRA=%.2f LU | "
            "Alvo: I=%.1f LUFS, TP=%.1f dBTP, LRA=%.1f LU",
            source_path.name, metrics.input_i, metrics.input_tp, metrics.input_lra,
            target_i_val, target_tp_val, target_lra_val,
        )

        same_container = suffix == source_path.suffix.lower()
        bypass = should_bypass(
            metrics,
            target_i=target_i_val,
            target_tp=target_tp_val,
            same_container=same_container,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._temporary_path(output_path)
        warnings: list[str] = []
        normalization_type = "bypass"
        metadata_preserved = True
        expected_channels = source_info.channels
        normalized_suffix = suffix
        expected_bit_depth = (
            source_info.bits_per_raw_sample
            if normalized_suffix in {".flac", ".wav"}
            else None
        )
        expected_sample_rate = source_info.sample_rate

        try:
            if bypass:
                logger.info(
                    "Faixa dentro do alvo. Aplicando bypass sem re-encode: %s -> %s",
                    source_path.name, output_path.name,
                )
                command = [
                    str(self.ffmpeg_path), "-y", "-i", str(source_path),
                    "-map", "0", "-c", "copy", str(temp_path),
                ]
                self._run(command)
            else:
                linear_possible = self._linear_normalization_possible(
                    metrics,
                    target_i=target_i_val,
                    target_tp=target_tp_val,
                    target_lra=target_lra_val,
                )
                normalization_type = "linear" if linear_possible else "dynamic"
                logger.info(
                    "Aplicando normalização EBU R128 em 2 passos (%s): %s -> %s",
                    normalization_type, source_path.name, output_path.name,
                )
                filter_value = (
                    f"loudnorm=I={target_i_val:.1f}:TP={target_tp_val:.1f}:"
                    f"LRA={target_lra_val:.1f}:"
                    f"measured_I={metrics.input_i:.6f}:"
                    f"measured_TP={metrics.input_tp:.6f}:"
                    f"measured_LRA={metrics.input_lra:.6f}:"
                    f"measured_thresh={metrics.input_thresh:.6f}:"
                    f"offset={metrics.target_offset:.6f}:"
                    f"linear={'true' if linear_possible else 'false'}:"
                    "print_format=json"
                )
                command = [
                    str(self.ffmpeg_path), "-y", "-i", str(source_path),
                    "-map", "0:a:0", "-af", filter_value,
                ]
                codec_args, expected_channels, expected_bit_depth = self._codec_arguments(
                    source_info, suffix, warnings=warnings
                )
                command += codec_args
                if expected_sample_rate:
                    command += ["-ar", str(expected_sample_rate)]
                if expected_channels:
                    command += ["-ac", str(expected_channels)]
                if (
                    source_info.channel_layout
                    and expected_channels == source_info.channels
                ):
                    command += ["-channel_layout", source_info.channel_layout]
                command.append(str(temp_path))

                completed = self._run(command)
                normalization_type = self._read_normalization_type(
                    completed.stderr, fallback=normalization_type
                )

            self._ensure_output(temp_path)
            metadata_preserved, metadata_warning = self._copy_metadata(
                source_path, temp_path
            )
            if metadata_warning:
                warnings.append(metadata_warning)

            validation = analyzer.validate_export(
                source_path,
                temp_path,
                lossless=normalized_suffix in {".flac", ".wav"},
                expected_sample_rate=expected_sample_rate,
                expected_channels=expected_channels,
                expected_bit_depth=expected_bit_depth,
            )
            if not validation[0]:
                raise AudioValidationError(
                    "A saída não preservou as propriedades técnicas esperadas: "
                    + "; ".join(validation[1])
                )

            # Publica a saída somente depois de gerar, validar e copiar metadados.
            os.replace(temp_path, output_path)
            return NormalizationResult(
                status="bypass" if bypass else "normalized",
                input_metrics=metrics,
                post_validation=validation,
                normalization_type=normalization_type,
                metadata_preserved=metadata_preserved,
                warnings=tuple(warnings),
            )
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError as cleanup_exc:
                    logger.warning(
                        "Não foi possível remover o arquivo temporário '%s': %s",
                        temp_path, cleanup_exc,
                    )

    def _read_normalization_type(self, stderr: str, *, fallback: str) -> str:
        """Lê o tipo efetivamente usado pelo loudnorm no segundo passe."""
        try:
            data = self._extract_last_json(stderr)
        except LoudnessAnalysisError:
            # O relatório do segundo passe é informativo; não invalida o áudio.
            return fallback
        value = data.get("normalization_type")
        if value in {"linear", "dynamic"}:
            return str(value)
        return fallback
