import json
import time
import requests

import logging
from logging.handlers import TimedRotatingFileHandler


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
def setup_logging(log_file, log_level):
    """Настройка логгера с поддержкой ротации логов."""
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
    logger.setLevel(log_levels.get(log_level, logging.INFO))

    # Форматирование сообщений
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Обработчик для консольного вывода
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Обработчик для ротации логов
    file_handler = TimedRotatingFileHandler(
        filename=log_file,  # Имя файла логов
        when="W0",  # Ротация каждую неделю (понедельник)
        interval=1,  # Интервал - одна неделя
        backupCount=2,  # Хранить до 2 старых логов
        encoding="utf-8",  # Кодировка для правильной записи
    )
    file_handler.setFormatter(formatter)

    # Добавляем обработчики в логгер
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# Функция отправки запроса на сервер для данных
def send_request(url, data):
    max_retries = 5
    delay = 3  # задержка в секундах между попытками

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                url, data=json.dumps(data), headers=config["headers"]
            )

            if response.status_code == 200:
                logger.info(f"Данные успешно отправлены: {data}")
                return True
            else:
                logger.error(
                    f"Ошибка при отправке данных: {response.status_code} - {response.text}"
                )

        except requests.exceptions.Timeout:
            logger.error("Тайм-аут при отправке запроса.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при отправке запроса: {e}")

        if attempt < max_retries:
            logger.info(
                f"Повторная попытка отправки ({attempt}/{max_retries}) через {delay} секунд..."
            )
            time.sleep(delay)
        else:
            logger.error("Превышено максимальное количество попыток отправки.")

    return False

config = load_config()
logger = setup_logging(config["log_file"], config["log_level"])
