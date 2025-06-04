import json
import os
import requests
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from pathlib import Path
import sys

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(project_root))

from utils.overall_work import logger

TELEGRAM_TOKEN = "8194020891:AAFikscpl5pzhRUvBVLPSqdxtP00syOrPAo"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SUBSCRIBERS_FILE = os.path.join(SCRIPT_DIR, "subscribers.json")
TEMP_STATE_FILE = os.path.join(SCRIPT_DIR, "temp_state.json")

TEMPERATURE_LIMIT_OVERHEAT = 50.0
TEMPERATURE_LIMIT_NORMAL = 49.0
REMINDER_INTERVAL = 3600  # 1 час
MIN_INTERVAL_BETWEEN_MESSAGES = 600  # 10 минут


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers = load_json(SUBSCRIBERS_FILE, [])
    if chat_id not in subscribers:
        subscribers.append(chat_id)
        save_json(SUBSCRIBERS_FILE, subscribers)
        await update.message.reply_text("✅ Вы подписаны на уведомления о температуре.")
        logger.info(f"Подписка пользователя {chat_id}")
    else:
        await update.message.reply_text("🔔 Вы уже подписаны.")


def send_telegram_message_to_all(text):
    subscribers = load_json(SUBSCRIBERS_FILE, [])
    for chat_id in subscribers:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        try:
            requests.post(url, data=payload)
        except Exception as e:
            logger.error(f"Ошибка отправки {chat_id}: {e}")


def format_sensor_name(register):
    mapping = {
        "R16384": "Темп. мотора 1",
        "R16386": "Темп. редуктора 1",
        "R16388": "Темп. подшипника передн. 1",
        "R16390": "Темп. подшипника задн. 2",
        "R16392": "Темп. подшипника передн. 3",
        "R16394": "Темп. подшипника задн. 4",
        "R16396": "Темп. мотора 2",
        "R16398": "Темп. редуктора 2",
        "R16400": "Темп. подшипника передн. 5",
        "R16402": "Темп. подшипника задн. 4",
        "R16404": "Темп. подшипника передн. 7",
        "R16406": "Темп. подшипника задн. 8",
        "R16408": "Темп. мотора 3",
        "R16410": "Темп. редуктора 3",
        "R16412": "Темп. подшипника передн. 9",
        "R16414": "Темп. подшипника задн. 10",
        "R16416": "Темп. подшипника передн. 11",
        "R16418": "Темп. подшипника задн. 12",
    }
    return mapping.get(register, f"Регистр {register}")


def check_temperatures(data):
    temp_state = load_json(TEMP_STATE_FILE, {})
    now = time.time()

    for reg, value_str in data.items():
        try:
            value = float(value_str)
        except ValueError:
            continue

        state = temp_state.get(reg, {})
        status = state.get("status", "normal")
        last_notify = state.get("last_notify", 0)
        can_send = now - last_notify >= MIN_INTERVAL_BETWEEN_MESSAGES

        if value >= TEMPERATURE_LIMIT_OVERHEAT:
            if status != "overheat" and can_send:
                send_telegram_message_to_all(
                    f"🔥 Перегрев: {format_sensor_name(reg)} = {value}°C"
                )
                logger.info(f"🔥 Перегрев: {reg} = {value}")
                temp_state[reg] = {"status": "overheat", "last_notify": now}
            elif now - last_notify >= max(
                REMINDER_INTERVAL, MIN_INTERVAL_BETWEEN_MESSAGES
            ):
                send_telegram_message_to_all(
                    f"⏰ Напоминание: {format_sensor_name(reg)} по-прежнему {value}°C"
                )
                logger.info(f"⏰ Напоминание: {reg} = {value}")
                temp_state[reg]["last_notify"] = now

        elif value <= TEMPERATURE_LIMIT_NORMAL and status == "overheat" and can_send:
            send_telegram_message_to_all(
                f"✅ Норма: {format_sensor_name(reg)} = {value}°C"
            )
            logger.info(f"✅ Температура нормализовалась: {reg} = {value}")
            temp_state[reg] = {"status": "normal", "last_notify": now}

    save_json(TEMP_STATE_FILE, temp_state)


def bot_start():
    logger.info("🤖 Telegram-бот запущен")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()


if __name__ == "__main__":
    bot_start()
