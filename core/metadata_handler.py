"""Cópia de tags e capas de álbum com Mutagen."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path


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
            raise RuntimeError("Mutagen não está instalado. Execute: pip install mutagen") from exc

        source_path, destination_path = Path(source), Path(destination)
        original = File(source_path)
        exported = File(destination_path)
        if original is None or exported is None:
            raise ValueError("Mutagen não reconheceu o arquivo de origem ou destino.")

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
            if exported.tags is None:
                exported.add_tags()
            exported.tags.clear()
            exported.tags.update(deepcopy(original.tags))
            exported.save()
