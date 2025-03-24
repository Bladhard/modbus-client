from pymodbus.client import ModbusSerialClient

# Настройка клиента
client = ModbusSerialClient(port="COM4", baudrate=115200)


# Подключение
if client.connect():
    try:
        response = client.read_holding_registers(address=16384, count=2, slave=16)
        if response.isError():
            print(f"Ошибка: {response}")
        else:
            import struct

            # Объединенное 32-битное значение
            value = (response.registers[1] << 16) | response.registers[0]

            # Преобразуем в байты (big-endian)
            bytes_value = value.to_bytes(4, byteorder="big")

            # Интерпретируем байты как float
            float_value = struct.unpack(">f", bytes_value)[0]

            print(float_value)
            print(f"Input Registers: {response.registers}")
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        client.close()
else:
    print("Не удалось подключиться к устройству")
