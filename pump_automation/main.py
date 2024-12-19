import csv
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
import time
from datetime import datetime

from bit import valid_addresses, register_bit_labels
from tg_alarm import notify_server
from overall_work import config, logger, send_request


CSV_FILE = "modbus_data.csv"
# "127.0.0.1"


data_server = config["server_url"]
alarm_server = config["server_url_alarm"]


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
    # print("Collected Alarm: ", collected_alarm)
    # Отправка данных на сервер
    send_request(data_server, collected_data)
    send_request(data_server, collected_alarm)


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

                        try:
                            for request in config["request_settings"]:
                                address = request.get("address")
                                count = request.get("count")

                                if address is None or count is None:
                                    logger.error(f"Некорректный запрос: {request}")
                                    continue

                                addresses_to_read.append((address, count))
                                logger.info(
                                    f"Запланировано чтение {count} регистров с адреса {address} с {ip}"
                                )
                        except Exception as e:
                            logger.error(
                                f"Ошибка при подготовке адресов для чтения: {e}"
                            )

                        if not client.is_socket_open():
                            logger.warning(f"Соединение с {ip} потеряно. Пропуск.")
                            continue

                        start_time = time.time()
                        max_duration = config["max_read_duration"]
                        # Опрос всех адресов за раз
                        read_modbus_data(
                            client,
                            addresses=addresses_to_read,
                            retries=config.get("retries", 3),
                            delay=config.get("retry_delay", 5),
                            ip=ip,
                        )

                        if time.time() - start_time > max_duration:
                            logger.error(f"Превышено время выполнения чтения для {ip}.")
                            break

                        # Задержка между опросами одного устройства
                        time.sleep(config["machine_interval"])

                    except Exception as e:
                        logger.error(f"Ошибка при опросе {ip}: {e}.")
                        logger.info("Попробуем переподключиться в следующий цикл.")
                        clients[ip] = None  # Помечаем клиент как недоступный

            # Пауза между полными циклами опроса
            logger.info("Ожидание следующего цикла...")
            try:
                notify_server()
            except Exception as e:
                logger.error(
                    f"Ошибка при уведомлении сервера: {e}. Повторная попытка не будет выполнена."
                )

            polling_interval = config["polling_interval"]
            if not isinstance(polling_interval, (int, float)) or polling_interval <= 0:
                logger.error(
                    f"Некорректное значение polling_interval: {polling_interval}. Установлено значение по умолчанию: 100."
                )
                polling_interval = 100
            time.sleep(polling_interval)  # Задержка между циклами
            # time.sleep(config["polling_interval"])  # Задержка между циклами

    except Exception as e:
        logger.error(f"Ошибка в основном цикле: {e}")
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

    except Exception as e:
        logger.error(f"Ошибка в основном цикле: {e}")
        time.sleep(10)  # Задержка перед повторной попыткой

    except KeyboardInterrupt:
        logger.info("Опрос остановлен пользователем.")


if __name__ == "__main__":
    main()
