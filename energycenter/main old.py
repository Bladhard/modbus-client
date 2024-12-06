import logging
import csv
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
import time
from datetime import datetime
import requests
import json


CSV_FILE = "modbus_data.csv"
# "127.0.0.1"


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
    log_levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    logging.basicConfig(
        level=log_levels.get(log_level, logging.INFO),  # Уровень DEBUG для отладки
        format="%(asctime)s - %(levelname)s - %(message)s",  # Формат сообщений
        handlers=[
            logging.FileHandler(
                log_file, mode="a", encoding="utf-8"
            ),  # Логи сохраняются в файл
            logging.StreamHandler(),  # Также выводятся в консоль
        ],
    )
    return logging.getLogger(__name__)


config = load_config()
logger = setup_logging(config["log_file"], config["log_level"])


# Функция отправки запроса на сервер для данных
def send_request(data):
    try:
        response = requests.post(
            config["server_url"], data=json.dumps(data), headers=config["headers"]
        )
        if response.status_code == 200:
            logger.info(f"Данные успешно отправлены: {data}")
        else:
            logger.error(
                f"Ошибка при отправке данных: {response.status_code} - {response.text}"
            )
    except requests.exceptions.Timeout:
        logger.error("Тайм-аут при отправке запроса.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при отправке запроса: {e}")


# Функция отправки запроса на сервер для предупреждений
def send_alarm_request(data):
    try:
        response = requests.post(
            config["server_url_alarm"], data=json.dumps(data), headers=config["headers"]
        )
        if response.status_code == 200:
            logger.info(f"Данные успешно отправлены: {data}")
        else:
            logger.error(
                f"Ошибка при отправке данных: {response.status_code} - {response.text}"
            )
    except requests.exceptions.Timeout:
        logger.error("Тайм-аут при отправке запроса.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при отправке запроса: {e}")


def write_to_csv(register, value):
    """Запись данных в CSV файл с временем."""
    try:
        # Получаем текущее время
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(CSV_FILE, mode="a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(
                [current_time, register, value]
            )  # Добавляем время, регистр и значение
        logger.info(f"Записано в CSV: {current_time} {register} = {value}")
    except Exception as e:
        logger.error(f"Ошибка при записи в CSV: {e}")


def convert_to_signed(value):
    """Преобразует беззнаковое 16-битное значение в знаковое."""
    return value if value < 32768 else value - 65536


def read_modbus_data(client, address, count, retries=3, delay=5, ip=None):
    """Чтение данных Modbus с повторными попытками."""
    for attempt in range(retries):
        try:
            response = client.read_holding_registers(address=address, count=count)

            if response.isError():
                logger.error(
                    f"Ошибка при чтении регистров с адреса {address}: {response}"
                )
                continue  # Попробуем снова, если была ошибка
            else:
                data = {}
                data["IP"] = ip

                if address == 14 or address == 15:
                    # Определяем битовые метки для адресов 14 и 15
                    bit_labels = {
                        14: [
                            440,
                            439,
                            438,
                            437,
                            436,
                            435,
                            434,
                            433,
                            432,
                            431,
                            430,
                            429,
                            428,
                            427,
                            426,
                            425,
                        ],
                        15: [
                            456,
                            455,
                            454,
                            453,
                            452,
                            451,
                            450,
                            449,
                            448,
                            447,
                            446,
                            445,
                            444,
                            443,
                            442,
                            441,
                        ],
                    }

                    value = response.registers[0]
                    print(f"Значение регистра R{address:03d}: {value:016b}")

                    # Парсинг битовых данных
                    for i, bit_label in enumerate(bit_labels[address]):
                        bit_value = (value >> (15 - i)) & 0x01  # Сдвиг и маскирование
                        data[f"{bit_label}"] = "Сообщение" if bit_value else "ОК"

                else:
                    # Чтение регистров и добавление в словарь для остальных адресов
                    for i, reg_value in enumerate(response.registers):
                        signed_value = convert_to_signed(reg_value)
                        register = f"R{address + i:03d}"
                        data[register] = str(
                            signed_value
                        )  # Добавляем значение регистра в data

                # Отправка данных на сервер
                if address == 14 or address == 15:
                    print("Alarm: ", data)
                    # send_alarm_request(data)
                else:
                    print("Data: ", data)
                    # send_request(data)
                return  # Завершаем функцию, если данные успешно получены и отправлены

        except ModbusException as e:
            logger.error(f"Ошибка Modbus при чтении с адреса {address}: {e}")

        # Если не получилось, подождем и сделаем еще одну попытку
        if attempt < retries - 1:
            logger.info(f"Повторная попытка {attempt + 1} из {retries}...")
            time.sleep(delay)

    # Если после всех попыток не получилось, сообщаем об ошибке
    logger.error(
        f"Не удалось получить данные с адреса {address} после {retries} попыток."
    )


# Функция для работы с каждым IP-адресом
def process_modbus_data():
    clients = {}  # Словарь для хранения подключений

    # Создаем подключение для каждого IP и сохраняем в словарь
    for ip in config["modbus_servers"]:
        client = ModbusTcpClient(ip, port=config["modbus_port"])
        try:
            # Подключаемся к серверу
            connection = client.connect()
            if connection:
                logger.info(f"Подключение к {ip} успешно.")
                clients[ip] = client  # Сохраняем подключение в словарь
            else:
                logger.error(
                    f"Не удалось установить соединение с сервером {ip}. Пропуск."
                )
                clients[ip] = None  # Если не удалось подключиться, помечаем как None
        except Exception as e:
            logger.error(f"Ошибка при подключении к {ip}: {e}. Пропуск.")
            clients[ip] = None  # Если ошибка подключения, помечаем как None

    try:
        while True:
            # Цикл обработки данных с каждого сервера
            for ip, client in clients.items():
                if client is not None:  # Если подключение установлено
                    try:
                        for request in config["request_settings"]:
                            address = request["address"]
                            count = request["count"]
                            logger.info(
                                f"Чтение {count} регистров с адреса {address} с {ip}"
                            )
                            read_modbus_data(client, address, count, ip=ip)
                        time.sleep(
                            config["machine_interval"]
                        )  # Задержка между опросами машинок
                    except KeyboardInterrupt:
                        logger.info("Опрос остановлен пользователем.")
                        break
                else:
                    logger.info(f"Сервер {ip} не доступен. Пропуск...")

            # Пауза между полными циклами опроса
            logger.info("Ожидание следующего цикла...")
            time.sleep(config["polling_interval"])  # Задержка между циклами

    except KeyboardInterrupt:
        logger.info("Опрос остановлен пользователем.")
    finally:
        # Закрытие всех подключений
        for ip, client in clients.items():
            if client:
                client.close()
                logger.info(f"Соединение с {ip} закрыто.")


# Основная функция
def main():
    try:
        process_modbus_data()
    except KeyboardInterrupt:
        logger.info("Опрос остановлен пользователем.")


if __name__ == "__main__":
    main()
