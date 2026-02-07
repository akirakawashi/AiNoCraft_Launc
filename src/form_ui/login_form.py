from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from src.config import urlSetting
from src.style.StyleManager import StyleManager


class LoginForm(QWidget):
    login_requested = pyqtSignal(str, str)  # логин, пароль

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.setup_styles()

    def setup_ui(self):
        """create login form"""

        # Основной layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(50, 350, 50, 10)
        self.main_layout.addStretch(1)

        # Заголовок
        self.title_label = QLabel("Приветствуем в LoliCraft!")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setProperty("class", "title-label")

        # Подзаголовок
        self.subtitle_label = QLabel("Авторизуйтесь, чтобы продолжить")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setProperty("class", "subtitle-label")

        # Поле логина
        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText("Введите ваш логин")
        self.login_input.setProperty("class", "input_label")
        self.login_input.setFixedWidth(500)

        # Поле пароля
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Введите ваш пароль")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setProperty("class", "input_label")
        self.password_input.setFixedWidth(500)

        # Чекбокс для отображения пароля и восстановления пароля
        self.password_layout = QHBoxLayout()
        self.show_password_checkbox = QCheckBox("Показать пароль")
        self.show_password_checkbox.setProperty("class", "checkbox_label")
        self.forgot_password_link = QLabel(
            f'<a href="{urlSetting.forgot_password}" style="color: #a490ff; text-decoration: none; font-size: 20px" >Забыли пароль?</a>'
        )
        self.forgot_password_link.setOpenExternalLinks(True)
        self.forgot_password_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.forgot_password_link.setProperty("class", "reset_password_link")

        self.password_layout.addWidget(self.show_password_checkbox)
        self.password_layout.addSpacing(155)
        self.password_layout.addWidget(self.forgot_password_link)

        self.login_button = QPushButton("Войти")
        self.login_button.setProperty("class", "button_login")
        self.login_button.setFixedWidth(500)
        # self.login_button.setFixedHeight(45)

        # Добавление элементов в layout
        self.main_layout.addWidget(self.title_label)
        self.main_layout.addWidget(self.subtitle_label)
        self.main_layout.addSpacing(10)
        self.main_layout.addWidget(self.login_input, alignment=Qt.AlignCenter)
        self.main_layout.addSpacing(15)
        self.main_layout.addWidget(self.password_input, alignment=Qt.AlignCenter)
        self.main_layout.addSpacing(10)
        password_container = QWidget()
        password_container.setLayout(self.password_layout)
        password_container.layout().setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(password_container, alignment=Qt.AlignCenter)
        self.main_layout.addSpacing(20)
        self.main_layout.addWidget(self.login_button, alignment=Qt.AlignCenter)
        self.main_layout.addStretch(1)

        self.setup_connections()

    def clear(self):
        """clear login form"""
        self.login_input.clear()
        self.password_input.clear()
        self.show_password_checkbox.setChecked(False)
        self.login_input.setFocus()

    def toggle_password_visibility(self, state):
        """toggle password visibility"""
        if state == Qt.Checked:
            self.password_input.setEchoMode(QLineEdit.Normal)
        else:
            self.password_input.setEchoMode(QLineEdit.Password)

    def set_loading(self, loading):
        """interactive login form button"""
        self.login_button.setEnabled(not loading)
        self.login_button.setText("Подождите..." if loading else "Войти")

    def on_login_clicked(self):
        """login button click"""
        login = self.login_input.text().strip()
        password = self.password_input.text().strip()
        self.login_requested.emit(login, password)

    def setup_connections(self):
        """setup connections"""
        self.login_button.clicked.connect(self.on_login_clicked)
        self.login_input.returnPressed.connect(self.on_login_clicked)
        self.password_input.returnPressed.connect(self.on_login_clicked)
        self.show_password_checkbox.stateChanged.connect(self.toggle_password_visibility)

    def setup_styles(self):
        StyleManager.load_styles(self)
