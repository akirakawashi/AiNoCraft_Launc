# from loguru import logger
import webbrowser

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config import javaFunc, urlSetting
from src.form_ui.dialog_form import SettingDialog
from src.style.StyleManager import StyleManager


class GameForm(QWidget):
    """widget for game settings and play button"""

    logout_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    play_requested = pyqtSignal(int)

    def __init__(self, login="", parent=None):
        super().__init__(parent)
        self.login = login
        self.setup_ui()
        self.setup_styles()
        self.update_memory_display()

    def setup_ui(self):
        """Создание интерфейса формы"""

        # Основной layout
        self.main_layout = QVBoxLayout(self)

        self.main_layout.setContentsMargins(50, 370, 50, 10)
        self.main_layout.addStretch(1)

        # Заголовок
        self.title_label = QLabel(f"{self.login}, добро пожаловать на сервер!")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setProperty("class", "title-label")

        # Информация о текущей памяти
        self.memory_info_label = QLabel()
        self.memory_info_label.setAlignment(Qt.AlignCenter)
        self.memory_info_label.setProperty("class", "memory-info")

        button_layout = QHBoxLayout()
        self.game_button = QPushButton("Играть")
        self.game_button.setProperty("class", "button_game")
        self.game_button.setFixedWidth(250)

        # НОВАЯ КНОПКА "Сайт"
        self.site_button = QPushButton("Сайт")
        self.site_button.setProperty("class", "button_site")  # можно задать свой CSS класс
        self.site_button.setFixedWidth(250)

        self.logout_button = QPushButton("Выход")
        self.logout_button.setProperty("class", "button_logout")
        self.logout_button.setFixedWidth(250)

        self.setting_button = QPushButton("Настройки")
        self.setting_button.setProperty("class", "button_settings")
        self.setting_button.setFixedWidth(250)

        button_layout.addWidget(self.game_button)
        button_layout.addSpacing(1)
        button_layout.addWidget(self.setting_button)
        button_layout.addSpacing(1)
        button_layout.addWidget(self.site_button)
        button_layout.addSpacing(1)
        button_layout.addWidget(self.logout_button)
        self.button_layout = button_layout

        self.main_layout.addWidget(self.title_label)
        self.main_layout.addSpacing(10)
        self.main_layout.addWidget(self.memory_info_label)
        self.main_layout.addSpacing(40)
        self.main_layout.addLayout(self.button_layout)
        self.main_layout.addStretch(1)

        self.setup_connections()

    def setup_connections(self):
        """signals connections"""
        self.game_button.clicked.connect(self.on_play_clicked)
        self.logout_button.clicked.connect(self.on_logout_clicked)
        self.setting_button.clicked.connect(self.on_settings_clicked)
        self.site_button.clicked.connect(self.on_site_clicked)

    def on_logout_clicked(self):
        """callback for logout button"""
        self.logout_requested.emit()

    def on_settings_clicked(self):
        """callback for settings button"""
        dialog = SettingDialog(self)
        dialog.memory_changed.connect(self.update_memory_display)
        dialog.exec_()

    def on_play_clicked(self):
        """callback for play button"""
        settings = javaFunc.load_settings()
        memory_mb = settings.get("memory_mb", 2048)
        self.play_requested.emit(memory_mb)

    def on_site_clicked(self):
        """callback for site button"""
        webbrowser.open(urlSetting.site)

    def update_memory_display(self, memory_mb: int | None = None):
        """Обновление отображения информации о памяти"""
        if memory_mb is None:
            settings = javaFunc.load_settings()
            memory_mb = settings.get("memory_mb", 2048)

        self.memory_info_label.setText(f"Выделено памяти: {memory_mb} MB")

    def setup_styles(self):
        """load styles"""
        StyleManager.load_styles(self)
