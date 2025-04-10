import os
import subprocess
import http.client
import urllib.parse
import re
import sys
import io
import json
import time
import logging
import ssl

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding="utf-8")
except io.UnsupportedOperation:
    pass

# --- Константы и конфиг ---
URL = "https://eco-system.tech/dary/api/power/updateState2"
HOST = "192.168.123.10"
config = {"headers": {"x-access-token": "1000007", "Content-Type": "application/json"}}
PROGRAM_NAME = "Energy_DarPrirod_2"
API_KEY = "Energy_DarPrirod_2"

API_URL_ALARM = "http://185.149.146.250:8050/update_status"

COOKIE_FILE = "cookie"
PATH = "/webdef/0000W_A/scriptbib/rs/OPCData.asp"
PARAMS = {"_method": "read", "_mtype": "execute", "pcount": "0"}
CREATE_NO_WINDOW = 0x08000000

# --- Логгер ---
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def read_cookie_from_file():
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r") as f:
            return f.read().strip()
    return None


def save_cookie_to_file(cookie):
    with open(COOKIE_FILE, "w") as f:
        f.write(cookie.strip())


def update_cookie_via_tshark(
    interface="Подключение по локальной сети 2", filter_ip=HOST, timeout=10
):
    print("[*] Обновление cookie через tshark...")
    cmd = [
        "F:\\Program Files (x86)\\Wireshark\\tshark.exe",
        "-i",
        interface,
        "-Y",
        "http.request and ip.dst == {}".format(filter_ip),
        "-T",
        "fields",
        "-e",
        "http.cookie",
        "-a",
        "duration:{}".format(timeout),
    ]
    try:
        result = subprocess.check_output(
            cmd,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            creationflags=CREATE_NO_WINDOW,
        )
        cookie_lines = result.strip().splitlines()
        cookie = cookie_lines[1]
        if cookie:
            print("[+] Новый cookie: {}".format(cookie))
            save_cookie_to_file(cookie)
            return cookie
        raise Exception("Cookie не найден.")
    except Exception as e:
        print("[!] Ошибка при захвате cookie: {}".format(e))
        return None


def make_request_with_cookie(cookie):
    headers = {
        "User-Agent": "Mozilla/4.0 (Windows 7 6.1) Java/1.6.0_20",
        "Host": HOST,
        "Accept": "text/html, image/gif, image/jpeg, *; q=.2, */*; q=.2",
        "Connection": "keep-alive",
        "Cookie": cookie,
    }
    try:
        query = urllib.parse.urlencode(PARAMS)
        path = PATH + "?" + query
        conn = http.client.HTTPConnection(HOST, 80, timeout=5)
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return data.decode("latin1")
    except Exception as e:
        print("[!] Ошибка запроса: {}".format(e))
        return None


def extract_return_values(response):
    match = re.search(r"<RETURN_VALUE[^>]*>(.*?)</RETURN_VALUE>", response)
    if not match:
        raise ValueError("RETURN_VALUE не найден")
    raw_data = match.group(1)
    items = re.split(r"%231%23\d%7C", raw_data)
    cleaned_items = [re.sub(r"%231%23\d$", "", item) for item in items]
    return {"R{}".format(i + 1): val for i, val in enumerate(cleaned_items)}


def group_registers(data):
    mapping = {
        "M01": range(1, 20),
        "M02": range(20, 39),
        "M09": range(39, 58),
        "M10": range(58, 77),
        "M11": range(77, 96),
        "M12": range(96, 115),
        "M13": range(115, 134),
    }
    result = {}
    for module, r_range in mapping.items():
        module_data = {}
        new_index = 1
        for i in r_range:
            key = "R{}".format(i)
            if key in data:
                module_data["R{}".format(new_index)] = data[key]
                new_index += 1
        result[module] = module_data
    return result


def main_logic():
    cookie = read_cookie_from_file()
    response = make_request_with_cookie(cookie)
    if response and len(response) >= 2000:
        return extract_return_values(response)
    print("[!] Попытка обновления cookie...")
    new_cookie = update_cookie_via_tshark()
    if not new_cookie:
        print("[x] Не удалось обновить cookie.")
        return None
    response = make_request_with_cookie(new_cookie)
    if response and len(response) >= 2000:
        return extract_return_values(response)
    return None


def notify_server(max_retries=3, backoff_factor=0.5):
    """
    Отправляет статусное уведомление на сервер с повторными попытками (без библиотеки requests).

    :param max_retries: Максимальное количество попыток
    :param backoff_factor: Множитель задержки
    :return: True, если отправлено успешно, иначе False
    """
    parsed_url = urllib.parse.urlparse(API_URL_ALARM)
    host = parsed_url.hostname
    port = parsed_url.port or 80
    path = parsed_url.path or "/"

    payload = {"program_name": PROGRAM_NAME, "api_key": API_KEY}
    body = json.dumps(payload)
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}

    for attempt in range(max_retries):
        try:
            conn = http.client.HTTPConnection(host, port, timeout=5)
            conn.request("POST", path, body, headers)
            response = conn.getresponse()
            resp_body = response.read()

            if response.status == 200:
                logger.info("Статус для {} успешно отправлен.".format(PROGRAM_NAME))
                conn.close()
                return True
            else:
                logger.error(
                    "Ошибка отправки: {} - {}".format(response.status, resp_body)
                )

            conn.close()

        except Exception as e:
            wait_time = backoff_factor * (2**attempt)
            logger.warning(
                "Попытка {}/{} не удалась. Ошибка: {}. Повтор через {:.2f} сек.".format(
                    attempt + 1, max_retries, e, wait_time
                )
            )

            if attempt == max_retries - 1:
                logger.error(
                    "Не удалось отправить статус после {} попыток. Ошибка: {}".format(
                        max_retries, e
                    )
                )
                return False

            time.sleep(wait_time)

    return False


def send_request(url, data):
    max_retries = 5
    delay = 3
    parsed_url = urllib.parse.urlparse(url)
    host = parsed_url.hostname
    port = parsed_url.port or 443
    path = parsed_url.path or "/"
    if parsed_url.query:
        path += "?" + parsed_url.query
    for attempt in range(1, max_retries + 1):
        try:
            body = json.dumps(data)
            headers = config["headers"]
            context = ssl._create_unverified_context()
            conn = http.client.HTTPSConnection(host, port, timeout=5, context=context)
            conn.request("POST", path, body, headers)
            response = conn.getresponse()
            resp_body = response.read()
            if response.status == 200:
                logger.info("Данные отправлены: {}".format(data))
                conn.close()
                return True
            else:
                logger.error(
                    "Ошибка отправки: {} - {}".format(response.status, resp_body)
                )
            conn.close()
        except Exception as e:
            logger.error("Ошибка: {}".format(e))
        if attempt < max_retries:
            logger.info("Повтор {} через {} сек...".format(attempt, delay))
            time.sleep(delay)
        else:
            logger.error("Максимум попыток.")
    return False


def loop_main():
    while True:
        html = main_logic()
        if html:
            grouped = group_registers(html)
            send_request(URL, grouped)
            notify_server()
        else:
            logger.error("Не удалось получить данные.")
        time.sleep(120)  # Задержка перед следующим запросом


if __name__ == "__main__":
    loop_main()
