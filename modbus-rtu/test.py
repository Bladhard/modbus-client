from pymodbus.client import ModbusSerialClient

# Настройка COM-порта (замените параметры на свои)
port = 'COM3'      # Имя порта (Linux: /dev/ttyS0, /dev/ttyUSB0)
baudrate = 9600    # Скорость передачи
parity = 'N'       # Четность (N - None, E - Even, O - Odd)
stopbits = 1       # Стоп-биты
bytesize = 8       # Размер байта

client = ModbusSerialClient(
    port=port,
    baudrate=baudrate,
    parity=parity,
    stopbits=stopbits,
    bytesize=bytesize,
    timeout=1
)

if client.connect():
    print("Подключено к RTU")
    # Чтение Holding Register (адрес 0x01, стартовый регистр 0, количество 1)
    response = client.read_holding_registers(address=0, count=1, slave=1)
    if not response.isError():
        print("Ответ от RTU:", response.registers)
    else:
        print("Ошибка:", response)
    client.close()
else:
    print("Не удалось подключиться к COM-порту")