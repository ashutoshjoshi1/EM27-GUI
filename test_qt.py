import sys
from PyQt5.QtWidgets import QApplication, QLabel, QWidget

app = QApplication(sys.argv)
window = QWidget()
window.setWindowTitle("PyQt Test")
window.setGeometry(100, 100, 280, 80)
label = QLabel("PyQt is working!", window)
label.move(60, 30)
window.show()
sys.exit(app.exec_())