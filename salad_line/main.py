from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
import time


from overall_work import config, logger


data_server = config["server_url"]
alarm_server = config["server_url_alarm"]

# Ограничение на общее время выполнения цикла
MAX_CYCLE_TIME = config["max_cycle_time"]


def validate_config(config):
    """Проверяет корректность конфигурации."""
    required_keys = [
        "modbus_servers",
        "modbus_port",
        "request_settings",
        "polling_interval",
    ]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Отсутствует обязательный параметр конфигурации: {key}")
    if (
        not isinstance(config["polling_interval"], (int, float))
        or config["polling_interval"] <= 0
    ):
        raise ValueError(
            f"Некорректное значение polling_interval: {config['polling_interval']}"
        )


def convert_to_signed(value):
    """Преобразует беззнаковое 16-битное значение в знаковое."""
    return value if value < 32768 else value - 65536


def read_modbus_data(client, addresses, retries=3, delay=5, ip=None):
    """Чтение данных Modbus с накоплением и отправкой в один пакет."""
    collected_data = {}  # Словарь для накопления данных
    collected_alarm = {}  # Словарь для накопления данных
    logger.info(f"Производится чтение данных с IP-адреса {ip}")
    for (
        address,
        count,
    ) in addresses:  # Адреса и количество регистров в виде списка кортежей
        for attempt in range(retries):
            try:
                start_time = time.time()

                response = client.read_holding_registers(address=address, count=count)
                print(response)
                end_time = time.time()
                execution_time = end_time - start_time
                if execution_time > 5:
                    logger.warning(
                        f"Чтение {address} заняло {execution_time:.2f} секунд."
                    )

                if response.isError():
                    logger.error(
                        f"Ошибка при чтении регистров с адреса {address}: {response}"
                    )
                    continue  # Попробуем снова, если была ошибка
                else:
                    if ip:
                        collected_data["IP"] = ip
                        collected_alarm["IP"] = ip

                        response_bits = client.read_coils(address=address, count=16)
                        if not response_bits.isError():
                            bits = response_bits.bits[:16]
                        else:
                            logger.error(f"Ошибка чтения битов с адреса {address}")
                            continue
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
    print("Collected Data: ", collected_data)
    print("Collected Alarm: ", collected_alarm)
    # Отправка данных на сервер
    # send_request(data_server, collected_data)
    # send_request(data_server, collected_alarm)


# Функция для работы с каждым IP-адресом
def process_modbus_data():
    clients = {}

    for ip in config["modbus_servers"]:
        client = ModbusTcpClient(ip, port=config["modbus_port"], timeout=5)
        try:
            connection = client.connect()
            if connection:
                logger.info(f"Подключение к {ip} успешно.")
                clients[ip] = client
            else:
                logger.error(
                    f"Не удалось установить соединение с сервером {ip}. Пропуск."
                )
                clients[ip] = None
        except Exception as e:
            logger.error(f"Ошибка при подключении к {ip}: {e}. Пропуск.")
            clients[ip] = None

    try:
        while True:
            cycle_start_time = time.time()
            for ip, client in clients.items():
                if client is None:
                    try:
                        logger.info(f"Проверка доступности сервера {ip}...")
                        new_client = ModbusTcpClient(
                            ip, port=config["modbus_port"], timeout=5
                        )
                        connection = new_client.connect()
                        if connection:
                            logger.info(f"Соединение с сервером {ip} восстановлено.")
                            clients[ip] = new_client
                        else:
                            logger.warning(f"Сервер {ip} по-прежнему недоступен.")
                    except Exception as e:
                        logger.error(f"Ошибка при повторном подключении к {ip}: {e}.")
                else:
                    try:
                        addresses_to_read = []
                        for request in config["request_settings"]:
                            address = request.get("address")
                            count = request.get("count")
                            if address is None or count is None:
                                logger.error(f"Некорректный запрос: {request}")
                                continue
                            addresses_to_read.append((address, count))

                        if not client.is_socket_open():
                            logger.warning(f"Соединение с {ip} потеряно. Пропуск.")
                            client.close()
                            continue

                        start_time = time.time()
                        read_modbus_data(
                            client,
                            addresses=addresses_to_read,
                            retries=config.get("retries", 3),
                            delay=config.get("retry_delay", 5),
                            ip=ip,
                        )
                        if time.time() - start_time > config.get(
                            "max_read_duration", 60
                        ):
                            logger.error(f"Превышено время выполнения чтения для {ip}.")
                            continue

                        time.sleep(config["machine_interval"])
                    except Exception as e:
                        logger.error(f"Ошибка при опросе {ip}: {e}.")
                        clients[ip] = None

            if time.time() - cycle_start_time > MAX_CYCLE_TIME:
                logger.error(
                    "Превышено максимальное время выполнения цикла. Прерывание."
                )
                break

            logger.info("Ожидание следующего цикла...")

            time.sleep(config["polling_interval"])

    except Exception as e:
        logger.error(f"Ошибка в основном цикле: {e}")
    except KeyboardInterrupt:
        logger.info("Опрос остановлен пользователем.")
    finally:
        for ip, client in clients.items():
            if client:
                client.close()
                logger.info(f"Соединение с {ip} закрыто.")


# Основная функция
def main():
    try:
        validate_config(config)
        process_modbus_data()
    except ValueError as e:
        logger.error(f"Ошибка конфигурации: {e}")
    except Exception as e:
        logger.error(f"Ошибка в основном цикле: {e}")
        time.sleep(10)
    except KeyboardInterrupt:
        logger.info("Опрос остановлен пользователем.")


if __name__ == "__main__":
    main()
