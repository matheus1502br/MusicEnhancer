"""Teste manual de ponta a ponta do engine MusicEnhancer."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.audio_analyzer import AudioAnalyzer
from core.ffmpeg_engine import FFmpegEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="Normaliza uma música para -14 LUFS / -1 dBTP.")
    parser.add_argument("--input", required=True, type=Path, help="Arquivo de áudio de origem")
    parser.add_argument("--output", required=True, type=Path, help="Arquivo exportado")
    args = parser.parse_args()

    try:
        engine = FFmpegEngine()
        analyzer = AudioAnalyzer(engine)
        print(f"FFmpeg:  {engine.ffmpeg_path}")
        print(f"FFprobe: {engine.ffprobe_path}")
        original = analyzer.inspect(args.input)
        loudness = engine.analyze_loudness(args.input)
        print("\nMétricas originais")
        print(f"  Loudness: {loudness.input_i:.2f} LUFS | True Peak: {loudness.input_tp:.2f} dBTP")
        print(f"  LRA: {loudness.input_lra:.2f} LU | Threshold: {loudness.input_thresh:.2f} LUFS")
        print(f"  Sample rate: {original.sample_rate} Hz | Bitrate: {original.bit_rate} bps | Bit-depth: {original.bits_per_raw_sample}")
        result = engine.normalize(args.input, args.output)
        print(f"\nDecisão: {'Bypass (cópia sem re-encode)' if result.status == 'bypass' else 'Normalização em 2 passagens'}")
        print("Passagem 2 concluída." if result.status == "normalized" else "Cópia direta concluída.")
        print("Metadados/Capas: copiados com Mutagen.")
        final = analyzer.inspect(args.output)
        print("\nMétricas finais")
        print(f"  Sample rate: {final.sample_rate} Hz | Bitrate: {final.bit_rate} bps | Bit-depth: {final.bits_per_raw_sample}")
        if result.post_validation is not None:
            print("  Pós-validação: " + ("OK" if result.post_validation[0] else "; ".join(result.post_validation[1])))
        return 0
    except Exception as exc:
        print(f"ERRO: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
