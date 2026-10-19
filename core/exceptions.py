"""Exceções específicas do processamento de áudio."""

from __future__ import annotations


class AudioProcessingError(RuntimeError):
    """Erro recuperável durante análise, normalização ou validação de uma faixa."""


class FFmpegExecutionError(AudioProcessingError):
    """Falha ao localizar ou executar ``ffmpeg``/``ffprobe``."""


class LoudnessAnalysisError(AudioProcessingError):
    """Métricas EBU R128 ausentes, inválidas ou incompatíveis com o loudnorm."""


class AudioValidationError(AudioProcessingError):
    """A saída gerada não preservou as propriedades técnicas esperadas."""


class UnsupportedAudioFormatError(ValueError):
    """Formato de destino não suportado pelo fluxo de normalização."""
