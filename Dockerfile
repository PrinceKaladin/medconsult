# Используем базовый образ Python
FROM python:3.12-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы проекта
COPY bot.py ./
COPY requirements.txt ./
CMD pip install -r requirements.txt && python3 bot.py
# Устанавливаем зависимости

