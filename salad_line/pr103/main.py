from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
import time
import struct

from utils.tg_alarm import notify_server
from utils.overall_work import config, logger
from utils.DataQueueManager import DataQueueManager

data_server = config["server_url"]

# data.db и alarm.db обязательно называть таким образом для сервера приема
qm_data = DataQueueManager(
    db_name="data.db",
    server_url=data_server,
)

# Настройки Modbus по последовательному интерфейсу
serial_client = ModbusSerialClient(
    port=config["serial_port"],
    baudrate=config["baud_rate"],
)


def convert_registers_to_float(registers):
    """
    Преобразует два 16-битных регистра в число с плавающей точкой (float).
    """
    # Объединенное 32-битное значение
    value = (registers[1] << 16) | registers[0]
    # Преобразуем в байты (big-endian)
    bytes_value = value.to_bytes(4, byteorder="big")
    # Интерпретируем байты как float
    float_value = struct.unpack(">f", bytes_value)[0]
    return float_value


def read_modbus_data(client, addresses, slave_id):
    """Чтение данных Modbus и отправка на сервер."""
    collected_data = {}

    for address, count in addresses:
        try:
            response = client.read_holding_registers(
                address=address, count=count, slave=slave_id
            )

            if response.isError():
                logger.error(f"Ошибка при чтении {address}: {response}")
                continue

            # Если данные — это float (два регистра)
            if count == 2:
                float_value = convert_registers_to_float(response.registers)
                collected_data[f"R{address:03d}"] = f"{float_value:.2f}"
            else:
                # Обработка обычных 16-битных значений
                for i, reg_value in enumerate(response.registers):
                    collected_data[f"R{address + i:03d}"] = reg_value
        except ModbusException as e:
            logger.error(f"Ошибка Modbus при чтении {address}: {e}")
        except ValueError as e:
            logger.error(f"Ошибка преобразования данных: {e}")

        # print(collected_data)
        qm_data.save_to_db(collected_data)


def process_modbus_data():
    """Основной цикл опроса."""
    if not serial_client.connect():
        logger.error("Не удалось установить соединение по последовательному порту.")
        return

    try:
        while True:
            unit_id = config["slave_id"]
            addresses_to_read = [
                (req["address"], req["count"]) for req in config["request_settings"]
            ]
            read_modbus_data(serial_client, addresses_to_read, unit_id)
            try:
                notify_server()
            except Exception as e:
                logger.error(f"Ошибка при уведомлении сервера: {e}.")

            time.sleep(config["polling_interval"])
    except KeyboardInterrupt:
        logger.info("Опрос остановлен пользователем.")
    finally:
        serial_client.close()
        logger.info("Соединение закрыто.")


def main():
    try:
        process_modbus_data()
    except Exception as e:
        logger.error(f"Ошибка в основном цикле: {e}")
        time.sleep(10)


if __name__ == "__main__":
    main()
