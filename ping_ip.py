import subprocess

# Диапазон IP-адресов
start_ip = 201
end_ip = 224
base_ip = "192.168.75."


# Функция для проверки доступности IP-адреса
def ping_ip(ip):
    try:
        result = subprocess.run(["ping", "-n", "1", ip], capture_output=True, text=True)
        if "TTL=" in result.stdout:
            print(f"{ip} доступен")
        else:
            print(f"{ip} недоступен")
    except Exception as e:
        print(f"Ошибка при проверке {ip}: {e}")


# Перебор всех IP в указанном диапазоне
for i in range(start_ip, end_ip + 1):
    ip = f"{base_ip}{i}"
    ping_ip(ip)

input("Нажмите Enter для завершения...")
