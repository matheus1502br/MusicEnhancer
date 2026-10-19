"""Cópia de tags e capas de álbum com Mutagen."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


class MetadataHandler:
  """Preserva metadados após a criação do arquivo pelo FFmpeg."""

  @staticmethod
  def copy_all(source: str | Path, destination: str | Path) -> None:
    """Copia tags e imagens incorporadas entre arquivos do mesmo formato.

    MP3 é salvo explicitamente como ID3v2.3. Para FLAC, os Vorbis Comments e
    todos os blocos de imagem são recriados. Outros formatos suportados pelo
    Mutagen recebem uma cópia profunda de sua coleção de tags quando possível.
    """
    try:
      from mutagen import File
      from mutagen.flac import FLAC
      from mutagen.id3 import ID3
      from mutagen.mp3 import MP3
    except ImportError as exc:
      raise RuntimeError(
          "Mutagen não está instalado. Execute: pip install mutagen"
      ) from exc

    source_path, destination_path = Path(source), Path(destination)
    original = File(source_path)
    exported = File(destination_path)
    if original is None or exported is None:
      raise ValueError(
          "Mutagen não reconheceu o arquivo de origem ou destino."
      )

    if isinstance(original, MP3) and isinstance(exported, MP3):
      tags = deepcopy(original.tags) if original.tags is not None else ID3()
      exported.tags = tags
      exported.save(v2_version=3)
      return

    if isinstance(original, FLAC) and isinstance(exported, FLAC):
      exported.delete()
      if original.tags:
        for key, values in original.tags.items():
          exported[key] = list(values)
      exported.clear_pictures()
      for picture in original.pictures:
        exported.add_picture(deepcopy(picture))
      exported.save()
      return

    if original.tags is not None:
      try:
        if exported.tags is None:
          exported.add_tags()

        # Tipagem Any para informar o Pylance sobre a estrutura dinâmica do Mutagen
        orig_tags: Any = original.tags
        exp_tags: Any = exported.tags

        if exp_tags is not None and orig_tags is not None:
          # Se o objeto suportar a interface direta de dicionário
          if hasattr(exp_tags, "clear") and hasattr(exp_tags, "update"):
            exp_tags.clear()
            exp_tags.update(deepcopy(orig_tags))
          elif hasattr(orig_tags, "items"):
            # Fallback para M4A/MP4/Ogg
            if hasattr(exp_tags, "keys"):
              for key in list(exp_tags.keys()):
                del exp_tags[key]
            for key, value in orig_tags.items():
              exp_tags[key] = deepcopy(value)

        exported.save()
      except Exception as e:
        raise ValueError(
            f"Não foi possível copiar metadados para este formato: {e}"
        ) from e