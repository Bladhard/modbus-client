import socket
import struct
import threading
from time import sleep
from concurrent.futures import ThreadPoolExecutor


class ModbusTestServer:
    def __init__(self, host="127.0.0.1", port=502, max_workers=10):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers)  # Пул потоков для клиентов
        # Создадим несколько адресов с фейковыми значениями
        self.registers = {
            658: 1234,
            659: -25,
            660: 4321,
            1016: 1234,  # R000 MSB
            1015: 4321,
            1014: 6789,
            1013: 9876,
            1012: 2345,
            1011: 3456,
            1010: 7890,
            1009: 4567,
            1008: 5678,  # R000 LSB
            1007: 1357,
            1006: 2468,
            1005: 3579,
            1004: 4680,
            1003: 5791,
            1002: 6802,
            1001: 7913,
            1032: 9101,  # R001 MSB
            1031: 1239,
            1030: 3478,
            1029: 1122,
            1028: 3344,
            1027: 5566,
            1026: 7788,
            1025: 9900,
            1024: 2910,  # R001 LSB
            1023: 1827,
            1022: 5739,
            1021: 6832,
            1020: 4938,
            1019: 7482,
            1018: 3847,
            1017: 2381,
            1048: 3344,  # R002 MSB
            1047: 8473,
            1046: 1920,
            1045: 5643,
            1044: 2938,
            1043: 1765,
            1042: 8392,
            1041: 2718,
            1040: 5566,  # R002 LSB
            1039: 3467,
            1038: 2389,
            1037: 4756,
            1036: 8291,
            1035: 5627,
            1034: 7192,
            1033: 3849,
            1064: 7788,  # R003 MSB
            1063: 1902,
            1062: 3948,
            1061: 4837,
            1060: 2873,
            1059: 6729,
            1058: 4857,
            1057: 1829,
            1056: 9900,  # R003 LSB
            1055: 5738,
            1054: 3821,
            1053: 4918,
            1052: 3847,
            1051: 7391,
            1050: 2981,
            1049: 6821,
        }

    def start(self):
        """Запуск тестового сервера"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            self.running = True
            print(f"Сервер запущен на {self.host}:{self.port}")

            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    print(f"Подключение от {address}")
                    # Добавляем обработку клиента в пул потоков
                    self.executor.submit(self.handle_client, client_socket)
                except Exception as e:
                    if self.running:
                        print(f"Ошибка при принятии подключения: {e}")
        except Exception as e:
            print(f"Ошибка запуска сервера: {e}")
        finally:
            self.stop()

    def stop(self):
        """Остановка сервера"""
        self.running = False
        self.executor.shutdown(wait=True)  # Ожидаем завершения всех потоков
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        print("Сервер остановлен")

    def handle_client(self, client_socket):
        """Обработка клиентских запросов"""
        try:
            while self.running:
                header = client_socket.recv(7)
                if not header or len(header) < 7:
                    break

                trans_id, proto_id, length, unit_id = struct.unpack(">HHHB", header[:7])
                function_code = int.from_bytes(client_socket.recv(1), "big")
                start_address = int.from_bytes(client_socket.recv(2), "big")
                register_count = int.from_bytes(client_socket.recv(2), "big")

                if function_code == 0x03:
                    response_data = bytearray()
                    for i in range(register_count):
                        reg_address = start_address + i
                        # Преобразуем отрицательные значения в 16-битные беззнаковые числа
                        value = self.registers.get(reg_address, 0) & 0xFFFF
                        high_byte, low_byte = divmod(value, 256)
                        response_data.extend([high_byte, low_byte])

                    response = (
                        struct.pack(
                            ">HHHBB",
                            trans_id,
                            proto_id,
                            3 + len(response_data),
                            unit_id,
                            function_code,
                        )
                        + struct.pack("B", len(response_data))
                        + bytes(response_data)
                    )

                    try:
                        client_socket.send(response)
                        print(
                            f"Отправлен ответ для адреса {start_address}: {response.hex()}"
                        )
                    except Exception as e:
                        print(f"Ошибка при отправке ответа: {e}")
                        break

                    else:
                        print(f"Неизвестный код функции: {function_code}")
                        break

        except Exception as e:
            print(f"Ошибка при обработке клиента: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass


def run_test_server():
    server = ModbusTestServer(host="127.0.0.1", port=502, max_workers=100)
    server_thread = threading.Thread(target=server.start)
    server_thread.daemon = True
    server_thread.start()

    print("Тестовый сервер запущен. Нажмите Ctrl+C для остановки.")

    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        print("\nОстановка сервера...")
        server.stop()


if __name__ == "__main__":
    run_test_server()
