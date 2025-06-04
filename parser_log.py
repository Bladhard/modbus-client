import json
import re
import sqlite3
from pathlib import Path
import ast


LOG_FILE = "modbus_data.log"
DB_FILE = "modbus_clean_data.db"


def extract_data_from_log(file_path):
    """Извлекает все словари после 'Данные успешно отправлены:' и безопасно конвертирует их."""
    pattern = re.compile(r"Данные успешно отправлены: ({.*})")
    entries = []

    with open(file_path, encoding="utf-8") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                try:
                    # Преобразуем строку в Python-словарь
                    data_dict = ast.literal_eval(match.group(1))
                    entries.append(data_dict)
                except Exception as e:
                    print(f"Ошибка при парсинге строки: {e}")
    return entries


def clean_data(data_dict):
    """Заменяет все значения -9999.00 и -9999999.00 на 0.00"""
    cleaned = {
        k: ("0.00" if v in ("-9999.00", "-9999999.00") else v)
        for k, v in data_dict.items()
    }
    return cleaned


def init_db(db_path):
    """Создаёт таблицу, если её нет"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS data_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """
    )
    conn.commit()
    conn.close()


def save_to_db(entries, db_path):
    """Сохраняет список записей в БД"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for entry in entries:
        timestamp = entry.get("timestamp")
        cleaned_data = clean_data(entry.get("data", {}))
        if not cleaned_data:
            continue  # пропуск пустых записей
        cur.execute(
            "INSERT INTO data_queue (timestamp, data) VALUES (?, ?)",
            (timestamp, json.dumps(cleaned_data)),
        )
    conn.commit()
    conn.close()


def main():
    if not Path(LOG_FILE).exists():
        print(f"Файл {LOG_FILE} не найден.")
        return

    print("[*] Чтение и парсинг логов...")
    extracted = extract_data_from_log(LOG_FILE)

    print(f"[*] Извлечено записей: {len(extracted)}")
    print("[*] Инициализация базы...")
    init_db(DB_FILE)

    print("[*] Сохраняем в базу данных...")
    save_to_db(extracted, DB_FILE)
    print("[+] Готово! База: modbus_clean_data.db")


if __name__ == "__main__":
    main()
