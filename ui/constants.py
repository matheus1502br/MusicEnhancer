"""Constantes centralizadas do MusicEnhancer — strings PT-BR, chaves de settings, atalhos."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

# ============================================================
# STRINGS DA INTERFACE (PT-BR)
# ============================================================

class UIStrings:
    """Todas as strings visuais do usuário em um só lugar."""

    # Janela / Título
    APP_NAME = "MusicEnhancer"
    WINDOW_TITLE = "MusicEnhancer — Normalização de Loudness EBU R128"

    # Toolbar
    BTN_ADD_FILES = "+ Adicionar Arquivos"
    BTN_ADD_FOLDER = "+ Adicionar Pasta"
    TOOLTIP_ADD_FILES = "Adicionar arquivos de áudio individuais (Ctrl+O)"
    TOOLTIP_ADD_FOLDER = "Adicionar todos os arquivos de uma pasta recursivamente (Ctrl+Shift+O)"
    LBL_PRESET = "Preset:"
    TOOLTIP_PRESET = "Selecione um preset de loudness alvo"
    LBL_SELECTION_COUNT = "{selected} de {total} selecionadas"

    # Tabela — Cabeçalhos
    TABLE_HEADERS = [
        "",                    # Checkbox
        "Nome da Faixa",
        "Duração",
        "Formato",
        "LUFS Atual",
        "Pico Real (dBTP)",
        "Taxa de Bits",
        "Status",
    ]

    # Tabela — Tooltips dos cabeçalhos
    TABLE_HEADER_TOOLTIPS = {
        0: "Marcar/desmarcar todas as faixas (clique no cabeçalho)",
        1: "Nome do arquivo de áudio",
        2: "Duração da faixa (minutos:segundos)",
        3: "Formato do contêiner (MP3, FLAC, WAV, M4A, AAC)",
        4: "Loudness integrado medido (LUFS). Verde ≤ -14,0 LUFS (pronto para streaming)",
        5: "True Peak máximo medido (dBTP). Laranja > -1,0 dBTP (risco de clipping em lossy)",
        6: "Taxa de bits do arquivo original",
        7: "Estado do processamento: Analisado, Pico Elevado, Copiado (Bypass), Concluído, Erro",
    }

    # Tabela — Empty State
    EMPTY_STATE_TITLE = "Nenhuma faixa na lista"
    EMPTY_STATE_MESSAGE = "Arraste seus arquivos de áudio aqui\nou clique em '+ Adicionar Arquivos'"

    # Tabela — Badges de status (texto exibido)
    STATUS_TEXT = {
        "pending": "Pendente",
        "analyzed": "Analisado",
        "peak_warn": "Pico Elevado",
        "completed": "Concluído",
        "bypass": "Copiado (Bypass)",
        "error": "Erro",
    }

    # Tabela — Tooltips dos badges
    STATUS_TOOLTIPS = {
        "pending": "Aguardando análise de loudness",
        "analyzed": "Loudness analisado; pronto para normalização",
        "peak_warn": "True Peak acima de -1,0 dBTP — risco de clipping ao converter para MP3/AAC",
        "completed": "Normalização aplicada com sucesso; metadados copiados",
        "bypass": "Já dentro do alvo (-14,0 LUFS ±0,5; TP ≤ -1,0 dBTP); arquivo copiado sem recodificação",
        "error": "Falha no processamento — passe o mouse para ver detalhes",
    }

    # Inspetor — Cabeçalhos e grupos
    INSPECTOR_TITLE = "Faixa Selecionada"
    INSPECTOR_METRICS_GROUP = "Métricas Analisadas"
    INSPECTOR_CONFIG_GROUP = "Configuração de Normalização"
    INSPECTOR_ADVANCED_GROUP = "Ajustes Avançados"

    # Inspetor — Labels de métricas
    INSPECTOR_METRICS = {
        "lufs": "Loudness Integrado (LUFS)",
        "true_peak": "True Peak (dBTP)",
        "lra": "LRA (LU)",
        "duration": "Duração",
        "sample_rate": "Taxa de Amostragem",
        "bit_depth": "Profundidade de Bits",
        "bitrate": "Taxa de Bits",
        "format": "Formato",
    }

    # Inspetor — Tooltips das métricas
    INSPECTOR_METRIC_TOOLTIPS = {
        "lufs": "Loudness integrado (EBU R128). Alvo de streaming: -14,0 LUFS",
        "true_peak": "Pico real entre amostras. Limite seguro: ≤ -1,0 dBTP",
        "lra": "Loudness Range — variação dinâmica da faixa",
        "duration": "Duração total da faixa",
        "sample_rate": "Taxa de amostragem (Hz). Ex.: 44100, 48000, 96000",
        "bit_depth": "Profundidade de bits por amostra. Ex.: 16, 24, 32",
        "bitrate": "Taxa de bits média do arquivo original",
        "format": "Formato do contêiner de áudio",
    }

    # Inspetor — Configuração
    INSPECTOR_PRESET_LABEL = "Preset"
    INSPECTOR_PRESET_TOOLTIP = "Selecione um preset de loudness alvo"
    INSPECTOR_PRESETS = [
        "Streaming (-14 LUFS, -1,0 dBTP)",
        "Carro / Festa (-11 LUFS, -1,0 dBTP)",
        "Preservado / Arquivo (-18 LUFS, -1,5 dBTP)",
        "Personalizado…",
    ]

    INSPECTOR_LOUDNESS_LABEL = "Loudness Alvo (LUFS)"
    INSPECTOR_LOUDNESS_TOOLTIP = "Loudness integrado alvo segundo EBU R128 (padrão streaming: -14,0 LUFS)"
    INSPECTOR_LOUDNESS_MIN = -24.0
    INSPECTOR_LOUDNESS_MAX = -9.0
    INSPECTOR_LOUDNESS_STEP = 0.5
    INSPECTOR_LOUDNESS_DEFAULT = -14.0

    INSPECTOR_TRUE_PEAK_LABEL = "Pico Máximo True Peak (dBTP)"
    INSPECTOR_TRUE_PEAK_TOOLTIP = "Limite de True Peak para evitar clipping em conversão lossy (padrão: -1,0 dBTP)"
    INSPECTOR_TRUE_PEAK_MIN = -3.0
    INSPECTOR_TRUE_PEAK_MAX = -0.5
    INSPECTOR_TRUE_PEAK_STEP = 0.1
    INSPECTOR_TRUE_PEAK_DEFAULT = -1.0

    INSPECTOR_LRA_LABEL = "LRA Alvo (LU)"
    INSPECTOR_LRA_TOOLTIP = "Loudness Range alvo (fixo em 11 LU para loudnorm linear)"
    INSPECTOR_LRA_DEFAULT = 11.0

    # Rodapé (Footer)
    FOOTER_OUTPUT_LABEL = "Saída:"
    FOOTER_OUTPUT_PLACEHOLDER = "Selecione a pasta de saída…"
    FOOTER_BROWSE_BTN = "Procurar…"
    FOOTER_PROGRESS_LABEL = "Progresso:"
    FOOTER_PROGRESS_FORMAT = "Processando {current} de {total} faixas…"
    FOOTER_CANCEL_BTN = "Cancelar Operação"
    FOOTER_START_BATCH_BTN = "INICIAR LOTE"
    FOOTER_START_BATCH_TOOLTIP = "Iniciar normalização das faixas selecionadas (Ctrl+Enter)"

    # Diálogos / Mensagens
    DLG_ADD_FILES_TITLE = "Adicionar Arquivos de Áudio"
    DLG_ADD_FILES_FILTER = "Áudio (*.mp3 *.flac *.wav *.m4a *.aac);;Todos (*.*)"
    DLG_ADD_FOLDER_TITLE = "Adicionar Pasta"

    DLG_NO_OUTPUT_FOLDER_TITLE = "Pasta de saída não definida"
    DLG_NO_OUTPUT_FOLDER_MSG = "Selecione a pasta de saída antes de iniciar o lote."

    DLG_NO_SELECTION_TITLE = "Nenhuma faixa selecionada"
    DLG_NO_SELECTION_MSG = "Marque ao menos uma faixa na tabela para iniciar o processamento em lote."

    DLG_CONFIRM_OVERWRITE_TITLE = "Arquivos já existentes na pasta de destino"
    DLG_CONFIRM_OVERWRITE_MSG = (
        "{count} arquivo(s) com o mesmo nome já existem na pasta de saída.\n\n"
        "Como deseja proceder?"
    )
    DLG_OVERWRITE_REPLACE_ALL = "Substituir Todos"
    DLG_OVERWRITE_SKIP = "Ignorar Existentes"
    DLG_OVERWRITE_RENAME = "Renomear com Sufixo"
    DLG_OVERWRITE_APPLY_ALL = "Aplicar a todos"

    DLG_WRITE_PERMISSION_TITLE = "Sem permissão de escrita"
    DLG_WRITE_PERMISSION_MSG = "Não é possível gravar na pasta de saída selecionada:\n{path}\n\nVerifique as permissões e tente novamente."

    DLG_DISK_SPACE_TITLE = "Espaço em disco insuficiente"
    DLG_DISK_SPACE_MSG = "Espaço livre: {free} MB\nEstimado necessário: {needed} MB\n\nLibere espaço e tente novamente."

    MSG_ANALYZING = "Analisando {count} arquivo(s)…"
    MSG_SCANNING = "Escaneando pasta: {path}…"
    MSG_ANALYSIS_DONE = "Análise concluída."
    MSG_SCAN_DONE = "Escaneamento concluído."
    MSG_SCAN_NO_FILES = "Nenhum arquivo de áudio suportado encontrado na pasta."
    MSG_BATCH_STARTED = "Processando lote…"
    MSG_BATCH_DONE = "Normalização concluída: {success}/{total} faixas processadas."
    MSG_BATCH_DONE_ERRORS = "Concluído com erros: {success}/{total} faixas. Erros: {errors}"
    MSG_BATCH_CANCELLED = "Lote cancelado pelo usuário."
    MSG_ANALYSIS_CANCELLED = "Análise cancelada."
    MSG_READY = "Pronto. Arraste arquivos ou use 'Adicionar Arquivos'."

    # Status Bar
    STATUSBAR_READY = "Pronto. Arraste arquivos ou use 'Adicionar Arquivos'."

    # About / Versão
    ABOUT_TITLE = "Sobre o MusicEnhancer"
    ABOUT_TEXT = (
        "MusicEnhancer v0.3.0\n"
        "Normalização de loudness EBU R128 / -14 LUFS\n"
        "Processamento offline em lote com FFmpeg\n\n"
        "Desenvolvido para engenheiros de áudio e produtores."
    )


# ============================================================
# CHAVES DE QSETTINGS
# ============================================================

class SettingsKeys:
    """Chaves para QSettings — evita typos e facilita manutenção."""

    # Geometria / Layout
    WINDOW_GEOMETRY = "window/geometry"
    WINDOW_STATE = "window/state"
    SPLITTER_STATE = "splitter/state"
    TABLE_HEADER_STATE = "table/headerState"

    # Preferências de usuário
    OUTPUT_FOLDER = "preferences/outputFolder"
    CURRENT_PRESET = "preferences/currentPreset"
    ADVANCED_EXPANDED = "preferences/advancedExpanded"
    TARGET_LOUDNESS = "preferences/targetLoudness"
    TARGET_TRUE_PEAK = "preferences/targetTruePeak"

    # Overwrite dialog
    OVERWRITE_CHOICE = "batch/overwriteChoice"
    OVERWRITE_APPLY_ALL = "batch/overwriteApplyAll"


# ============================================================
# ATALHOS DE TECLADO (QKeySequence)
# ============================================================

class Shortcuts:
    """Atalhos globais da aplicação."""

    ADD_FILES = QKeySequence(QKeySequence.StandardKey.Open)  # Ctrl+O
    ADD_FOLDER = QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier, Qt.Key.Key_O)  # Ctrl+Shift+O
    REMOVE_SELECTED = QKeySequence(Qt.Key.Key_Delete)  # Delete
    REMOVE_SELECTED_ALT = QKeySequence(Qt.Key.Key_Backspace)  # Backspace
    START_BATCH = QKeySequence(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_Return)  # Ctrl+Enter
    START_BATCH_ALT = QKeySequence(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_Enter)  # Ctrl+Enter (numpad)
    CANCEL_BATCH = QKeySequence(Qt.Key.Key_Escape)  # Esc


# ============================================================
# VALORES PADRÃO / CONSTANTES DE NEGÓCIO
# ============================================================

class Defaults:
    """Valores padrão do domínio."""

    # Loudness
    TARGET_LOUDNESS_STREAMING = -14.0
    TARGET_LOUDNESS_CAR = -11.0
    TARGET_LOUDNESS_ARCHIVE = -18.0

    TARGET_TRUE_PEAK_DEFAULT = -1.0
    TARGET_TRUE_PEAK_CAR = -1.0
    TARGET_TRUE_PEAK_ARCHIVE = -1.5

    TARGET_LRA = 11.0

    # Bypass thresholds
    BYPASS_LUFS_MIN = -14.5
    BYPASS_LUFS_MAX = -13.5
    BYPASS_TP_MAX = -1.0

    # MP3 bitrate clamp
    MP3_BITRATE_MIN = 192  # kbps
    MP3_BITRATE_MAX = 320  # kbps

    # Janela
    WINDOW_MIN_WIDTH = 900
    WINDOW_MIN_HEIGHT = 600
    WINDOW_DEFAULT_WIDTH = 1024
    WINDOW_DEFAULT_HEIGHT = 680

    # Tabela
    TABLE_MIN_HEIGHT = 200
    TABLE_ROW_HEIGHT = 44

    # Inspetor
    INSPECTOR_MAX_HEIGHT = 300

    # Splitter
    SPLITTER_SIZES = [540, 180]  # [table, inspector]
    SPLITTER_STRETCH_TABLE = 3
    SPLITTER_STRETCH_INSPECTOR = 1


# ============================================================
# EXTENSÕES SUPORTADAS
# ============================================================

SUPPORTED_AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".aac"}

# Mapas de formato para exibição
FORMAT_DISPLAY_NAME = {
    ".mp3": "MP3",
    ".flac": "FLAC",
    ".wav": "WAV",
    ".m4a": "M4A",
    ".aac": "AAC",
}