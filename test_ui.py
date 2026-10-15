import sys
sys.path.insert(0, r"C:\Users\Matheus\Documents\GitHub\MusicEnhancer")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

app = QApplication.instance() or QApplication(sys.argv)

from ui.styles import get_stylesheet
app.setStyleSheet(get_stylesheet())

from ui.main_window import MainWindow
window = MainWindow()
window.show()

# Auto-quit after 2 seconds
QTimer.singleShot(2000, app.quit)

exit_code = app.exec()
print(f"UI Test OK - Exit code: {exit_code}")
sys.exit(exit_code)