# Используем базовый образ Python
FROM python:3.12-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы проекта
COPY bot.py ./
COPY requirements.txt ./

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Скрипт для автоматического перезапуска
COPY restart.sh /app/restart.sh
RUN chmod +x /app/restart.sh

# Указываем команду запуска контейнера
CMD ["/bin/bash", "-c", "./restart.sh"]
