import json
import os
import requests

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from utils.overall_work import logger


# === Константы ===
TELEGRAM_TOKEN = "7902002433:AAHmrHoBriL8dRcskrJtzQPDXwag7OQd4Fs"

# Получаем текущую директорию скрипта
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, "states.json")
SUBSCRIBERS_FILE = os.path.join(SCRIPT_DIR, "subscribers.json")


# === Загрузка и сохранение состояния ===
def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


# === Telegram логика ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers = load_json(SUBSCRIBERS_FILE, [])
    if chat_id not in subscribers:
        subscribers.append(chat_id)
        save_json(SUBSCRIBERS_FILE, subscribers)
        await update.message.reply_text(
            "✅ Вы подписаны на уведомления о состоянии баков."
        )
        logger.info(
            f"Подписка пользователя {chat_id} на уведомления о состоянии баков."
        )
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
            print(f"Ошибка отправки {chat_id}: {e}")
            logger.error(f"Ошибка отправки {chat_id}: {e}")


# === Логика проверки состояния ===
def parse_payload(payloads, states):
    slave_id = payloads.get("slave_id")
    data = payloads.get("data", {})
    state_value = data.get("R513")
    if state_value is None:
        return  # если нет значения — игнорируем

    if slave_id == 16:
        check_state("MC01", state_value, states)
    elif slave_id == 17:
        check_state("MC02", state_value, states)


def check_state(mc_name, current_state, states):
    prev_state = states.get(mc_name)
    if prev_state != current_state:
        states[mc_name] = current_state
        if int(current_state) == 0:
            send_telegram_message_to_all(f"{mc_name}:  ❗ Бак пустой")
            logger.info(f"Сообщение в Telegram отправлено: {mc_name}:  ❗ Бак пустой")
        elif int(current_state) == 1:
            send_telegram_message_to_all(f"{mc_name}:  ✅ Бак наполнен")
            logger.info(f"Сообщение в Telegram отправлено: {mc_name}:  ✅ Бак наполнен")


def monitoring_tank_tg(payloads):
    states = load_json(STATE_FILE, {"MC01": None, "MC02": None})
    parse_payload(payloads, states)
    save_json(STATE_FILE, states)


# === Старт Telegram-бота ===
def bot_start():
    logger.info("🤖 Telegram-бот запущен")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()


if __name__ == "__main__":
    bot_start()
