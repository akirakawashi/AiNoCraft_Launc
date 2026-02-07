# main_window.py (финальная версия)
import os
import json  
import requests  
from loguru import logger
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QLabel, QMainWindow, QMessageBox

from src.logics.download_start import DownloadManager
from src.logics.minecraft_start import MinecraftManager

from .config import javaFunc, launcherSetting, apiSetting
from .form_ui.dialog_form import DownloadDialog
from .form_ui.game_form import GameForm
from .form_ui.login_form import LoginForm


class MainWindow(QMainWindow):
    """main window"""

    def __init__(self):
        super().__init__()
        self.minecraft_manager = MinecraftManager()
        self.download_manager = None
        self.download_dialog = None
        self.setup_window()
        self.setup_background()
        self.setup_login_form()
        self.game_form = None
        self.user_data = None
        self.current_user = None

    def setup_window(self):
        """setting main window"""
        self.setWindowTitle(launcherSetting.name)
        self.setFixedSize(launcherSetting.width, launcherSetting.height)

        # Установка иконки
        if hasattr(launcherSetting, "icon") and os.path.exists(launcherSetting.icon):
            self.setWindowIcon(QIcon(launcherSetting.icon))

    def setup_background(self):
        """create background image"""
        self.background_label = QLabel()

        if os.path.exists(launcherSetting.background):
            pixmap = QPixmap(launcherSetting.background)

            if pixmap.width() != launcherSetting.width or pixmap.height() != launcherSetting.height:
                pixmap = pixmap.scaled(
                    launcherSetting.width,
                    launcherSetting.height,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
            self.background_label.setPixmap(pixmap)
        self.background_label.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(self.background_label)


    def setup_login_form(self):
        """add login form"""
        self.login_form = LoginForm(self.background_label)
        self.login_form.setGeometry(0, 0, self.width(), self.height())
        self.login_form.login_requested.connect(self.handle_login)

    def handle_login(self, login, password):
        """handle login request"""
        logger.info(f"Login: {login}, Password: {password}")
        self.login_form.set_loading(True)
        if self.authenticate_user(login, password):
            self.setup_game_form(login)
            QTimer.singleShot(1000, lambda: self.on_login_successful())
        else:
            logger.info("Incorrect data")
            QTimer.singleShot(2000, lambda: self.login_form.set_loading(False))

        # if login == "admin" and password == "admin":
        #     logger.info("Authorization successful")
        #     self.setup_game_form(login)
        #     QTimer.singleShot(1000, lambda: self.on_login_successful())
        # else:
        #     logger.info("Incorrect data")
        #     QTimer.singleShot(2000, lambda: self.login_form.set_loading(False))

    def setup_game_form(self, login):
        """add game form"""
        if self.game_form:
            self.game_form.deleteLater()

        self.game_form = GameForm(login=login, parent=self.background_label)
        self.game_form.setGeometry(0, 0, self.width(), self.height())
        self.game_form.hide()

        self.game_form.logout_requested.connect(self.handle_logout)
        self.game_form.play_requested.connect(self.handle_play)

    def handle_logout(self):
        self.game_form.hide()
        self.login_form.show()
        self.login_form.clear()
        self.login_form.set_loading(False)
        logger.info("Logout successful")

    def handle_play(self, memory_mb):
        self.last_memory_mb = memory_mb

        if not self.minecraft_manager.is_installed():
            self.offer_download()
            return

        # Если установлен - запускаем
        self.launch_minecraft(memory_mb)

    def offer_download(self):
        """offer download minecraft"""
        response = QMessageBox.question(
            self,
            "Lolicraft не установлен",
            "При первом запуске необходимо установить Minecraft\n\nУстановить сейчас?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if response == QMessageBox.Yes:
            self.start_download()
        else:
            QMessageBox.information(self, "Установка отменена", "Вы можете установить Minecraft позже")

    def start_download(self):
        """start download"""
        self.download_dialog = DownloadDialog()
        self.download_dialog.setModal(True)
        self.download_manager = DownloadManager()
        self.download_manager.progress_percent.connect(self.download_dialog.update_progress)
        self.download_manager.download_info.connect(self.download_dialog.update_download_info)
        self.download_manager.finished.connect(self.on_download_finished)
        self.download_dialog.rejected.connect(self.cancel_download)
        self.download_manager.start()
        self.download_dialog.exec_()

    def on_login_successful(self):
        self.login_form.set_loading(False)
        self.login_form.hide()
        self.game_form.show()

    def cancel_download(self):
        """Отменить скачивание"""
        if self.download_manager:
            self.download_manager.stop_download()

    def on_download_finished(self, success: bool, message: str):
        """Загрузка завершена"""
        logger.info(f"on_download_finished вызван: success={success}, message={message}")
        if success:
            logger.info("Успешная загрузка, закрываю диалог")
            self.minecraft_manager = MinecraftManager()

            if self.download_dialog:
                self.download_dialog.accept()

            QMessageBox.information(
                self,
                "Установка завершена",
                "LoliCraft успешно установлен!\n\nНажмите кнопку 'Играть' для запуска!",
            )

    def launch_minecraft(self, memory_mb: int):
        """Запуск Minecraft (когда уже установлен)"""
        try:
            javaFunc.load_settings()
            logger.info(f"Запуск Minecraft для пользователя: {self.game_form.login}")
            logger.info(f"Запуск Minecraft с памятью: {memory_mb}MB")
            process = self.minecraft_manager.launch(self.game_form.login, memory_mb)

            logger.info(f"Minecraft запущен (PID: {process.pid})")

            self.close()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка запуска", f"Не удалось запустить Minecraft:\n{str(e)}")
            logger.debug(f"Ошибка запуска Minecraft: {e}")

    def authenticate_user(self, login, password):
        """Authenticate api user"""
        try:
            logger.info(f"Authenticating user: {login}")

            response = requests.post(
                apiSetting.api_url,
                json = {"login": login, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=apiSetting.timeout
            )

            if response.status_code == 200:
                logger.info("сервер принял запрос, парсим json")
                data = response.json()
                if data.get("success"):
                    logger.info("User authenticated successfully")
                    return True
                else:
                    logger.warning(f"Authentication failed: {data.get('message')}")
            else:
                logger.error(f"Authentication failed with status code: {response.status_code}")
        
        except requests.exceptions.ConnectionError:
            logger.error("Не удалось подключиться к серверу аутентификации")
            return self.fallback_authentication(login, password)
        except requests.exceptions.Timeout:
            logger.error("Таймаут подключения к серверу")
            return self.fallback_authentication(login, password)
        except Exception as e:
            logger.error(f"Ошибка аутентификации: {e}")
        
        return False