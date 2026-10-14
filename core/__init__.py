"""Núcleo de processamento de áudio do MusicEnhancer."""

from .audio_analyzer import AudioAnalyzer, AudioMetrics
from .ffmpeg_engine import FFmpegEngine, NormalizationResult
from .metadata_handler import MetadataHandler

__all__ = ["AudioAnalyzer", "AudioMetrics", "FFmpegEngine", "NormalizationResult", "MetadataHandler"]
