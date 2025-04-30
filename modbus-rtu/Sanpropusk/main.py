from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
import time
import threading

from utils.tg_alarm import notify_server
from utils.overall_work import config, logger
from utils.DataQueueManager import DataQueueManager
from Telegram.bot import bot_start, monitoring_tank_tg


data_server = config["server_url"]
alarm_server = config["server_url_alarm"]


qm_data = DataQueueManager(
    db_name="data.db",
    server_url=data_server,
)

# Настройки Modbus по последовательному интерфейсу
serial_client = ModbusSerialClient(
    port=config["serial_port"],
    baudrate=config["baud_rate"],
)


def convert_to_signed(value):
    """Преобразует беззнаковое 16-битное значение в знаковое."""
    return value if value < 32768 else value - 65536


def read_modbus_data(client, addresses, slave_id):
    """Чтение данных Modbus и отправка на сервер по конкретному slave_id."""
    collected_data = {}

    for address, count in addresses:
        try:
            response = client.read_holding_registers(
                address=address, count=count, slave=slave_id
            )
            if response.isError():
                logger.error(
                    f"Ошибка при чтении {address} (slave {slave_id}): {response}"
                )
                continue

            for i, reg_value in enumerate(response.registers):
                collected_data[f"R{address + i:03d}"] = str(
                    convert_to_signed(reg_value)
                )

        except ModbusException as e:
            logger.error(f"Modbus-ошибка при чтении {address} (slave {slave_id}): {e}")

    # Формируем структуру данных с указанием slave_id
    payload = {"slave_id": slave_id, "data": collected_data}

    monitoring_tank_tg(payload)
    qm_data.save_to_db(payload)


def process_modbus_data():
    """Основной цикл опроса всех slave-устройств по очереди."""
    if not serial_client.connect():
        logger.error("Не удалось установить соединение по последовательному порту.")
        return

    try:
        while True:
            slave_ids = config["slave_ids"]  # список: [1, 2, 3,...]
            addresses_to_read = [
                (req["address"], req["count"]) for req in config["request_settings"]
            ]

            for unit_id in slave_ids:
                read_modbus_data(serial_client, addresses_to_read, unit_id)

            notify_server()
            time.sleep(config["polling_interval"])
    except KeyboardInterrupt:
        logger.info("Опрос остановлен пользователем.")
    finally:
        serial_client.close()
        logger.info("Соединение закрыто.")


def main():
    try:
        # Запускаем мониторинг в отдельном потоке
        threading.Thread(target=process_modbus_data, daemon=True).start()

        bot_start()
    except Exception as e:
        logger.error(f"Ошибка в основном цикле: {e}")
        time.sleep(10)


if __name__ == "__main__":
    main()
