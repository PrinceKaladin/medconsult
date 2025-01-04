# Используем базовый образ Python
FROM python:3.9


# Устанавливаем рабочую директорию
WORKDIR /app

ADD requirements.txt requirements.txt
ADD bot.py bot.py


RUN pip install -r requirements.txt

CMD ["sh", "-c", "python3 bot.py & sleep infinity"]
