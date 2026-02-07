import time
import zipfile
from pathlib import Path

import requests
from loguru import logger

# from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal

from ..config import javaFunc, systemSetting, urlSetting


class DownloadManager(QThread):
    """start download manager"""

    finished = pyqtSignal(bool, str)
    progress_percent = pyqtSignal(int)
    download_info = pyqtSignal(int, int, float)

    def __init__(self):
        super().__init__()
        self.appdata_path = Path(systemSetting.appdata)
        self.minecraft_path = Path(javaFunc.minecraft_directory)
        self.download_url = urlSetting.download
        self.is_downloading = False

        self.start_time = None
        self.last_update_time = None
        self.last_downloaded = 0

    def run(self):
        """start download and unzip"""
        self.is_downloading = True
        archive_path = None

        try:
            archive_path = self.appdata_path / ".LoliCraft_temp.zip"
            response = requests.get(self.download_url, stream=True, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Ошибка сервера: {response.status_code}")

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            self.start_time = time.time()
            self.last_update_time = self.start_time
            self.last_downloaded = 0

            with open(archive_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self.isInterruptionRequested() or not self.is_downloading:
                        logger.info("Загрузка прервана пользователем")
                        self.finished.emit(False, "Загрузка отменена")
                        return

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            self.progress_percent.emit(percent)

                            current_time = time.time()
                            time_diff = current_time - self.last_update_time

                            if time_diff > 0.5 or self.last_downloaded == 0:
                                if time_diff > 0:
                                    speed = (downloaded - self.last_downloaded) / time_diff
                                else:
                                    speed = 0

                                self.download_info.emit(downloaded, total_size, speed)
                                self.last_update_time = current_time
                                self.last_downloaded = downloaded

            logger.info("Загрузка завершена")
            self.progress_percent.emit(100)
            if total_size > 0:
                total_time = time.time() - self.start_time
                avg_speed = total_size / total_time if total_time > 0 else 0
                self.download_info.emit(total_size, total_size, avg_speed)

            logger.info(f"Распаковка в: {self.minecraft_path}")
            if not self.minecraft_path.exists():
                logger.info(f"Создание директории: {self.minecraft_path}")
                self.minecraft_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Директория создана: {self.minecraft_path}")

            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(self.minecraft_path)
            archive_path.unlink()
            logger.info("Распаковка завершена")

            logger.info(f"Установка в: {javaFunc.jar_directory}")
            if Path(javaFunc.jar_directory).exists():
                logger.info(javaFunc.jar_directory)
                self.finished.emit(True, "Загрузка завершена")
            else:
                logger.error("Ошибка установки")
                raise FileNotFoundError("Ошибка установки")

        except Exception as e:
            logger.error(f"Ошибка в DownloadManager: {e}")
            self.finished.emit(False, f"Ошибка загрузки: {e}")

        finally:
            try:
                if archive_path and archive_path.exists():
                    logger.info(f"Удаление временного архива: {archive_path}")
                    archive_path.unlink()
                    logger.info("Временный архив удален")
            except Exception as e:
                logger.error(f"Не удалось удалить временный архив: {e}")

            logger.info("Загрузка завершена (finally)")
            self.is_downloading = False

    def stop_download(self):
        """stop download"""
        logger.info("Загрузка прервана")
        self.is_downloading = False
        self.requestInterruption()
