#!/usr/bin/env python3
"""Ponto de entrada do MusicEnhancer — Inicializa a aplicação PySide6."""

from __future__ import annotations

import sys
import os

# Garante que o diretório do projeto está no path para imports relativos
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase

from ui.main_window import MainWindow
from ui.styles import get_stylesheet


def setup_application() -> QApplication:
    """Configura e retorna a instância do QApplication."""
    # Qt6 gerencia High DPI nativamente — não requer atributos AA_EnableHighDpiScaling
    app = QApplication(sys.argv)
    app.setApplicationName("MusicEnhancer")
    app.setApplicationVersion("0.3.0")
    app.setOrganizationName("MusicEnhancer")
    app.setOrganizationDomain("musicenhancer.local")

    # Aplica stylesheet global
    app.setStyleSheet(get_stylesheet())

    # Tenta registrar fontes adicionais se existirem (opcional)
    fonts_dir = os.path.join(PROJECT_ROOT, "assets", "fonts")
    if os.path.isdir(fonts_dir):
        for font_file in os.listdir(fonts_dir):
            if font_file.lower().endswith((".ttf", ".otf")):
                QFontDatabase.addApplicationFont(os.path.join(fonts_dir, font_file))

    return app


def main() -> int:
    try:
        print("[MusicEnhancer] Inicializando aplicação...")
        app = setup_application()

        window = MainWindow()
        window.show()
        window.raise_()
        window.activateWindow()
        print("[MusicEnhancer] Janela principal pronta e em primeiro plano.")

        return app.exec()
    except Exception as exc:
        import traceback
        print(f"[MusicEnhancer] Erro crítico ao iniciar aplicação: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())