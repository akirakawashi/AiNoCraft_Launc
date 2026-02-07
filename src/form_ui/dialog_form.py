# from loguru import logger
import psutil
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from src.config import javaFunc
from src.style.StyleManager import StyleManager


class SettingDialog(QDialog):
    """settings dialog form"""

    memory_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.total_memory_mb = 0
        self.available_memory_mb = 0
        self.setup_ui()
        self.setup_styles()
        self.load_settings()

    def setup_ui(self):
        """create settings dialog form"""
        self.get_system_memory()
        self.setWindowTitle("Настройки запуска")
        self.setFixedSize(500, 500)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # Заголовок окна
        title_label = QLabel("Настройки запуска")
        title_label.setProperty("class", "title-label_dialog")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # Группа настроек памяти
        memory_group = QGroupBox("Настройки оперативной памяти")
        memory_layout = QVBoxLayout()

        # Верхняя панель с текущим значением
        top_panel = QHBoxLayout()

        self.memory_value_label = QLabel("2048 MB")
        self.memory_value_label.setProperty("class", "memory-value-label")
        self.memory_value_label.setAlignment(Qt.AlignCenter)
        top_panel.addWidget(self.memory_value_label)

        # Индикатор использования
        self.usage_indicator = QLabel("Низкое")
        self.usage_indicator.setProperty("class", "usage-indicator usage-low")
        self.usage_indicator.setAlignment(Qt.AlignCenter)
        top_panel.addWidget(self.usage_indicator)

        memory_layout.addLayout(top_panel)

        # Прогресс-бар для визуализации
        self.memory_progress = QProgressBar()
        self.memory_progress.setRange(1024, self.total_memory_mb)
        self.memory_progress.setValue(2048)
        self.memory_progress.setTextVisible(False)
        self.memory_progress.setProperty("class", "memory-bar")
        memory_layout.addWidget(self.memory_progress)

        # Панель слайдера
        slider_layout = QHBoxLayout()

        min_label = QLabel("1 GB")
        min_label.setProperty("class", "info-label")
        max_label_gb = self.total_memory_mb // 1024
        max_label = QLabel(f"{max_label_gb} GB")
        max_label.setProperty("class", "info-label")

        # Слайдер для выбора памяти
        self.memory_slider = QSlider(Qt.Horizontal)
        self.memory_slider.setMinimum(1024)
        self.memory_slider.setMaximum(self.total_memory_mb)
        self.memory_slider.setSingleStep(512)
        self.memory_slider.setTickPosition(QSlider.TicksBelow)
        self.memory_slider.setTickInterval(2048)

        slider_layout.addWidget(min_label)
        slider_layout.addWidget(self.memory_slider)
        slider_layout.addWidget(max_label)

        memory_layout.addLayout(slider_layout)

        # Панель точного ввода
        input_layout = QHBoxLayout()
        input_layout.addStretch()

        input_label = QLabel("Точное значение:")
        input_label.setProperty("class", "info-label")
        input_layout.addWidget(input_label)

        # Спинбокс для точного ввода
        self.memory_spinbox = QSpinBox()
        self.memory_spinbox.setMinimum(1024)
        self.memory_spinbox.setMaximum(self.total_memory_mb)
        self.memory_spinbox.setSingleStep(512)
        self.memory_spinbox.setSuffix(" MB")
        self.memory_spinbox.setProperty("class", "memory-spinbox")
        input_layout.addWidget(self.memory_spinbox)
        input_layout.addStretch()
        memory_layout.addLayout(input_layout)

        # Рекомендации
        recommendation_label = QLabel("⚠ Рекомендуется уставновить 4096-8192 MB для оптимальной игры!")
        recommendation_label.setProperty("class", "recommendation-label")
        recommendation_label.setAlignment(Qt.AlignCenter)
        recommendation_label.setWordWrap(True)
        memory_layout.addWidget(recommendation_label)

        # Информация об использовании (ВНУТРИ группы памяти)
        info_layout = QHBoxLayout()
        info_layout.addStretch()
        self.usage_info = QLabel("Использование: --%")
        self.usage_info.setProperty("class", "info-label")
        info_layout.addWidget(self.usage_info)

        memory_layout.addLayout(info_layout)
        memory_group.setLayout(memory_layout)
        main_layout.addWidget(memory_group)

        # Кнопки
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_button = QPushButton("Сохранить настройки")
        self.cancel_button = QPushButton("Отмена")

        self.save_button.setProperty("class", "save-button")
        self.cancel_button.setProperty("class", "cancel-button")

        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()

        main_layout.addLayout(button_layout)

        # Статус-бар
        self.status_label = QLabel("Готово")
        self.status_label.setProperty("class", "status-label info")
        main_layout.addWidget(self.status_label)

        # Подключение сигналов
        self.save_button.clicked.connect(self.save_settings)
        self.cancel_button.clicked.connect(self.reject)

        # Подключение сигналов обновления UI
        self.memory_slider.valueChanged.connect(self.update_memory_display)
        self.memory_spinbox.valueChanged.connect(self.update_memory_display)

        # Связываем слайдер и спинбокс
        self.memory_slider.valueChanged.connect(self.memory_spinbox.setValue)
        self.memory_spinbox.valueChanged.connect(self.memory_slider.setValue)
        self.memory_slider.valueChanged.connect(self.memory_progress.setValue)

    def get_system_memory(self):
        """get system memory"""
        memory = psutil.virtual_memory()
        self.total_memory_mb = int(memory.total / (1024**2))
        self.available_memory_mb = int(memory.available / (1024**2))

    def update_memory_display(self, value):
        """Обновление отображения значения памяти"""
        self.memory_value_label.setText(f"{value} MB ({value / 1024:.1f} GB)")
        usage_percent = (value / self.total_memory_mb) * 100

        if value < 2048:
            usage_text = "Низкое"
            usage_class = "usage-low"
            status_class = "warning"
            status_text = "⚠ Мало памяти, возможны лаги"
        elif value < 4096:
            usage_text = "Среднее"
            usage_class = "usage-medium"
            status_class = "info"
            status_text = "✓ Достаточно для базовой игры"
        elif value < 8192:
            usage_text = "Оптимальное"
            usage_class = "usage-normal"
            status_class = "success"
            status_text = "✓ Оптимально для большинства модов"
        elif value < self.total_memory_mb * 0.8:
            usage_text = "Высокое"
            usage_class = "usage-high"
            status_class = "normal"
            status_text = "✓ Отлично для тяжелых модов и текстурпаков"
        else:
            usage_text = "Очень высокое"
            usage_class = "usage-critical"
            status_class = "overload"
            status_text = "✓ Лагов не будет)"

        self.usage_indicator.setText(usage_text)
        self.usage_indicator.setProperty("class", f"usage-indicator {usage_class}")

        self.usage_info.setText(f"Использование: {usage_percent:.1f}%")

        self.status_label.setText(status_text)
        self.status_label.setProperty("class", f"status-label {status_class}")

        # Обновляем стиль индикатора
        self.usage_indicator.style().unpolish(self.usage_indicator)
        self.usage_indicator.style().polish(self.usage_indicator)

        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def load_settings(self):
        """download settings json"""
        settings = javaFunc.load_settings()
        memory_mb = settings.get("memory_mb", 2048)

        if memory_mb > self.total_memory_mb:
            memory_mb = self.total_memory_mb
            javaFunc.save_memory_setting(memory_mb)

        self.memory_slider.setValue(memory_mb)

    def save_settings(self):
        """save settings json"""
        memory_mb = self.memory_slider.value()

        if memory_mb > self.available_memory_mb:
            allocated_gb = memory_mb / 1024
            available_gb = self.available_memory_mb / 1024
            self.status_label.setText(f"⚠ Внимание: выделено {allocated_gb:.1f} GB при свободных {available_gb:.1f} GB")
            self.status_label.setProperty("class", "status-label warning")
        else:
            self.status_label.setText("✓ Настройки успешно сохранены")
            self.status_label.setProperty("class", "status-label success")

        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

        javaFunc.save_memory_setting(memory_mb)
        self.memory_changed.emit(memory_mb)

        QTimer.singleShot(1000, self.accept)

    def setup_styles(self):
        """Настройка стилей"""
        StyleManager.load_styles(self)


