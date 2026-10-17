"""Configuração centralizada de logs do MusicEnhancer."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

DEFAULT_LOG_FILE = Path(__file__).resolve().parents[1] / "musicenhancer.log"


def setup_logging(log_file: str | Path | None = None, level: int = logging.INFO) -> logging.Logger:
    """Configura o sistema de log da aplicação.
    
    Abre o arquivo em modo 'w' para que a cada execução o log anterior
    seja substituído por uma sessão limpa.
    """
    target_path = Path(log_file) if log_file else DEFAULT_LOG_FILE
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Formatação com timestamp, nível alinhado, nome do módulo e mensagem
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File Handler com mode="w" (substitui a cada execução)
    file_handler = logging.FileHandler(target_path, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console Handler para exibir mensagens no terminal
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # Configura o root logger para que todos os módulos utilizem esses handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove handlers antigos para evitar duplicações
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logger = logging.getLogger("MusicEnhancer")
    logger.info("Sistema de log iniciado. Arquivo: %s", target_path.name)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger configurado para o módulo informado."""
    return logging.getLogger(name)

