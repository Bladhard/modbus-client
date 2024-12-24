from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
import time

from tg_alarm import notify_server
from overall_work import config, logger, send_request


data_server = config["server_url"]
alarm_server = config["server_url_alarm"]


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

    # После опроса всех адресов отправляем собранные данные
    # print("Collected Data: ", collected_data)
    # print("Collected Alarm: ", collected_alarm)
    # Отправка данных на сервер
    send_request(data_server, collected_data)
    send_request(alarm_server, collected_alarm)


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
            try:
                notify_server()
            except Exception as e:
                logger.error(
                    f"Ошибка при уведомлении сервера: {e}. Повторная попытка не будет выполнена."
                )
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
