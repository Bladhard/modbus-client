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
