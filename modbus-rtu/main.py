from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
import time


from tg_alarm import notify_server
from overall_work import config, logger, send_request

data_server = config["server_url"]
alarm_server = config["server_url_alarm"]

# Настройки Modbus по последовательному интерфейсу
serial_client = ModbusSerialClient(
    port=config["serial_port"],
    baudrate=config["baud_rate"],
)


def convert_to_signed(value):
    """Преобразует беззнаковое 16-битное значение в знаковое."""
    return value if value < 32768 else value - 65536


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

            for i, reg_value in enumerate(response.registers):
                collected_data[f"R{address + i:03d}"] = str(
                    convert_to_signed(reg_value)
                )

        except ModbusException as e:
            logger.error(f"Ошибка Modbus при чтении {address}: {e}")

    # print(collected_data)
    send_request(data_server, collected_data)
    # send_request(data_server, collected_alarm)


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

            notify_server()
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
