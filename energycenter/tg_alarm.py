import requests
import json
import time


# Загрузка конфигурации из файла
def load_config(config_file="config.json"):
    try:
        with open(config_file, "r") as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"Ошибка при загрузке конфигурационного файла: {e}")
        return None


config = load_config()
# Конфигурация клиента
API_URL_ALARM = config["API_URL_ALARM"]
PROGRAM_NAME = config["PROGRAM_NAME"]
API_KEY = config["API_KEY"]  # Тот же ключ, что указан в config.ini сервера


def notify_server(max_retries: int = 3, backoff_factor: float = 0.5) -> bool:
    """
    Отправляет статусное уведомление на сервер с механизмом повторных попыток.

    Args:
        max_retries (int, optional): Максимальное количество попыток. По умолчанию 3.
        backoff_factor (float, optional): Коэффициент экспоненциальной задержки. По умолчанию 0.5.

    Returns:
        bool: True, если уведомление отправлено успешно, иначе False.
    """
    from main import logger

    payload = {"program_name": PROGRAM_NAME, "api_key": API_KEY}

    for attempt in range(max_retries):
        try:
            response = requests.post(
                API_URL_ALARM,
                json=payload,
                timeout=5,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            logger.info(f"Статус для {PROGRAM_NAME} успешно отправлен.")
            return True

        except requests.exceptions.RequestException as e:
            wait_time = backoff_factor * (2**attempt)
            logger.warning(
                f"Попытка {attempt + 1}/{max_retries} не удалась. "
                f"Ошибка: {e}. Повторная попытка через {wait_time:.2f} секунд."
            )

            if attempt == max_retries - 1:
                logger.error(
                    f"Не удалось отправить статус после {max_retries} попыток. Ошибка: {e}"
                )
                return False

            time.sleep(wait_time)

    return False


def start_periodic_notification(
    interval_seconds: int = 300, max_retries: int = 3
) -> None:
    """
    Запускает периодическую отправку уведомлений на сервер.

    Args:
        interval_seconds (int, optional): Интервал между отправками в секундах. По умолчанию 300 (5 минут).
        max_retries (int, optional): Максимальное количество попыток отправки. По умолчанию 3.
    """
    from main import logger

    logger.info(
        f"Запуск периодической отправки уведомлений каждые {interval_seconds} секунд"
    )

    while True:
        try:
            success = notify_server(max_retries=max_retries)
            if success:
                logger.info(
                    f"Уведомление отправлено успешно. Следующая отправка через {interval_seconds} секунд."
                )
            else:
                logger.error("Не удалось отправить уведомление после всех попыток.")

            time.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("Остановка периодической отправки уведомлений.")
            break
        except Exception as e:
            logger.error(
                f"Непредвиденная ошибка: {e}. Повторная попытка через {interval_seconds} секунд."
            )
            time.sleep(interval_seconds)


if __name__ == "__main__":
    # Пример использования
    start_periodic_notification(interval_seconds=180)  # Отправка каждые 3 минуты
