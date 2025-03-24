#!/bin/bash

# Функция для вывода ошибок
error_exit() {
    echo "Ошибка: $1" >&2
    exit 1
}

# Функция для проверки версии Python
check_python_version() {
    local required_version="3.11"
    local current_version=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))" 2>/dev/null)

    if [[ -z "$current_version" ]]; then
        echo "Python не установлен"
        return 1
    fi

    # Сравнение версий
    if [[ "$(printf '%s\n' "$required_version" "$current_version" | sort -V | head -n1)" != "$required_version" ]]; then
        echo "Требуется Python $required_version, установлена версия $current_version"
        return 1
    fi

    return 0
}

# Улучшенная функция установки пакета
install_package() {
    local package_name="$1"
    local package_install="$2"
    local max_attempts=3
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if ! command -v "$package_name" &>/dev/null; then
            echo "Устанавливаем $package_name..."
            sudo apt update
            if sudo apt install -y "$package_install"; then
                echo "$package_name успешно установлен"
                return 0
            else
                ((attempt++))
                echo "Попытка $attempt установки $package_name не удалась"

                if [ $attempt -eq $max_attempts ]; then
                    echo "Не удалось установить $package_name после $max_attempts попыток" >&2
                    return 1
                fi

                sleep 2  # Пауза между попытками
            fi
        else
            echo "$package_name уже установлен."
            return 0
        fi
    done
}

# Функция для проверки и конвертации файла в Unix-формат
convert_to_unix_format() {
    local file_path="$1"
    
    # Проверка наличия dos2unix
    if ! command -v dos2unix &>/dev/null; then
        echo "Устанавливаем dos2unix..."
        sudo apt update
        sudo apt install -y dos2unix
    fi
    
    # Проверка формата файла
    if file "$file_path" | grep -q "with CRLF line terminators"; then
        echo "Конвертация $file_path в Unix-формат..."
        dos2unix "$file_path"
    fi
}

# Конвертация текущего скрипта
convert_to_unix_format "$0"

# Проверка операционной системы
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    error_exit "Скрипт поддерживает только Linux-системы"
fi

# Проверка версии Python перед установкой
if ! check_python_version; then
    echo "Установка Python $required_version..."
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update
    sudo apt install -y python3.11 python3.11-venv
fi

# Получаем текущий путь
CURRENT_DIR=$(pwd)

# Проверка доступа sudo с таймаутом
echo "Проверка прав sudo..."
if ! sudo -v -n 2>/dev/null; then
    read -sp "Введите пароль sudo: " SUDO_PASSWORD
    echo "$SUDO_PASSWORD" | sudo -S -v || error_exit "Не удалось получить права sudo"
fi

# Установка необходимых пакетов
install_package python3.11 "python3.11 python3.11-venv"
install_package pip "python3-pip"
install_package node "nodejs npm"

# Установка PM2
if ! command -v pm2 &>/dev/null; then
    echo "Устанавливаем PM2..."
    sudo npm install -g pm2 || error_exit "Не удалось установить PM2"
else
    echo "PM2 уже установлен."
fi

# Генерация имени виртуального окружения
DEFAULT_VENV_NAME="modbus_venv"
read -p "Введите название виртуального окружения [$DEFAULT_VENV_NAME]: " VENV_NAME
VENV_NAME=${VENV_NAME:-$DEFAULT_VENV_NAME}

# Проверка существования виртуального окружения
if [ -d "$VENV_NAME" ]; then
    read -p "Виртуальное окружение $VENV_NAME уже существует. Перезаписать? (y/n): " OVERWRITE
    if [[ "$OVERWRITE" != "y" ]]; then
        error_exit "Операция отменена пользователем"
    fi
    rm -rf "$VENV_NAME"
fi

# Создание виртуального окружения
echo "Создаем виртуальное окружение $VENV_NAME..."
python3.11 -m venv "$VENV_NAME" || error_exit "Не удалось создать виртуальное окружение"

# Активация виртуального окружения
echo "Активируем виртуальное окружение $VENV_NAME..."
source "$VENV_NAME/bin/activate"

# Установка зависимостей
if [ ! -f "requirements.txt" ]; then
    echo "Создаем базовый requirements.txt..."
    touch requirements.txt
    echo "# Добавьте необходимые зависимости" > requirements.txt
fi

echo "Устанавливаем зависимости из requirements.txt..."
pip install -r requirements.txt || error_exit "Не удалось установить зависимости"

# Создание стартового скрипта
START_SCRIPT="$CURRENT_DIR/$VENV_NAME/start_script.sh"
echo "Создаем скрипт $START_SCRIPT..."

mkdir -p "$CURRENT_DIR/$VENV_NAME"

cat <<EOL > "$START_SCRIPT"
#!/bin/bash
cd $CURRENT_DIR/$VENV_NAME
source $CURRENT_DIR/$VENV_NAME/bin/activate
python3 main.py
EOL

# Делаем файл исполняемым
chmod +x "$START_SCRIPT"

# Запуск скрипта через pm2
echo "Запускаем скрипт с помощью pm2..."
pm2 start "$START_SCRIPT" --name "$VENV_NAME" || error_exit "Не удалось запустить скрипт через PM2"

echo "Скрипт $START_SCRIPT успешно создан и запущен через pm2 с именем $VENV_NAME."
pm2 list

echo "Проект успешно настроен!"