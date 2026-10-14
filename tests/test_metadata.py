"""Testes de leitura e escrita de metadados via Mutagen."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Mutagen é dependência opcional em tempo de teste; se não instalado, marcamos como skip
pytest.importorskip("mutagen")

from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from core.metadata_handler import MetadataHandler


class TestMetadataHandler:
    """Cópia de tags e capas entre arquivos."""

    def test_copy_mp3_id3v23(self, tmp_path: Path) -> None:
        """Testa cópia de tags ID3v2.3 e APIC via mock do mutagen.File."""
        src = tmp_path / "src.mp3"
        dst = tmp_path / "dst.mp3"
        src.write_bytes(b"ID3")
        dst.write_bytes(b"ID3")

        # Mock do mutagen.File para retornar objetos MP3 mockados com spec correto
        with patch("mutagen.File") as mock_file:
            mock_src_tags = MagicMock()
            mock_src_tags.__getitem__ = lambda self, k: {"TIT2": MagicMock(text=["Título Original"]), "TPE1": MagicMock(text=["Artista Teste"]), "APIC": [MagicMock(data=b"cover_data")]}[k]
            mock_src_tags.getall = lambda k: [MagicMock(data=b"cover_data")] if k == "APIC" else []
            mock_src_tags.version = (3, 0)

            mock_dst_tags = MagicMock()
            mock_dst_tags.__setitem__ = MagicMock()

            mock_src_mp3 = MagicMock(spec=MP3)
            mock_src_mp3.tags = mock_src_tags
            mock_src_mp3.save = MagicMock()

            mock_dst_mp3 = MagicMock(spec=MP3)
            mock_dst_mp3.tags = mock_dst_tags
            mock_dst_mp3.save = MagicMock()

            mock_file.side_effect = [mock_src_mp3, mock_dst_mp3]

            MetadataHandler.copy_all(src, dst)

            # Verifica se o destino salvou com v2_version=3
            mock_dst_mp3.save.assert_called_with(v2_version=3)

    def test_copy_flac_vorbis_and_pictures(self, tmp_path: Path) -> None:
        """Testa cópia de Vorbis Comments e pictures em FLAC via mock do mutagen.File."""
        src = tmp_path / "src.flac"
        dst = tmp_path / "dst.flac"
        src.write_bytes(b"fLaC")
        dst.write_bytes(b"fLaC")

        with patch("mutagen.File") as mock_file:
            mock_pic = MagicMock()
            mock_pic.type = 3
            mock_pic.mime = "image/jpeg"
            mock_pic.desc = "Front cover"
            mock_pic.data = b"fake_jpeg_data"

            mock_src = MagicMock(spec=FLAC)
            mock_src.tags = {"title": ["Título FLAC"], "artist": ["Artista FLAC"], "album": ["Álbum Teste"]}
            mock_src.pictures = [mock_pic]

            mock_dst = MagicMock(spec=FLAC)
            mock_dst.tags = {}
            mock_dst.pictures = []
            mock_dst.clear_pictures = MagicMock()
            mock_dst.add_picture = MagicMock()
            mock_dst.save = MagicMock()
            mock_dst.__setitem__ = MagicMock()
            mock_dst.delete = MagicMock()

            mock_file.side_effect = [mock_src, mock_dst]

            MetadataHandler.copy_all(src, dst)

            mock_dst.delete.assert_called()
            mock_dst.clear_pictures.assert_called()
            mock_dst.add_picture.assert_called_with(mock_pic)
            mock_dst.save.assert_called()

    def test_copy_generic_fallback(self, tmp_path: Path) -> None:
        """Formatos não MP3/FLAC usam cópia genérica de tags via mock do mutagen.File."""
        src = tmp_path / "src.ogg"
        dst = tmp_path / "dst.ogg"
        src.write_bytes(b"OggS")
        dst.write_bytes(b"OggS")

        with patch("mutagen.File") as mock_file:
            mock_src = MagicMock()
            mock_src.tags = {"title": ["OGG Title"]}
            mock_src.__class__ = MagicMock()
            mock_src.__class__.__name__ = "OggVorbis"

            mock_dst_tags = MagicMock()
            mock_dst_tags.clear = MagicMock()
            mock_dst_tags.update = MagicMock()

            mock_dst = MagicMock()
            mock_dst.tags = None
            mock_dst.add_tags = MagicMock(side_effect=lambda: setattr(mock_dst, 'tags', mock_dst_tags))
            mock_dst.save = MagicMock()
            mock_dst.__class__ = MagicMock()
            mock_dst.__class__.__name__ = "OggVorbis"

            mock_file.side_effect = [mock_src, mock_dst]

            MetadataHandler.copy_all(src, dst)

            mock_dst.add_tags.assert_called()
            mock_dst_tags.clear.assert_called()
            mock_dst_tags.update.assert_called()
            mock_dst.save.assert_called()

    def test_raises_when_mutagen_missing(self, tmp_path: Path) -> None:
        src = tmp_path / "src.mp3"
        dst = tmp_path / "dst.mp3"
        src.write_bytes(b"ID3")
        dst.write_bytes(b"ID3")

        with patch.dict("sys.modules", {"mutagen": None, "mutagen.mp3": None, "mutagen.id3": None}):
            with pytest.raises(RuntimeError, match="Mutagen não está instalado"):
                MetadataHandler.copy_all(src, dst)