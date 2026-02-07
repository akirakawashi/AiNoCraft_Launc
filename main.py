import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from src.config import launcherSetting
from src.main_window import MainWindow


def main():
    """Точка входа в приложение"""
    app = QApplication(sys.argv)
    app.setApplicationName("LolCraft Launcher")

    # Установка иконки приложения
    icon_path = launcherSetting.icon
    app.setWindowIcon(QIcon(icon_path))

    # Создание и отображение главного окна
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()