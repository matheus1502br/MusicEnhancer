#!/usr/bin/env python3
"""Ponto de entrada do MusicEnhancer — Inicializa a aplicação PySide6."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# 1. Garante que o diretório raiz do projeto está no sys.path independente do CWD
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from core.settings import load_config
from ui.main_window import MainWindow
from ui.styles import get_stylesheet
from utils.logger import setup_logging

# 2. Configura o sistema centralizado de logs (terminal e musicenhancer.log)
logger = setup_logging()


def handle_exception(exc_type, exc_value, exc_traceback):
    """Captura exceções não tratadas e grava no log antes de encerrar."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical(
        "Exceção não tratada capturada no arranque:",
        exc_info=(exc_type, exc_value, exc_traceback),
    )


# 3. Define o manipulador global de exceções
sys.excepthook = handle_exception


def setup_application() -> QApplication:
    """Configura e retorna a instância do QApplication com metadados do aplicativo."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MusicEnhancer")
    app.setApplicationVersion("0.3.0")
    app.setOrganizationName("MusicEnhancer")
    app.setOrganizationDomain("musicenhancer.local")

    # Aplica stylesheet global DAW / Dark Mode
    app.setStyleSheet(get_stylesheet())
    return app


def main() -> int:
    """Ponto de entrada principal."""
    logger.info("=== Inicializando MusicEnhancer ===")

    try:
        app = setup_application()

        logger.debug("Lendo configurações...")
        config = load_config()

        logger.debug("Instanciando MainWindow...")
        window = MainWindow(config=config)
        window.show()
        window.raise_()
        window.activateWindow()

        logger.info("Aplicação iniciada com sucesso.")
        return app.exec()
    except Exception as exc:
        logger.exception("Erro crítico durante a inicialização: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())