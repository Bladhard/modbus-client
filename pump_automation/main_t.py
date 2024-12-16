import logging
from logging.handlers import TimedRotatingFileHandler
import csv
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
import time
from datetime import datetime
import requests
import json
from bit import valid_addresses, register_bit_labels

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


config = load_config()
logger = setup_logging(config["log_file"], config["log_level"])

data_server = config["server_url"]
alarm_server = config["server_url_alarm"]


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


def read_modbus_data(client, addresses, retries=3, delay=5, ip=None):
    """Чтение данных Modbus с накоплением и отправкой в один пакет."""
    collected_data = {}  # Словарь для накопления данных
    collected_alarm = {}  # Словарь для накопления данных

    for (
        address,
        count,
    ) in addresses:  # Адреса и количество регистров в виде списка кортежей
        for attempt in range(retries):
            try:
                response = client.read_holding_registers(address=address, count=count)

                if response.isError():
                    logger.error(
                        f"Ошибка при чтении регистров с адреса {address}: {response}"
                    )
                    continue  # Попробуем снова, если была ошибка
                else:
                    if ip:
                        collected_data["IP"] = ip
                        collected_alarm["IP"] = ip

                    if address in valid_addresses:
                        response = client.read_discrete_inputs(address=100, count=16)
                        bits = response.bits
                        print("Прочитанные входы:", bits)
                        response_bits = client.read_coils(address=address, count=16)
                        bits = response_bits.bits[
                            :16
                        ]  # Массив значений битов (True/False)
                        # print(f"Значение регистра R{address:03d}: {bits}")
                        # print(f"Значение регистра R{address:03d}: {bits:016b}")
                        existing_alarms = {}
                        # Парсинг битовых данных
                        for i, bit_label in enumerate(register_bit_labels[address]):
                            if i < len(
                                bits
                            ):  # Проверяем, существует ли бит с таким индексом
                                bit_value = bits[i]
                                # print(i, bit_label, bit_value)
                                existing_alarms[bit_label] = (
                                    "Сообщение" if bit_value else "ОК"
                                )
                        # Вывод результатов
                        # Добавляем данные из existing_alarms в collected_alarm
                        for label, status in existing_alarms.items():
                            collected_alarm[label] = status
                    else:
                        # Чтение регистров и добавление в словарь для остальных адресов
                        for i, reg_value in enumerate(response.registers):
                            signed_value = convert_to_signed(reg_value)
                            register = f"R{address + i:03d}"
                            collected_data[register] = str(
                                signed_value
                            )  # Добавляем значение регистра в collected_data

                    break  # Успешное чтение завершено, выходим из цикла попыток

            except ModbusException as e:
                logger.error(f"Ошибка Modbus при чтении с адреса {address}: {e}")

            # Если не получилось, подождем и сделаем еще одну попытку
            if attempt < retries - 1:
                logger.info(f"Повторная попытка {attempt + 1} из {retries}...")
                time.sleep(delay)

        else:
            # Если после всех попыток не получилось, сообщаем об ошибке
            logger.error(
                f"Не удалось получить данные с адреса {address} после {retries} попыток."
            )

    # После опроса всех адресов отправляем собранные данные
    # print("Collected Data: ", collected_data)
    print("Collected Alarm: ", collected_alarm)
    # Отправка данных на сервер
    # send_request(data_server, collected_data)
    # send_request(data_server, collected_alarm)


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
            for ip, client in clients.items():
                if client is None:  # Если клиент не был подключен
                    try:
                        logger.info(f"Проверка доступности сервера {ip}...")
                        new_client = ModbusTcpClient(ip, port=config["modbus_port"])
                        connection = new_client.connect()
                        if connection:
                            logger.info(f"Соединение с сервером {ip} восстановлено.")
                            clients[ip] = new_client  # Обновляем клиента
                        else:
                            logger.warning(f"Сервер {ip} по-прежнему недоступен.")
                    except Exception as e:
                        logger.error(f"Ошибка при повторном подключении к {ip}: {e}.")
                else:  # Если клиент подключен
                    try:
                        # Список адресов и количества регистров для опроса
                        addresses_to_read = []

                        for request in config["request_settings"]:
                            address = request["address"]
                            count = request["count"]
                            addresses_to_read.append((address, count))
                            logger.info(
                                f"Запланировано чтение {count} регистров с адреса {address} с {ip}"
                            )
                        # Опрос всех адресов за раз
                        read_modbus_data(
                            client,
                            addresses=addresses_to_read,
                            retries=config.get("retries", 3),
                            delay=config.get("retry_delay", 5),
                            ip=ip,
                        )

                        # Задержка между опросами одного устройства
                        time.sleep(config["machine_interval"])

                    except Exception as e:
                        logger.error(f"Ошибка при опросе {ip}: {e}.")
                        logger.info("Попробуем переподключиться в следующий цикл.")
                        clients[ip] = None  # Помечаем клиент как недоступный

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
