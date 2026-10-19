"""Módulo de configurações centrais do MusicEnhancer.

Gerencia o carregamento, validação e persistência das configurações da aplicação,
garantindo tolerância a falhas, valores padrão seguros do domínio EBU R128 e
compatibilidade de diretórios graváveis pelo usuário no Windows, Linux e macOS.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Diretório raiz do projeto (independente do CWD)
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Valores padrão seguros baseados nos padrões de áudio (EBU R128) e na interface
DEFAULT_CONFIG: dict[str, Any] = {
    "target_loudness": -14.0,
    "target_true_peak": -1.0,
    "target_lra": 11.0,
    "output_folder": "",
    "current_preset": "Streaming (-14 LUFS, -1,0 dBTP)",
    "advanced_expanded": False,
    "overwrite_choice": "rename",
    "overwrite_apply_all": False,
}

VALID_OVERWRITE_CHOICES = {"rename", "replace", "skip"}


def get_default_config() -> dict[str, Any]:
    """Retorna uma cópia independente do dicionário de configurações padrão."""
    return copy.deepcopy(DEFAULT_CONFIG)


def get_user_config_dir() -> Path:
    """Retorna o diretório de dados/configurações gravável do usuário conforme o SO.
    
    No Windows, utiliza %APPDATA%/MusicEnhancer.
    No macOS, ~/Library/Application Support/MusicEnhancer.
    No Linux, $XDG_CONFIG_HOME/MusicEnhancer ou ~/.config/MusicEnhancer.
    """
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data) / "MusicEnhancer"
        return Path.home() / "AppData" / "Roaming" / "MusicEnhancer"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MusicEnhancer"
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            return Path(xdg_config) / "MusicEnhancer"
        return Path.home() / ".config" / "MusicEnhancer"


def get_default_config_path(check_portable: bool = True) -> Path:
    """Retorna o caminho do arquivo de configuração padrão.
    
    Se check_portable=True e existir um config.json na raiz do projeto (modo dev/portátil),
    ele será priorizado. Caso contrário, retorna o caminho seguro em AppData do usuário.
    """
    if check_portable:
        portable_file = PROJECT_ROOT / "config.json"
        if portable_file.is_file():
            return portable_file

    return get_user_config_dir() / "config.json"


def sanitize_config(data: Any) -> dict[str, Any]:
    """Valida e sanitiza um dicionário de configuração.
    
    Valores ausentes ou de tipos inválidos são substituídos de forma segura
    pelos valores correspondentes em DEFAULT_CONFIG.
    """
    defaults = get_default_config()
    if not isinstance(data, dict):
        logger.warning(
            "Configuração carregada não é um dicionário (tipo: %s). Usando valores padrão.",
            type(data).__name__,
        )
        return defaults

    sanitized: dict[str, Any] = {}

    # target_loudness (-70.0 a 0.0 LUFS)
    raw_lufs = data.get("target_loudness")
    if isinstance(raw_lufs, (int, float)) and -70.0 <= float(raw_lufs) <= 0.0:
        sanitized["target_loudness"] = float(raw_lufs)
    else:
        sanitized["target_loudness"] = defaults["target_loudness"]

    # target_true_peak (-20.0 a 0.0 dBTP)
    raw_tp = data.get("target_true_peak")
    if isinstance(raw_tp, (int, float)) and -20.0 <= float(raw_tp) <= 0.0:
        sanitized["target_true_peak"] = float(raw_tp)
    else:
        sanitized["target_true_peak"] = defaults["target_true_peak"]

    # target_lra (1.0 a 50.0 LU)
    raw_lra = data.get("target_lra")
    if isinstance(raw_lra, (int, float)) and 1.0 <= float(raw_lra) <= 50.0:
        sanitized["target_lra"] = float(raw_lra)
    else:
        sanitized["target_lra"] = defaults["target_lra"]

    # output_folder
    raw_out = data.get("output_folder")
    if isinstance(raw_out, str):
        sanitized["output_folder"] = raw_out
    else:
        sanitized["output_folder"] = defaults["output_folder"]

    # current_preset
    raw_preset = data.get("current_preset")
    if isinstance(raw_preset, str) and raw_preset.strip():
        sanitized["current_preset"] = raw_preset.strip()
    else:
        sanitized["current_preset"] = defaults["current_preset"]

    # advanced_expanded
    raw_adv = data.get("advanced_expanded")
    if isinstance(raw_adv, bool):
        sanitized["advanced_expanded"] = raw_adv
    else:
        sanitized["advanced_expanded"] = defaults["advanced_expanded"]

    # overwrite_choice
    if "overwrite_choice" in data:
        raw_ow = data.get("overwrite_choice")
        if raw_ow in VALID_OVERWRITE_CHOICES or raw_ow is None:
            sanitized["overwrite_choice"] = raw_ow
        else:
            sanitized["overwrite_choice"] = defaults["overwrite_choice"]
    else:
        sanitized["overwrite_choice"] = defaults["overwrite_choice"]

    # overwrite_apply_all
    raw_ow_all = data.get("overwrite_apply_all")
    if isinstance(raw_ow_all, bool):
        sanitized["overwrite_apply_all"] = raw_ow_all
    else:
        sanitized["overwrite_apply_all"] = defaults["overwrite_apply_all"]

    return sanitized


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Carrega as configurações a partir do caminho informado ou do local padrão.
    
    Garante que:
    1. Se o arquivo não existir, retorna os valores padrão sem erro.
    2. Se o arquivo estiver corrompido ou malformado, captura a exceção,
       registra em log e retorna os valores padrão de maneira segura.
    3. Se houver valores parciais ou tipos inválidos, realiza fallback
       seguro para os padrões.
    """
    target_path = Path(config_path) if config_path is not None else get_default_config_path()

    if not target_path.is_file():
        logger.info(
            "Arquivo de configuração não encontrado em '%s'. Utilizando configurações padrão.",
            target_path,
        )
        return get_default_config()

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        logger.debug("Configurações lidas com sucesso de '%s'.", target_path)
        return sanitize_config(raw_data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning(
            "Arquivo de configuração corrompido em '%s' (%s). Restaurando configurações padrão.",
            target_path,
            exc,
        )
        return get_default_config()
    except OSError as exc:
        logger.warning(
            "Erro de E/S ao ler arquivo de configuração '%s': %s. Restaurando configurações padrão.",
            target_path,
            exc,
        )
        return get_default_config()


def save_config(config: dict[str, Any], config_path: str | Path | None = None) -> bool:
    """Salva o dicionário de configurações em arquivo JSON no disco.
    
    Cria os diretórios pai caso ainda não existam. Retorna True em caso de
    sucesso e False caso ocorra erro de permissão ou E/S.
    """
    target_path = Path(config_path) if config_path is not None else get_default_config_path(check_portable=False)

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        sanitized = sanitize_config(config)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(sanitized, f, indent=2, ensure_ascii=False)
        logger.debug("Configurações salvas com sucesso em '%s'.", target_path)
        return True
    except OSError as exc:
        logger.error(
            "Não foi possível salvar configurações em '%s': %s",
            target_path,
            exc,
        )
        return False