class DownloadDialog(QDialog):
    """Диалог загрузки Minecraft"""

    # Добавляем сигнал для отмены
    download_cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.start_time = None
        self.setup_ui()
        self.setup_styles()
        self.setWindowTitle("Установка Lolicraft")
        self.setFixedSize(500, 350)

    def setup_ui(self):
        """Создание интерфейса диалога"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(20, 20, 20, 20)

        # Заголовок с иконкой
        header_layout = QHBoxLayout()
        self.title_label = QLabel("📥 Установка Lolicraft")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setProperty("class", "download-title")
        header_layout.addWidget(self.title_label)
        layout.addLayout(header_layout)

        # Прогресс-бар с процентами
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setProperty("class", "download-progress")
        layout.addWidget(self.progress_bar)

        # Информационная панель
        info_group = QGroupBox("Информация о загрузке")
        info_layout = QVBoxLayout()

        # Скорость и время
        speed_time_layout = QHBoxLayout()

        self.speed_label = QLabel("Скорость: --")
        self.speed_label.setProperty("class", "download-info")

        self.time_label = QLabel("Осталось: --")
        self.time_label.setProperty("class", "download-info")

        speed_time_layout.addWidget(self.speed_label)
        speed_time_layout.addStretch()
        speed_time_layout.addWidget(self.time_label)

        # Прогресс в числах
        progress_layout = QHBoxLayout()

        self.downloaded_label = QLabel("Загружено: 0 MB / 0 MB")
        self.downloaded_label.setProperty("class", "download-info")

        self.percentage_label = QLabel("0%")
        self.percentage_label.setProperty("class", "download-percentage")
        self.percentage_label.setAlignment(Qt.AlignRight)

        progress_layout.addWidget(self.downloaded_label)
        progress_layout.addStretch()
        progress_layout.addWidget(self.percentage_label)

        info_layout.addLayout(speed_time_layout)
        info_layout.addLayout(progress_layout)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Кнопка отмены
        self.cancel_button = QPushButton("❌ Отменить загрузку")
        self.cancel_button.setProperty("class", "download-cancel-button")
        self.cancel_button.clicked.connect(self.cancel_download)
        layout.addWidget(self.cancel_button)

    def cancel_download(self):
        """Обработка отмены загрузки"""
        self.download_cancelled.emit()
        self.reject()

    def update_progress(self, percent: int):
        """Обновление прогресса"""
        self.progress_bar.setValue(percent)
        self.percentage_label.setText(f"{percent}%")

    def update_download_info(self, downloaded: int, total: int, speed: float):
        """Обновление информации о загрузке"""
        from time import time

        self.downloaded_bytes = downloaded
        self.total_bytes = total

        if self.start_time is None:
            self.start_time = time()

        # Обновление скорости
        if speed > 0:
            if speed >= 1024 * 1024:  # MB/s
                speed_text = f"{speed / (1024 * 1024):.1f} MB/сек"
            elif speed >= 1024:  # KB/s
                speed_text = f"{speed / 1024:.1f} KB/сек"
            else:  # B/s
                speed_text = f"{speed:.0f} B/сек"
            self.speed_label.setText(f"⚡ Скорость: {speed_text}")

        # Обновление размера
        if total > 0:
            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            percent = (downloaded / total) * 100

            self.downloaded_label.setText(f"📁 Загружено: {downloaded_mb:.1f} MB / {total_mb:.1f} MB")
            self.update_progress(int(percent))

            # Расчет оставшегося времени
            if speed > 0:
                remaining_bytes = total - downloaded
                remaining_seconds = remaining_bytes / speed

                if remaining_seconds > 3600:  # часов
                    hours = int(remaining_seconds // 3600)
                    minutes = int((remaining_seconds % 3600) // 60)
                    self.time_label.setText(f"⏳ Осталось: {hours}ч {minutes}м")
                elif remaining_seconds > 60:  # минут
                    minutes = int(remaining_seconds // 60)
                    seconds = int(remaining_seconds % 60)
                    self.time_label.setText(f"⏳ Осталось: {minutes}м {seconds}с")
                else:  # секунд
                    self.time_label.setText(f"⏳ Осталось: {int(remaining_seconds)}с")

    def setup_styles(self):
        """Настройка стилей"""
        StyleManager.load_styles(self)
