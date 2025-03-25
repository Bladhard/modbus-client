import sqlite3
import requests
import time
import socket
import json
from datetime import datetime
import threading
from typing import Dict, Optional, Any

from .overall_work import config, logger


class DataQueueManager:
    """Класс для управления очередью данных с локальным хранением и отправкой на сервер.

    Инициализация:
        queue_manager = DataQueueManager()

    2. Сохранение данных:
        data = {"sensor_id": 123, "temperature": 23.5}
        queue_manager.save_to_db(data)

    3. Отправка:
        Отправка происходит автоматически в фоновом потоке.
        Ничего дополнительно вызывать не нужно.
    """

    def __init__(
        self,
        db_name: str = "data.db",
        server_url: str = None,
        send_interval: int = 1,
    ):
        self.db_name = db_name
        self.server_url = server_url or config["server_url"]
        self.send_interval = send_interval
        self.headers = config.get("headers", {})
        self.lock = threading.Lock()
        self._init_db()
        self._start_sending_thread()

    def _init_db(self) -> None:
        """Инициализация базы данных SQLite."""
        try:
            with sqlite3.connect(self.db_name, check_same_thread=False) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS data_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        data TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    )
                """)
                conn.commit()
                logger.info(f"База данных: {self.db_name} успешно инициализирована.")
        except sqlite3.Error as e:
            logger.error(f"Ошибка при инициализации базы данных: {e}")
            raise

    def _check_network(self) -> bool:
        """Проверка наличия сети."""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            logger.debug("Сеть недоступна.")
            return False

    def save_to_db(self, data: Dict[str, Any]) -> None:
        """Сохранение данных в локальную базу (сериализация в JSON)."""
        try:
            timestamp = datetime.now().isoformat()
            data_json = json.dumps(data, ensure_ascii=False)
            with self.lock:
                with sqlite3.connect(self.db_name, check_same_thread=False) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO data_queue (data, timestamp) VALUES (?, ?)",
                        (data_json, timestamp),
                    )
                    conn.commit()
            # logger.debug(f"Данные сохранены в базу: {data_json[:50]}...")
        except (sqlite3.Error, json.JSONEncodeError) as e:
            logger.error(f"Ошибка при сохранении данных в базу: {e}")

    def _get_oldest_record(self) -> Optional[tuple]:
        """Получение самой старой записи из базы."""
        try:
            with self.lock:
                with sqlite3.connect(self.db_name, check_same_thread=False) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id, data, timestamp FROM data_queue ORDER BY timestamp ASC LIMIT 1"
                    )
                    record = cursor.fetchone()
            return record
        except sqlite3.Error as e:
            logger.error(f"Ошибка при получении записи из базы: {e}")
            return None

    def _delete_record(self, record_id: int) -> None:
        """Удаление записи из базы по ID."""
        try:
            with self.lock:
                with sqlite3.connect(self.db_name, check_same_thread=False) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM data_queue WHERE id = ?", (record_id,))
                    conn.commit()
            logger.debug(f"Запись с ID {record_id} удалена из базы.")
        except sqlite3.Error as e:
            logger.error(f"Ошибка при удалении записи из базы: {e}")

    def _send_to_server(self, data_json: str, timestamp: str) -> bool:
        """Отправка данных на сервер с retry-логикой."""
        max_retries = 5
        delay = 3

        for attempt in range(1, max_retries + 1):
            try:
                data = json.loads(data_json)
                payload = {"timestamp": timestamp, "data": data}
                response = requests.post(
                    self.server_url,
                    data=json.dumps(payload),
                    headers=self.headers,
                    timeout=5,
                )
                if response.status_code == 200:
                    logger.info(f"Данные успешно отправлены: {data}")
                    return True
                else:
                    logger.error(
                        f"Ошибка при отправке данных: {response.status_code} - {response.text}"
                    )

            except requests.exceptions.Timeout:
                logger.error("Тайм-аут при отправке запроса.")
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка при отправке запроса: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка при декодировании JSON: {e}")

            if attempt < max_retries:
                logger.info(
                    f"Повторная попытка отправки ({attempt}/{max_retries}) через {delay} секунд..."
                )
                time.sleep(delay)
            else:
                logger.error("Превышено максимальное количество попыток отправки.")

        return False

    def _send_data_thread(self) -> None:
        """Функция для параллельной отправки данных."""
        while True:
            if self._check_network():
                while True:
                    record = self._get_oldest_record()
                    if not record:
                        break
                    record_id, record_data, record_timestamp = record
                    if self._send_to_server(record_data, record_timestamp):
                        self._delete_record(record_id)
                    else:
                        logger.warning(
                            "Не удалось отправить данные, остаются в очереди"
                        )
                        break
                    time.sleep(self.send_interval)
            time.sleep(1)  # Пауза перед следующей проверкой сети

    def _start_sending_thread(self) -> None:
        """Запуск потока для отправки данных."""
        send_thread = threading.Thread(target=self._send_data_thread)
        send_thread.daemon = True
        send_thread.start()
        logger.info("Поток отправки данных запущен.")


# Пример использования
if __name__ == "__main__":
    # Инициализация менеджера очереди данных
    queue_manager = DataQueueManager()

    # Пример сложных данных (словарь)
    for i in range(5):
        sample_data = {
            "sensor_id": 123 + i,
            "temperature": 23.5 + i,
            "humidity": 60 + i,
            "timestamp": f"2023-10-01T12:0{i}:00",
        }
        queue_manager.save_to_db(sample_data)
        logger.info(f"Добавлены данные {i}")
        time.sleep(0.5)  # Имитация работы основного кода

    # Даем время на обработку всех данных перед завершением
    time.sleep(5)
