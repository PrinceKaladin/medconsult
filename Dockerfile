# Используем базовый образ Python
FROM python:3.12-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы проекта
COPY bot.py ./
COPY requirements.txt ./

# Устанавливаем зависимости
RUN pip install -r requirements.txt

# Скрипт для автоматического перезапуска

# Указываем команду запуска контейнера
CMD ["sh", "-c","python3 bot.py"]
