"""Painel Inspetor — Detalhes da faixa selecionada e configurações avançadas."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QGroupBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QSizePolicy,
    QSpacerItem,
)

from .constants import UIStrings, Defaults


class InspectorPanel(QWidget):
    """Painel lateral/inferior mostrando métricas da faixa selecionada e controles de loudness."""

    # Sinais
    preset_changed = Signal(str)           # nome do preset
    target_loudness_changed = Signal(float)
    target_true_peak_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._current_track_data: dict | None = None
        self._setup_ui()
        self._connect_signals()
        self.clear_selection()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # --------------------------------------------------------------
        # Cabeçalho: "Faixa Selecionada"
        # --------------------------------------------------------------
        header = QLabel(UIStrings.INSPECTOR_TITLE)
        header.setProperty("heading", True)
        layout.addWidget(header)

        # --------------------------------------------------------------
        # Grid de Métricas Lidas
        # --------------------------------------------------------------
        metrics_group = QGroupBox(UIStrings.INSPECTOR_METRICS_GROUP)
        metrics_layout = QGridLayout(metrics_group)
        metrics_layout.setContentsMargins(16, 20, 16, 16)
        metrics_layout.setHorizontalSpacing(24)
        metrics_layout.setVerticalSpacing(10)

        # Labels de métricas
        self._metric_labels = {}
        metrics_def = [
            ("lufs", UIStrings.INSPECTOR_METRICS["lufs"], "—"),
            ("true_peak", UIStrings.INSPECTOR_METRICS["true_peak"], "—"),
            ("lra", UIStrings.INSPECTOR_METRICS["lra"], "—"),
            ("duration", UIStrings.INSPECTOR_METRICS["duration"], "—"),
            ("sample_rate", UIStrings.INSPECTOR_METRICS["sample_rate"], "—"),
            ("bit_depth", UIStrings.INSPECTOR_METRICS["bit_depth"], "—"),
            ("bitrate", UIStrings.INSPECTOR_METRICS["bitrate"], "—"),
            ("format", UIStrings.INSPECTOR_METRICS["format"], "—"),
        ]

        for i, (key, label_text, default) in enumerate(metrics_def):
            row = i // 2
            col = (i % 2) * 2

            lbl = QLabel(label_text)
            lbl.setProperty("subheading", True)
            lbl.setWordWrap(True)
            lbl.setToolTip(UIStrings.INSPECTOR_METRIC_TOOLTIPS.get(key, ""))
            metrics_layout.addWidget(lbl, row, col)

            val = QLabel(default)
            val.setProperty("metric", True)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val.setMinimumWidth(150)
            val.setWordWrap(True)
            metrics_layout.addWidget(val, row, col + 1)

            self._metric_labels[key] = val

        # Stretch na última coluna
        metrics_layout.setColumnStretch(3, 1)
        layout.addWidget(metrics_group)

        # --------------------------------------------------------------
        # Divisor visual
        # --------------------------------------------------------------
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: #3F3F46; border: none; height: 1px;")
        layout.addWidget(divider)

        # --------------------------------------------------------------
        # Configuração de Normalização
        # --------------------------------------------------------------
        config_group = QGroupBox(UIStrings.INSPECTOR_CONFIG_GROUP)
        config_layout = QVBoxLayout(config_group)
        config_layout.setContentsMargins(16, 20, 16, 16)
        config_layout.setSpacing(12)

        # Preset Selector
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(16)
        preset_lbl = QLabel(UIStrings.INSPECTOR_PRESET_LABEL)
        preset_lbl.setProperty("subheading", True)
        preset_lbl.setFixedWidth(70)
        preset_lbl.setToolTip(UIStrings.INSPECTOR_PRESET_TOOLTIP)
        preset_layout.addWidget(preset_lbl)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(UIStrings.INSPECTOR_PRESETS)
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.setToolTip(UIStrings.INSPECTOR_PRESET_TOOLTIP)
        preset_layout.addWidget(self.preset_combo, 1)
        config_layout.addLayout(preset_layout)

        # Painel Avançado Expansível
        self.advanced_group = QGroupBox(UIStrings.INSPECTOR_ADVANCED_GROUP)
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        adv_layout = QGridLayout(self.advanced_group)
        adv_layout.setContentsMargins(16, 20, 16, 16)
        adv_layout.setHorizontalSpacing(24)
        adv_layout.setVerticalSpacing(12)

        # Loudness Alvo
        loud_lbl = QLabel(UIStrings.INSPECTOR_LOUDNESS_LABEL)
        loud_lbl.setProperty("subheading", True)
        loud_lbl.setToolTip(UIStrings.INSPECTOR_LOUDNESS_TOOLTIP)
        adv_layout.addWidget(loud_lbl, 0, 0)

        self.target_loudness = QDoubleSpinBox()
        self.target_loudness.setRange(UIStrings.INSPECTOR_LOUDNESS_MIN, UIStrings.INSPECTOR_LOUDNESS_MAX)
        self.target_loudness.setSingleStep(UIStrings.INSPECTOR_LOUDNESS_STEP)
        self.target_loudness.setDecimals(1)
        self.target_loudness.setValue(UIStrings.INSPECTOR_LOUDNESS_DEFAULT)
        self.target_loudness.setSuffix(" LUFS")
        self.target_loudness.setToolTip(UIStrings.INSPECTOR_LOUDNESS_TOOLTIP)
        self.target_loudness.setMinimumWidth(140)
        adv_layout.addWidget(self.target_loudness, 0, 1)

        # True Peak Alvo
        tp_lbl = QLabel(UIStrings.INSPECTOR_TRUE_PEAK_LABEL)
        tp_lbl.setProperty("subheading", True)
        tp_lbl.setToolTip(UIStrings.INSPECTOR_TRUE_PEAK_TOOLTIP)
        adv_layout.addWidget(tp_lbl, 1, 0)

        self.target_true_peak = QDoubleSpinBox()
        self.target_true_peak.setRange(UIStrings.INSPECTOR_TRUE_PEAK_MIN, UIStrings.INSPECTOR_TRUE_PEAK_MAX)
        self.target_true_peak.setSingleStep(UIStrings.INSPECTOR_TRUE_PEAK_STEP)
        self.target_true_peak.setDecimals(1)
        self.target_true_peak.setValue(UIStrings.INSPECTOR_TRUE_PEAK_DEFAULT)
        self.target_true_peak.setSuffix(" dBTP")
        self.target_true_peak.setToolTip(UIStrings.INSPECTOR_TRUE_PEAK_TOOLTIP)
        self.target_true_peak.setMinimumWidth(140)
        adv_layout.addWidget(self.target_true_peak, 1, 1)

        # LRA Alvo (opcional, apenas exibição informativa)
        lra_lbl = QLabel(UIStrings.INSPECTOR_LRA_LABEL)
        lra_lbl.setProperty("subheading", True)
        lra_lbl.setToolTip(UIStrings.INSPECTOR_LRA_TOOLTIP)
        adv_layout.addWidget(lra_lbl, 2, 0)

        self.target_lra = QDoubleSpinBox()
        self.target_lra.setRange(1.0, 20.0)
        self.target_lra.setSingleStep(1.0)
        self.target_lra.setDecimals(1)
        self.target_lra.setValue(UIStrings.INSPECTOR_LRA_DEFAULT)
        self.target_lra.setSuffix(" LU")
        self.target_lra.setEnabled(False)  # Fixado em 11 LU por enquanto
        self.target_lra.setToolTip(UIStrings.INSPECTOR_LRA_TOOLTIP)
        self.target_lra.setMinimumWidth(140)
        adv_layout.addWidget(self.target_lra, 2, 1)

        adv_layout.setColumnStretch(2, 1)
        config_layout.addWidget(self.advanced_group)

        layout.addWidget(config_group)

        # --------------------------------------------------------------
        # Espaçador final
        # --------------------------------------------------------------
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    def _connect_signals(self) -> None:
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        self.target_loudness.valueChanged.connect(self.target_loudness_changed.emit)
        self.target_true_peak.valueChanged.connect(self.target_true_peak_changed.emit)
        self.advanced_group.toggled.connect(self._on_advanced_toggled)

    def _on_preset_changed(self, text: str) -> None:
        """Atualiza spinboxes conforme preset selecionado."""
        presets = {
            UIStrings.INSPECTOR_PRESETS[0]: (Defaults.TARGET_LOUDNESS_STREAMING, Defaults.TARGET_TRUE_PEAK_DEFAULT),
            UIStrings.INSPECTOR_PRESETS[1]: (Defaults.TARGET_LOUDNESS_CAR, Defaults.TARGET_TRUE_PEAK_CAR),
            UIStrings.INSPECTOR_PRESETS[2]: (Defaults.TARGET_LOUDNESS_ARCHIVE, Defaults.TARGET_TRUE_PEAK_ARCHIVE),
        }
        if text in presets:
            loud, tp = presets[text]
            self.target_loudness.blockSignals(True)
            self.target_true_peak.blockSignals(True)
            self.target_loudness.setValue(loud)
            self.target_true_peak.setValue(tp)
            self.target_loudness.blockSignals(False)
            self.target_true_peak.blockSignals(False)
            # Emite sinais manualmente para notificar listeners
            self.target_loudness_changed.emit(loud)
            self.target_true_peak_changed.emit(tp)
        self.preset_changed.emit(text)

    def _on_advanced_toggled(self, checked: bool) -> None:
        # Animação suave seria ideal, mas Qt não tem built-in para GroupBox
        pass

    # ------------------------------------------------------------------
    # API Pública
    # ------------------------------------------------------------------
    def set_track_data(self, track_data: dict) -> None:
        """Preenche o painel com dados da faixa selecionada."""
        self._current_track_data = track_data

        # Atualiza métricas
        lufs = track_data.get("lufs", 0.0)
        tp = track_data.get("true_peak", 0.0)

        self._metric_labels["lufs"].setText(f"{lufs:.1f}")
        self._metric_labels["lufs"].setProperty("status", "ok" if lufs <= -14.0 else "warn")
        self._metric_labels["true_peak"].setText(f"{tp:.1f}")
        self._metric_labels["true_peak"].setProperty("status", "ok" if tp <= -1.0 else "warn")
        self._metric_labels["lra"].setText(f"{track_data.get('lra', 0.0):.1f}")
        self._metric_labels["duration"].setText(track_data.get("duration", "—"))
        self._metric_labels["sample_rate"].setText(f"{track_data.get('sample_rate', 0)} Hz" if track_data.get('sample_rate') else "—")
        self._metric_labels["bit_depth"].setText(f"{track_data.get('bit_depth', 0)} bit" if track_data.get('bit_depth') else "—")
        self._metric_labels["bitrate"].setText(track_data.get("bitrate", "—"))
        self._metric_labels["format"].setText(track_data.get("format", "—").upper())

        # Força refresh de estilo
        for lbl in self._metric_labels.values():
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    def clear_selection(self) -> None:
        """Limpa o painel quando nenhuma faixa está selecionada."""
        self._current_track_data = None
        for lbl in self._metric_labels.values():
            lbl.setText("—")
            lbl.setProperty("status", "")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    def get_current_settings(self) -> dict:
        """Retorna as configurações atuais de normalização."""
        return {
            "preset": self.preset_combo.currentText(),
            "target_loudness": self.target_loudness.value(),
            "target_true_peak": self.target_true_peak.value(),
            "target_lra": self.target_lra.value(),
            "advanced_expanded": self.advanced_group.isChecked(),
        }

    def set_preset(self, preset_text: str) -> None:
        """Define o preset programaticamente (para sincronizar com toolbar)."""
        self.preset_combo.blockSignals(True)
        index = self.preset_combo.findText(preset_text)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)
        self.preset_combo.blockSignals(False)