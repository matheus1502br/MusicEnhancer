"""Testes automatizados para o sistema de inicialização e configurações."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.settings import (
    DEFAULT_CONFIG,
    get_default_config,
    get_default_config_path,
    get_user_config_dir,
    load_config,
    sanitize_config,
    save_config,
)
from ui.constants import Shortcuts


class TestSettingsDefaults:
    """Validação dos valores padrão e tipos."""

    def test_default_config_contains_domain_values(self) -> None:
        defaults = get_default_config()
        assert defaults["target_loudness"] == -14.0
        assert defaults["target_true_peak"] == -1.0
        assert defaults["target_lra"] == 11.0
        assert defaults["output_folder"] == ""
        assert defaults["current_preset"] == "Streaming (-14 LUFS, -1,0 dBTP)"
        assert defaults["advanced_expanded"] is False
        assert defaults["overwrite_choice"] == "rename"
        assert defaults["overwrite_apply_all"] is False

    def test_get_default_config_returns_independent_copy(self) -> None:
        cfg1 = get_default_config()
        cfg2 = get_default_config()
        cfg1["target_loudness"] = -16.0
        assert cfg2["target_loudness"] == -14.0
        assert DEFAULT_CONFIG["target_loudness"] == -14.0


class TestSettingsLoad:
    """Validação do comportamento de carregamento e resiliência."""

    def test_load_config_when_file_not_found(self, tmp_path: Path) -> None:
        missing_file = tmp_path / "non_existent_config.json"
        loaded = load_config(missing_file)
        assert loaded == get_default_config()

    def test_load_config_valid_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        data = {
            "target_loudness": -16.0,
            "target_true_peak": -1.5,
            "target_lra": 14.0,
            "output_folder": str(tmp_path / "output"),
            "current_preset": "Preservado / Arquivo (-18 LUFS, -1,5 dBTP)",
            "advanced_expanded": True,
            "overwrite_choice": "skip",
            "overwrite_apply_all": True,
        }
        config_file.write_text(json.dumps(data), encoding="utf-8")

        loaded = load_config(config_file)
        assert loaded["target_loudness"] == -16.0
        assert loaded["target_true_peak"] == -1.5
        assert loaded["target_lra"] == 14.0
        assert loaded["output_folder"] == str(tmp_path / "output")
        assert loaded["current_preset"] == "Preservado / Arquivo (-18 LUFS, -1,5 dBTP)"
        assert loaded["advanced_expanded"] is True
        assert loaded["overwrite_choice"] == "skip"
        assert loaded["overwrite_apply_all"] is True

    def test_load_config_corrupted_json(self, tmp_path: Path) -> None:
        corrupted_file = tmp_path / "corrupted.json"
        corrupted_file.write_text("{invalid json, truncated...", encoding="utf-8")

        loaded = load_config(corrupted_file)
        # Deve retornar defaults sem lançar exceção
        assert loaded == get_default_config()

    def test_load_config_non_dict_json(self, tmp_path: Path) -> None:
        list_file = tmp_path / "list_config.json"
        list_file.write_text('["not", "a", "dictionary"]', encoding="utf-8")

        loaded = load_config(list_file)
        assert loaded == get_default_config()

    def test_load_config_sanitizes_invalid_types_and_ranges(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bad_types.json"
        data = {
            "target_loudness": "texto_invalido",  # tipo incorreto
            "target_true_peak": 5.0,              # acima de 0.0 dBTP (fora da faixa segura)
            "target_lra": -5.0,                  # negativo (inválido)
            "output_folder": 12345,               # não é string
            "current_preset": "",                 # string vazia
            "advanced_expanded": "sim",          # não é booleano
            "overwrite_choice": "destruir_tudo",  # opção inválida
            "overwrite_apply_all": 99,            # não é booleano
        }
        config_file.write_text(json.dumps(data), encoding="utf-8")

        loaded = load_config(config_file)
        defaults = get_default_config()

        assert loaded["target_loudness"] == defaults["target_loudness"]
        assert loaded["target_true_peak"] == defaults["target_true_peak"]
        assert loaded["target_lra"] == defaults["target_lra"]
        assert loaded["output_folder"] == defaults["output_folder"]
        assert loaded["current_preset"] == defaults["current_preset"]
        assert loaded["advanced_expanded"] == defaults["advanced_expanded"]
        assert loaded["overwrite_choice"] == defaults["overwrite_choice"]
        assert loaded["overwrite_apply_all"] == defaults["overwrite_apply_all"]

    def test_load_config_fills_missing_keys(self, tmp_path: Path) -> None:
        config_file = tmp_path / "partial.json"
        data = {"target_loudness": -11.0}
        config_file.write_text(json.dumps(data), encoding="utf-8")

        loaded = load_config(config_file)
        assert loaded["target_loudness"] == -11.0
        # Demais chaves devem conter os padrões
        assert loaded["target_true_peak"] == -1.0
        assert loaded["overwrite_choice"] == "rename"


class TestSettingsSave:
    """Validação da gravação de configurações."""

    def test_save_config_creates_parent_directories(self, tmp_path: Path) -> None:
        nested_file = tmp_path / "nested" / "subfolder" / "config.json"
        cfg = get_default_config()
        cfg["target_loudness"] = -12.5

        success = save_config(cfg, nested_file)
        assert success is True
        assert nested_file.is_file()

        reloaded = load_config(nested_file)
        assert reloaded["target_loudness"] == -12.5

    def test_save_and_reload_roundtrip(self, tmp_path: Path) -> None:
        target = tmp_path / "roundtrip.json"
        cfg = get_default_config()
        cfg["current_preset"] = "Carro / Festa (-11 LUFS, -1,0 dBTP)"
        cfg["advanced_expanded"] = True

        assert save_config(cfg, target) is True
        reloaded = load_config(target)
        assert reloaded["current_preset"] == "Carro / Festa (-11 LUFS, -1,0 dBTP)"
        assert reloaded["advanced_expanded"] is True


class TestPathAndEnvironmentIndependence:
    """Validação de diretórios do usuário e independência do CWD."""

    def test_user_config_dir_is_not_empty(self) -> None:
        user_dir = get_user_config_dir()
        assert isinstance(user_dir, Path)
        assert "MusicEnhancer" in str(user_dir)

    def test_default_config_path_independent_of_cwd(self, tmp_path: Path) -> None:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Ao mudar de CWD, o caminho padrão deve permanecer absoluto e coerente
            default_path = get_default_config_path(check_portable=False)
            assert default_path.is_absolute()
            assert str(tmp_path) not in str(default_path)
        finally:
            os.chdir(original_cwd)


class TestShortcutsInitialization:
    """Validação de atalhos e segurança multiplataforma."""

    def test_shortcuts_add_files_accessible_without_gui_app(self) -> None:
        # Acesso estático não deve gerar exceção nem abortar processo
        seq = Shortcuts.ADD_FILES
        assert seq is not None
        assert "O" in seq.toString()
