from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
import time

from tg_alarm import notify_server
from overall_work import config, logger, send_request


data_server = config["server_url"]
alarm_server = config["server_url_alarm"]
config_test = config["config_test"]


def convert_to_signed(value):
    """Преобразует беззнаковое 16-битное значение в знаковое."""
    return value if value < 32768 else value - 65536


def read_modbus_data(client, addresses, retries=3, delay=5, ip=None):
    """Чтение данных Modbus с накоплением и отправкой в один пакет."""
    collected_data = {}  # Словарь для накопления данных
    collected_alarm = {}  # Словарь для накопления данных
    error_flag = False  # Флаг ошибки для текущего клиента

    for (
        address,
        count,
    ) in addresses:  # Адреса и количество регистров в виде списка кортежей
        for attempt in range(retries):
            try:
                response = client.read_holding_registers(address=address, count=count)

                if response.isError():
                    # logger.error(
                    #     f"Ошибка при чтении регистров с адреса {address}: {response}"
                    # )
                    continue  # Попробуем снова, если была ошибка
                else:
                    if ip:
                        collected_data["IP"] = ip
                        collected_alarm["IP"] = ip

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
                            bit_value = (
                                value >> (15 - i)
                            ) & 0x01  # Сдвиг и маскирование
                            collected_alarm[f"{bit_label}"] = (
                                "Сообщение" if bit_value else "ОК"
                            )

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
            error_flag = True  # Устанавливаем флаг ошибки для клиента

    # После опроса всех адресов отправляем собранные данные
    if config_test:
        logger.info(f"Collected Data: {collected_data}")
        logger.info(f"Collected Alarm: {collected_alarm}")
    else:
        # Отправка данных на сервер
        send_request(data_server, collected_data)
        send_request(alarm_server, collected_alarm)

    return error_flag  # Возвращаем флаг ошибки


def connect_to_modbus_server(ip, port):
    """
    Попытка подключения к Modbus-серверу.
    Возвращает клиент при успешном подключении или None в случае неудачи.
    """
    try:
        client = ModbusTcpClient(ip, port=port, timeout=10)
        if client.connect():
            logger.info(f"Соединение с {ip} успешно установлено.")
            return client
        else:
            logger.warning(f"Не удалось установить соединение с сервером {ip}.")
    except Exception as e:
        logger.error(f"Ошибка при подключении к {ip}: {e}", exc_info=True)
    return None


def process_modbus_data():
    """
    Основной цикл опроса Modbus-серверов.
    Для каждого IP:
      - Пытаемся установить соединение.
      - Если соединение установлено – опрашиваем указанные адреса.
      - При ошибках или отсутствии соединения – повторная попытка подключения.
    """
    # Инициализация словаря клиентов; ключи — IP-адреса, значения — объекты клиентов или None.
    clients = {ip: None for ip in config["modbus_servers"]}

    # Первоначальное подключение к каждому серверу
    for ip in clients:
        clients[ip] = connect_to_modbus_server(ip, config["modbus_port"])

    try:
        while True:
            for ip, client in clients.items():
                if client is None:
                    # Попытка повторного подключения
                    logger.info(
                        f"Проверка доступности сервера {ip} для повторного подключения..."
                    )
                    new_client = connect_to_modbus_server(ip, config["modbus_port"])
                    if new_client is not None:
                        logger.info(
                            f"Соединение с сервером {ip} восстановлено, выполняем опрос."
                        )
                        clients[ip] = new_client
                        client = (
                            new_client  # сразу используем восстановленное соединение
                        )
                    else:
                        logger.warning(f"Сервер {ip} по-прежнему недоступен.")
                        continue  # переходим к следующему серверу

                # Если соединение установлено, выполняем опрос
                try:
                    # Формирование списка адресов и количества регистров для опроса
                    addresses_to_read = [
                        (req["address"], req["count"])
                        for req in config["request_settings"]
                    ]
                    logger.info(f"Чтение данных с {ip}: {addresses_to_read}")

                    error_flag = read_modbus_data(
                        client,
                        addresses=addresses_to_read,
                        retries=config.get("retries", 3),
                        delay=config.get("retry_delay", 5),
                        ip=ip,
                    )

                    if error_flag:
                        logger.warning(
                            f"Ошибки при работе с сервером {ip}. Переподключение..."
                        )
                        client.close()
                        clients[ip] = None

                    # Задержка между опросами одного устройства
                    time.sleep(config["machine_interval"])

                except Exception as e:
                    logger.error(f"Ошибка при опросе {ip}: {e}", exc_info=True)
                    if client:
                        client.close()
                        logger.info(f"Соединение с {ip} закрыто из-за ошибки.")
                    clients[ip] = None

            logger.info("Ожидание следующего цикла опроса...")
            try:
                notify_server()
            except Exception as e:
                logger.error(
                    f"Ошибка при уведомлении сервера: {e}. Повторная попытка не будет выполнена.",
                    exc_info=True,
                )
            time.sleep(config["polling_interval"])

    except KeyboardInterrupt:
        logger.info("Опрос остановлен пользователем.")
    finally:
        for ip, client in clients.items():
            if client:
                try:
                    client.close()
                    logger.info(f"Закрыто соединение для клиента {ip}.")
                except Exception as e:
                    logger.error(
                        f"Ошибка при закрытии клиента {ip}: {e}", exc_info=True
                    )


# Основная функция
def main():
    try:
        logger.info("Запуск опроса машин...")
        process_modbus_data()
    except KeyboardInterrupt:
        logger.info("Опрос остановлен пользователем.")


if __name__ == "__main__":
    main()
