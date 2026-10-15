"""Tema QSS profissional para MusicEnhancer — estética DAW moderna (Dark Mode)."""

STYLESHEET = """
/* ============================================================
   CORE PALETTE — Zinc / Cyan Acoustic
   ============================================================ */
* {
    font-family: "Segoe UI Variable", "Segoe UI", "Inter", "Arial", sans-serif;
    font-size: 13px;
    color: #FAFAFA;                    /* Zinc-50 — Texto Principal */
    background-color: transparent;
    selection-background-color: #06B6D4;  /* Ciano Acústico */
    selection-color: #18181B;              /* Zinc-900 */
}

/* ------------------------------------------------------------
   JANELA PRINCIPAL / WIDGETS BASE
   ------------------------------------------------------------ */
QMainWindow, QWidget {
    background-color: #18181B;          /* Zinc-900 — Fundo Principal */
    border: none;
}

/* ------------------------------------------------------------
   SPLITTERS
   ------------------------------------------------------------ */
QSplitter::handle {
    background-color: #3F3F46;          /* Zinc-700 — Divisor */
    width: 1px;
    height: 1px;
}
QSplitter::handle:hover {
    background-color: #06B6D4;          /* Ciano Acústico */
}

/* ------------------------------------------------------------
   SCROLLBARS — Finas e discretas
   ------------------------------------------------------------ */
QScrollBar:vertical, QScrollBar:horizontal {
    background: transparent;
    width: 8px;
    height: 8px;
    margin: 0;
}
QScrollBar::handle {
    background: #3F3F46;                /* Zinc-700 */
    border-radius: 4px;
    min-height: 30px;
    min-width: 30px;
}
QScrollBar::handle:hover {
    background: #52525B;                /* Zinc-600 */
}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {
    background: none;
    height: 0;
    width: 0;
}

/* ------------------------------------------------------------
   TABELA DE MÚSICAS — QTableView / QTableWidget
   ------------------------------------------------------------ */
MusicTableWidget, QTableView, QTableWidget {
    background-color: #27272A;          /* Zinc-800 — Superfície */
    alternate-background-color: #1F1F23; /* Zinc-850 sutil */
    gridline-color: #3F3F46;            /* Zinc-700 — Divisores */
    border: 1px solid #3F3F46;
    border-radius: 6px;
    outline: none;
    show-decoration-selected: 1;
}

MusicTableWidget::item, QTableView::item, QTableWidget::item {
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #3F3F46;
}

MusicTableWidget::item:selected, QTableView::item:selected, QTableWidget::item:selected {
    background-color: #06B6D4;          /* Ciano Acústico — Seleção */
    color: #18181B;                     /* Zinc-900 */
}

MusicTableWidget::item:hover, QTableView::item:hover, QTableWidget::item:hover {
    background-color: #2A2A2E;          /* Hover sutil */
}

QHeaderView::section {
    background-color: #1F1F23;          /* Cabeçalho levemente mais escuro */
    color: #A1A1AA;                     /* Zinc-400 — Texto Secundário */
    padding: 10px;
    border: none;
    border-bottom: 1px solid #3F3F46;
    border-right: 1px solid #3F3F46;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

QHeaderView::section:last {
    border-right: none;
}

/* Colunas numéricas — alinhamento tabular forçado via delegate,
   mas garantimos fallback visual aqui */
QTableWidgetItem[numeric="true"] {
    text-align: right;
    font-family: "Segoe UI Variable", "JetBrains Mono", "Consolas", monospace;
}

/* ------------------------------------------------------------
   CHECKBOX (coluna de seleção)
   ------------------------------------------------------------ */
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #3F3F46;
    border-radius: 4px;
    background: #27272A;
}
QCheckBox::indicator:hover {
    border-color: #06B6D4;
}
QCheckBox::indicator:checked {
    background-color: #06B6D4;
    border-color: #06B6D4;
    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOSIgdmlld0JveD0iMCAwIDEyIDkiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDQuNUw0LjUgOEwxMSAxIiBzdHJva2U9IiMxODE4MUIiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+Cjwvc3ZnPg==);
}

/* ------------------------------------------------------------
   BOTÕES
   ------------------------------------------------------------ */
QPushButton {
    background-color: #27272A;          /* Zinc-800 */
    color: #FAFAFA;
    border: 1px solid #3F3F46;          /* Zinc-700 */
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #3F3F46;          /* Zinc-700 */
    border-color: #52525B;
}
QPushButton:pressed {
    background-color: #18181B;
    border-color: #06B6D4;
}
QPushButton:disabled {
    background-color: #1F1F23;
    color: #52525B;
    border-color: #3F3F46;
}

/* Botão Primário — Ciano Acústico */
QPushButton[primary="true"] {
    background-color: #06B6D4;
    color: #18181B;
    border: none;
    font-weight: 700;
    letter-spacing: 0.3px;
}
QPushButton[primary="true"]:hover {
    background-color: #0891B2;
}
QPushButton[primary="true"]:pressed {
    background-color: #0E7490;
}
QPushButton[primary="true"]:disabled {
    background-color: #164E63;
    color: #4A4A52;
}

/* Botão Secundário / Perigo */
QPushButton[danger="true"] {
    background-color: transparent;
    color: #EF4444;
    border-color: #EF4444;
}
QPushButton[danger="true"]:hover {
    background-color: #EF4444;
    color: #FAFAFA;
}

/* Botão Flat (toolbar style) */
QPushButton[flat="true"] {
    background: transparent;
    border: none;
    padding: 6px 12px;
    color: #A1A1AA;
}
QPushButton[flat="true"]:hover {
    background: #27272A;
    color: #FAFAFA;
    border-radius: 4px;
}

/* ------------------------------------------------------------
   COMBO BOX — Preset Selector
   ------------------------------------------------------------ */
QComboBox {
    background-color: #27272A;
    color: #FAFAFA;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    padding: 6px 12px;
    padding-right: 32px; /* espaço para seta */
    min-width: 220px;
}
QComboBox:hover {
    border-color: #52525B;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
    subcontrol-origin: padding;
    subcontrol-position: top right;
}
QComboBox::down-arrow {
    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iNyIgdmlld0JveD0iMCAwIDEyIDciIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDFMNiA2TDExIDEiIHN0cm9rZT0iI0ExQTFBQSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz4KPC9zdmc+);
    width: 12px;
    height: 7px;
}
QComboBox QAbstractItemView {
    background-color: #27272A;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    selection-background-color: #06B6D4;
    selection-color: #18181B;
    outline: none;
    padding: 4px;
}
QComboBox QAbstractItemView::item {
    padding: 8px 12px;
    border-radius: 4px;
}
QComboBox QAbstractItemView::item:hover {
    background-color: #3F3F46;
}

/* ------------------------------------------------------------
   SPIN BOX — Loudness / True Peak
   ------------------------------------------------------------ */
QDoubleSpinBox, QSpinBox {
    background-color: #27272A;
    color: #FAFAFA;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    padding: 6px 10px;
    padding-right: 28px;
    font-family: "Segoe UI Variable", "JetBrains Mono", "Consolas", monospace;
}
QDoubleSpinBox:hover, QSpinBox:hover {
    border-color: #52525B;
}
QDoubleSpinBox:focus, QSpinBox:focus {
    border-color: #06B6D4;
}
QDoubleSpinBox::up-button, QSpinBox::up-button,
QDoubleSpinBox::down-button, QSpinBox::down-button {
    background: transparent;
    border: none;
    width: 20px;
    subcontrol-origin: border;
}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {
    background: #3F3F46;
    border-radius: 0 3px 0 0;
}
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {
    border-radius: 0 0 3px 0;
}
QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {
    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iOCIgaGVpZ2h0PSI0IiB2aWV3Qm94PSIwIDAgOCA0IiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPgo8cGF0aCBkPSJNMSAzLjVMNCAwLjVMNyAzLjUiIHN0cm9rZT0iI0ExQTFBQSIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPgo8L3N2Zz4=);
    width: 8px;
    height: 4px;
}
QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {
    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iOCIgaGVpZ2h0PSI0IiB2aWV3Qm94PSIwIDAgOCA0IiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPgo8cGF0aCBkPSJNMSAwLjVMNCAzLjVMNyAwLjUiIHN0cm9rZT0iI0ExQTFBQSIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPgo8L3N2Zz4=);
    width: 8px;
    height: 4px;
}

/* ------------------------------------------------------------
   LINE EDIT / TEXT EDIT — Caminho de saída
   ------------------------------------------------------------ */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #1F1F23;
    color: #FAFAFA;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    padding: 8px 12px;
    selection-background-color: #06B6D4;
    selection-color: #18181B;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover {
    border-color: #52525B;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #06B6D4;
}
QLineEdit:read-only {
    background-color: #18181B;
    color: #71717A;                     /* Zinc-500 */
}

/* ------------------------------------------------------------
   PROGRESS BAR
   ------------------------------------------------------------ */
QProgressBar {
    background-color: #1F1F23;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    text-align: center;
    color: #FAFAFA;
    font-weight: 600;
    height: 22px;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #06B6D4, stop:1 #0891B2);
    border-radius: 5px;
}

/* ------------------------------------------------------------
   GROUP BOX / COLLAPSIBLE SECTION
   ------------------------------------------------------------ */
QGroupBox {
    background-color: #27272A;
    border: 1px solid #3F3F46;
    border-radius: 8px;
    margin-top: 16px;
    padding-top: 16px;
    font-weight: 600;
    color: #FAFAFA;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: 0px;
    padding: 0 8px;
    color: #A1A1AA;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    background-color: #27272A;
}

/* ------------------------------------------------------------
   LABELS — Tipografia utilitária
   ------------------------------------------------------------ */
QLabel[heading="true"] {
    font-size: 15px;
    font-weight: 700;
    color: #FAFAFA;
    letter-spacing: -0.3px;
}
QLabel[subheading="true"] {
    font-size: 12px;
    font-weight: 500;
    color: #A1A1AA;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
QLabel[metric="true"] {
    font-family: "Segoe UI Variable", "JetBrains Mono", "Consolas", monospace;
    font-size: 14px;
    font-weight: 600;
}
QLabel[metric="true"][status="ok"] {
    color: #10B981;                     /* Verde Esmeralda */
}
QLabel[metric="true"][status="warn"] {
    color: #F97316;                     /* Laranja Químico */
}
QLabel[metric="true"][status="error"] {
    color: #EF4444;                     /* Vermelho */
}
QLabel[muted="true"] {
    color: #71717A;                     /* Zinc-500 */
    font-size: 12px;
}

/* ------------------------------------------------------------
   BADGE / STATUS — QLabel com property
   ------------------------------------------------------------ */
QLabel[badge="true"] {
    border-radius: 12px;
    padding: 3px 10px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    qproperty-alignment: AlignCenter;
}
QLabel[badge="true"][status="analyzed"] {
    background-color: #1E3A5F;          /* Azul profundo suave */
    color: #67E8F9;                     /* Cyan-300 */
}
QLabel[badge="true"][status="peak_warn"] {
    background-color: #451A03;          /* Laranja profundo */
    color: #FED7AA;                     /* Orange-200 */
}
QLabel[badge="true"][status="completed"] {
    background-color: #064E3B;          /* Verde profundo */
    color: #6EE7B7;                     /* Emerald-300 */
}
QLabel[badge="true"][status="error"] {
    background-color: #450A0A;          /* Vermelho profundo */
    color: #FCA5A5;                     /* Red-300 */
}
QLabel[badge="true"][status="pending"] {
    background-color: #3F3F46;
    color: #A1A1AA;
}

/* ------------------------------------------------------------
   TOOLTIP
   ------------------------------------------------------------ */
QToolTip {
    background-color: #27272A;
    color: #FAFAFA;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
}

/* ------------------------------------------------------------
   MENU BAR / CONTEXT MENU
   ------------------------------------------------------------ */
QMenuBar {
    background-color: #18181B;
    color: #FAFAFA;
    spacing: 4px;
}
QMenuBar::item {
    padding: 6px 12px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #27272A;
}
QMenu {
    background-color: #27272A;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 8px 24px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #06B6D4;
    color: #18181B;
}
QMenu::separator {
    height: 1px;
    background: #3F3F46;
    margin: 4px 8px;
}

/* ------------------------------------------------------------
   SPLASH / DIALOGS
   ------------------------------------------------------------ */
QDialog {
    background-color: #18181B;
}
QMessageBox {
    background-color: #18181B;
}
QMessageBox QLabel {
    color: #FAFAFA;
}
QMessageBox QPushButton {
    min-width: 80px;
}
"""


def get_stylesheet() -> str:
    """Retorna o QSS completo da aplicação."""
    return STYLESHEET