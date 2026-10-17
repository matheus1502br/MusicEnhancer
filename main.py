import sys
import logging
import traceback
from PySide6.QtWidgets import QApplication

# Configuração de Logs (sobrescreve o arquivo a cada execução com mode='w')
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("musicenhancer.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("MusicEnhancer")

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Exceção não tratada capturada no arranque:", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

logger.info("=== Inicializando MusicEnhancer ===")

# Inicialização do QApplication
app = QApplication(sys.argv)

try:
    # Carregamento de configurações
    logger.debug("Lendo configurações do QSettings")
    
    load_config()

    # Carregamento de estilos QSS
    logger.debug("Carregando estilos QSS")
    from ui.styles import apply_styles
    apply_styles()

    # Instanciação do MainWindow
    logger.debug("Instanciando MainWindow")
    from mainwindow import MainWindow
    window = MainWindow()
    window.show()

    # Entrada no loop de eventos
    logger.debug("Entrando no loop de eventos")
    sys.exit(app.exec())
except Exception as e:
    logger.exception("Erro crítico durante a inicialização:")
    sys.exit(1)