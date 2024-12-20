import requests
import json


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


def notify_server():
    from main import logger

    payload = {"program_name": PROGRAM_NAME, "api_key": API_KEY}
    try:
        response = requests.post(API_URL_ALARM, json=payload, timeout=5)
        response.raise_for_status()
        logger.info(f"Статус для {PROGRAM_NAME} отправлен.")
    except Exception as e:
        logger.error(f"Ошибка отправки статуса: {e}")
