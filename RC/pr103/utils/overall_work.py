import json
import os
import logging
from logging.handlers import TimedRotatingFileHandler
import zipfile
import glob
import re
from datetime import datetime


# Загрузка конфигурации из файла
def load_config(config_file="config.json"):
    try:
        with open(config_file, "r") as f:
            config = json.load(f)
        return config
    except Exception as e:
        logger.error(f"Ошибка при загрузке конфигурационного файла: {e}")
        return None


# Настройка логирования
def setup_logging(log_file: str) -> logging.Logger:
    """Настройка логгера с поддержкой ротации логов и архивированием старых логов в ZIP."""
    # Создаем папку для логов и архивов, если они не существуют
    log_dir = os.path.join(os.path.dirname(log_file), "logs")
    archive_dir = os.path.join(log_dir, "archive")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)
    log_file = os.path.join(log_dir, os.path.basename(log_file))

    # Уровни логирования
    log_levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    # Создаем основной логгер
    logger = logging.getLogger(__name__)
    logger.setLevel(log_levels.get(config["log_level"], logging.INFO))

    # Форматирование сообщений
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Обработчик для консольного вывода
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Кастомный обработчик для ротации логов с архивированием
    class ArchivingTimedRotatingFileHandler(TimedRotatingFileHandler):
        def __init__(self, *args, **kwargs):
            self.archive_dir = kwargs.pop("archive_dir", archive_dir)
            self.max_archives = kwargs.pop("max_archives", 2)  # Максимум 2 архива
            super().__init__(*args, **kwargs)

        def doRollover(self):
            """Выполняет ротацию логов и архивирует старый лог-файл в ZIP."""
            # Выполняем стандартную ротацию
            super().doRollover()

            # После ротации ищем старые лог-файлы
            base_filename = self.baseFilename
            rotated_files = glob.glob(f"{base_filename}.*")

            for rotated_file in rotated_files:
                if rotated_file != self.baseFilename and os.path.exists(rotated_file):
                    # Извлекаем дату из имени файла (например, tcp_server.log.2025-03-25_16-02-34)
                    date_match = re.search(
                        r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", rotated_file
                    )
                    if date_match:
                        timestamp = date_match.group(0)
                    else:
                        # Если дата не найдена, используем текущую
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

                    # Формируем имя архива с датой
                    archive_name = os.path.join(
                        self.archive_dir,
                        f"{os.path.basename(rotated_file)}.zip",
                    )

                    # Формируем имя файла внутри архива: tcp_server_YYYY-MM-DD_HH-MM-SS.log
                    archived_file_name = f"{os.path.basename(base_filename).replace('.log', '')}_{timestamp}.log"

                    try:
                        # Архивируем файл с максимальным сжатием
                        with zipfile.ZipFile(
                            archive_name,
                            "w",
                            compression=zipfile.ZIP_DEFLATED,
                            compresslevel=9,
                        ) as zipf:
                            zipf.write(rotated_file, archived_file_name)
                        logger.debug(f"Старый лог-файл архивирован: {archive_name}")

                        # Удаляем оригинальный файл после архивирования
                        os.remove(rotated_file)
                        logger.debug(
                            f"Старый лог-файл удален после архивирования: {rotated_file}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Ошибка при архивировании лог-файла {rotated_file}: {e}"
                        )
            # Управление количеством архивов
            self._manage_archives()

        def _manage_archives(self):
            """Управляет количеством архивов: оставляет только max_archives самых новых."""
            archives = sorted(
                glob.glob(os.path.join(self.archive_dir, "*.zip")), key=os.path.getmtime
            )  # Сортируем по времени изменения (самые старые в начале)

            # Если архивов больше, чем max_archives, удаляем самые старые
            while len(archives) > self.max_archives:
                oldest_archive = archives.pop(0)  # Удаляем самый старый из списка
                try:
                    os.remove(oldest_archive)
                    logger.debug(f"Удален старый архив: {oldest_archive}")
                except Exception as e:
                    logger.error(
                        f"Ошибка при удалении старого архива {oldest_archive}: {e}"
                    )

    # Обработчик для ротации логов с архивированием
    file_handler = ArchivingTimedRotatingFileHandler(
        filename=log_file,
        when="W0",  # Ротация каждую неделю (понедельник)
        interval=1,  # Интервал - одна неделя
        backupCount=2,  # Хранить до 2 старых логов (до архивирования)
        max_archives=2,  # Максимум 2 архива
        encoding="utf-8",
        archive_dir=archive_dir,
    )
    file_handler.setFormatter(formatter)

    # Очищаем предыдущие обработчики, если они есть
    logger.handlers.clear()

    # Добавляем обработчики в логгер
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logger.info("Логирование настроено с ротацией и архивированием.")

    return logger


config = load_config()
logger = setup_logging(config["log_file"])
