import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, date, time, timedelta
import schedule
import threading
import time as time_sleep

# --- Для московского времени ---
import pytz
moscow_tz = pytz.timezone("Europe/Moscow")

# ВАШ ТОКЕН
TOKEN = "7376605355:AAHGXDRBWVjTiwW0uAZFF70B0ggYIu7SU3Q"
bot = telebot.TeleBot(TOKEN)

# Чаты
X_CHAT_ID = -1002345604697
Y_CHAT_ID = -1002282039816
Z_CHAT_ID = -1002402983187

# ---------------------------------------------------------------------------------------
# ТЕКСТЫ ДЛЯ РУССКОГО / УЗБЕКСКОГО
# ---------------------------------------------------------------------------------------
LANG_TEXTS = {
    "Русский": {
        "start": "Здравствуйте! Выберите язык:",
        "main_menu": "Выберите функцию:",
        "go_back": "Вернуться в главное меню",
        "choose_day": "Выберите день для сессии:",
        "choose_time": "Выберите время для {date}:",
        "slot_taken": "Этот слот уже занят.",
        "no_slots": "К сожалению, все слоты на эту дату уже заняты или время прошло.",
        "days": ["Сегодня", "Завтра", "Послезавтра"],
        "slot_booked": (
            "Слот {date} {slot} успешно забронирован!\n\n"
            "Когда наступит время ({slot}), бот пришлёт ссылку на чат X.\n"
            "Ожидайте уведомление от бота."
        ),
        "already_booked_msg": (
            "У вас уже есть активная бронь.\n"
            "Дождитесь окончания текущего сеанса, прежде чем бронировать заново."
        ),
        "notify_time": (
            "Напоминаем, что сейчас {time_str} (по Москве).\n"
            "Вот ваша ссылка для входа в чат X:\n{invite_link}"
        ),
        "link_error": "Ошибка при получении ссылки на чат X: {error}",

        # Тексты для Y/Z
        "link_to_chat": "Ссылка на чат {chat_name}: {link}",
        "link_error_yz": "Ошибка при получении ссылки для {chat_name}: {error}",

        # Доптексты
        "kicked_msg": "Ваш сеанс истёк. Вы были удалены из чата X, ссылка отозвана.",
    },
    "Узбекский": {
        "start": "Salom! Tilni tanlang:",
        "main_menu": "Funktsiyani tanlang:",
        "go_back": "Asosiy menyuga qaytish",
        "choose_day": "Sessiya uchun kunni tanlang:",
        "choose_time": "{date} uchun vaqtni tanlang:",
        "slot_taken": "Bu slot allaqachon band qilingan.",
        "no_slots": "Afsuski, ushbu sana uchun barcha slotlar band yoki vaqt o'tdi.",
        "days": ["Bugun", "Ertaga", "Indinga"],
        "slot_booked": (
            "{date} {slot} slot muvaffaqiyatli band qilindi!\n\n"
            "Vaqti ({slot}) kelganda, bot X chatiga havolani jo'natadi.\n"
            "Bot xabarini kuting."
        ),
        "already_booked_msg": (
            "Sizda allaqachon faol bron mavjud.\n"
            "Yangi bron qilishdan oldin avvalgi seans tugashini kuting."
        ),
        "notify_time": (
            "Eslatma, hozir {time_str} (Moskva vaqti).\n"
            "Mana siz uchun X chatiga havola:\n{invite_link}"
        ),
        "link_error": "X chatiga havola olishda xatolik: {error}",
        "link_to_chat": "{chat_name} chatiga havola: {link}",
        "link_error_yz": "{chat_name} chatiga havola olishda xatolik: {error}",

        "kicked_msg": "Sizning seansingiz tugadi. X chatidan chiqarib yuborildingiz, havola bekor qilindi.",
    }
}

# ---------------------------------------------------------------------------------------
# ДАННЫЕ О ПОЛЬЗОВАТЕЛЯХ, БРОНИРОВАНИЯ, УВЕДОМЛЕНИЯ
# ---------------------------------------------------------------------------------------
# user_language[user_id] = "Русский"/"Узбекский"
user_language = {}

# Словарь броней: (дата, слот) -> user_id
booked_sessions = {}

# Список уведомлений/событий.
# Формат каждого события:
# {
#   "user_id": int,
#   "notify_dt": datetime (tz-aware, Москва),
#   "type": "NOTIFY" или "KICK",
#   "invite_link": str или None,
#   "sent": bool
# }
scheduled_notifications = []

# ---------------------------------------------------------------------------------------
# ФУНКЦИИ ПЕРЕВОДА, ПРОВЕРКИ ЯЗЫКА
# ---------------------------------------------------------------------------------------
def get_lang(user_id):
    return user_language.get(user_id, "Русский")

def tr(user_id, key, **kwargs):
    lang = get_lang(user_id)
    template = LANG_TEXTS[lang].get(key, "")
    if kwargs:
        return template.format(**kwargs)
    return template

# ---------------------------------------------------------------------------------------
# ГЕНЕРАЦИЯ СЛОТОВ (11:00-22:00) ПО МОСКОВСКОМУ ВРЕМЕНИ
# ---------------------------------------------------------------------------------------
def generate_time_slots():
    slots = []
    start_t = time(11, 0)
    end_t = time(22, 0)

    # Берём "сегодня" в Москве
    today_moscow = datetime.now(moscow_tz).date()
    current = datetime.combine(today_moscow, start_t)
    end_dt = datetime.combine(today_moscow, end_t)

    # Превращаем в aware datetime
    current = moscow_tz.localize(current)
    end_dt = moscow_tz.localize(end_dt)

    while current < end_dt:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=30)

    return slots

ALL_TIME_SLOTS = generate_time_slots()

# ---------------------------------------------------------------------------------------
# ПРОВЕРКА, ЕСТЬ ЛИ У ПОЛЬЗОВАТЕЛЯ АКТИВНАЯ БРОНЬ (НА БУДУЩЕЕ ВРЕМЯ)
# ---------------------------------------------------------------------------------------
def user_has_future_booking(user_id):
    now_moscow = datetime.now(moscow_tz)
    for (ds, sl), uid in booked_sessions.items():
        if uid == user_id:
            # Превратим ds+sl в московское время
            dt_naive = datetime.strptime(f"{ds} {sl}", "%Y-%m-%d %H:%M")
            dt_moscow = moscow_tz.localize(dt_naive)
            # Проверяем, не прошло ли ещё время
            # (если сейчас < dt_moscow+30мин — значит сеанс ещё не закончился)
            # Но можно считать "активной" только до начала, это на ваше усмотрение.
            # Допустим, считаем, что активна до конца 30 минут:
            if dt_moscow + timedelta(minutes=30) > now_moscow:
                return True
    return False

# ---------------------------------------------------------------------------------------
# ЗАПЛАНИРОВАТЬ СОБЫТИЕ
# ---------------------------------------------------------------------------------------
def schedule_event(user_id, dt_moscow, event_type, invite_link=None):
    """
    Создаём запись в scheduled_notifications.
    dt_moscow: datetime c tzinfo=Europe/Moscow
    event_type: "NOTIFY" или "KICK"
    invite_link: если уже есть ссылка, которую потом нужно revoke.
    """
    scheduled_notifications.append({
        "user_id": user_id,
        "notify_dt": dt_moscow,
        "type": event_type,
        "invite_link": invite_link,
        "sent": False
    })

# ---------------------------------------------------------------------------------------
# ГЛАВНОЕ МЕНЮ
# ---------------------------------------------------------------------------------------
def show_main_menu(message):
    user_id = message.chat.id if hasattr(message, 'chat') else message.from_user.id

    markup = InlineKeyboardMarkup()
    if get_lang(user_id) == "Узбекский":
        markup.add(InlineKeyboardButton(text="Tibbiy maslahat", callback_data="func_X"))
        markup.add(InlineKeyboardButton(text="Tez yordam chaqirish", callback_data="func_Y"))
        markup.add(InlineKeyboardButton(text="Dori-darmonlarga buyurtma berish", callback_data="func_Z"))
    else:
        markup.add(InlineKeyboardButton(text="Медицинская консультация", callback_data="func_X"))

    bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=message.message_id,
        text=tr(user_id, "main_menu"),
        reply_markup=markup
    )

# ---------------------------------------------------------------------------------------
# ФОНОВЫЙ ШЕДУЛЕР: ОБРАБОТКА СОБЫТИЙ (NOTIFY/KICK)
# ---------------------------------------------------------------------------------------
def check_scheduled_events():
    now_moscow = datetime.now(moscow_tz)
    for task in scheduled_notifications:
        if not task["sent"] and now_moscow >= task["notify_dt"]:
            user_id = task["user_id"]
            event_type = task["type"]
            invite_link = task["invite_link"]

            if event_type == "NOTIFY":
                # Создаём новую ссылку (или используем заранее созданную).
                # Чтобы потом иметь возможность её отозвать, используем create_chat_invite_link.
                try:
                    if not invite_link:
                        # создаём ссылку (без ограничений, но можно добавить expire_date, member_limit)
                        link_obj = bot.create_chat_invite_link(X_CHAT_ID, name="Slot link")
                        invite_link = link_obj.invite_link
                        # Сохраняем эту ссылку в нашу запись, чтобы потом (в KICK) отозвать
                        task["invite_link"] = invite_link

                    time_str = task["notify_dt"].strftime("%H:%M")
                    text_final = tr(
                        user_id, 
                        "notify_time", 
                        time_str=time_str, 
                        invite_link=invite_link
                    )
                except Exception as e:
                    text_final = tr(
                        user_id, 
                        "link_error", 
                        error=str(e)
                    )

                # Отправляем сообщение
                try:
                    bot.send_message(chat_id=user_id, text=text_final)
                except Exception as err:
                    print(f"Не удалось отправить ссылку пользователю {user_id}: {err}")

                task["sent"] = True

            elif event_type == "KICK":
                # Выгоняем пользователя из чата, затем ревокаем ссылку
                try:
                    bot.ban_chat_member(X_CHAT_ID, user_id)
                    # Чтобы пользователь мог заходить в будущем (другие слоты) — сразу "разбаним".
                    bot.unban_chat_member(X_CHAT_ID, user_id)
                except Exception as e:
                    print(f"Ошибка при кике пользователя {user_id}: {e}")

                # Отзываем ссылку, если она была
                if invite_link:
                    try:
                        bot.revoke_chat_invite_link(X_CHAT_ID, invite_link)
                    except Exception as e:
                        print(f"Ошибка при revoke ссылки {invite_link}: {e}")

                # Отправим пользователю сообщение, что сеанс истёк
                try:
                    kicked_msg = tr(user_id, "kicked_msg")
                    bot.send_message(chat_id=user_id, text=kicked_msg)
                except Exception as e:
                    print(f"Не удалось отправить уведомление об окончании {user_id}: {e}")

                task["sent"] = True

def run_schedule_checker():
    while True:
        schedule.run_pending()
        time_sleep.sleep(5)  # раз в 5 секунд можно, или в 10

def start_background_scheduler():
    schedule.every(1).minutes.do(check_scheduled_events)
    t = threading.Thread(target=run_schedule_checker, daemon=True)
    t.start()

# ---------------------------------------------------------------------------------------
# ХЕНДЛЕРЫ
# ---------------------------------------------------------------------------------------
@bot.message_handler(commands=['start'])
def start_command(message):
    markup = InlineKeyboardMarkup()
    for lang in ["Русский", "Узбекский"]:
        markup.add(InlineKeyboardButton(text=lang, callback_data=f"lang_{lang}"))

    bot.send_message(
        chat_id=message.chat.id,
        text="Здравствуйте! Выберите язык:\nSalom! Tilni tanlang:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
def callback_language(call):
    lang_chosen = call.data.split("_", 1)[1]
    user_language[call.from_user.id] = lang_chosen
    show_main_menu(call.message)

@bot.callback_query_handler(func=lambda call: call.data in ["func_X", "func_Y", "func_Z"])
def callback_function_choice(call):
    user_id = call.from_user.id

    # --- ФУНКЦИЯ X ---
    if call.data == "func_X":
        # Проверяем, нет ли уже активной (будущей) брони
        if user_has_future_booking(user_id):
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=tr(user_id, "already_booked_msg")
            )
            return

        # Выбираем день
        markup = InlineKeyboardMarkup()
        days_labels = LANG_TEXTS[get_lang(user_id)]["days"]  # ["Сегодня","Завтра","Послезавтра"]
        for i, day_name in enumerate(days_labels):
            markup.add(InlineKeyboardButton(text=day_name, callback_data=f"day_{i}"))

        markup.add(InlineKeyboardButton(text=tr(user_id, "go_back"), callback_data="go_main_menu"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=tr(user_id, "choose_day"),
            reply_markup=markup
        )

    # --- ФУНКЦИЯ Y ---
    elif call.data == "func_Y":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text=tr(user_id, "go_back"), callback_data="go_main_menu"))

        try:
            link_y = bot.export_chat_invite_link(Y_CHAT_ID)
            text_y = tr(user_id, "link_to_chat", chat_name="Y", link=link_y)
        except Exception as e:
            text_y = tr(user_id, "link_error_yz", chat_name="Y", error=str(e))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text_y,
            reply_markup=markup
        )

    # --- ФУНКЦИЯ Z ---
    elif call.data == "func_Z":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text=tr(user_id, "go_back"), callback_data="go_main_menu"))

        try:
            link_z = bot.export_chat_invite_link(Z_CHAT_ID)
            text_z = tr(user_id, "link_to_chat", chat_name="Z", link=link_z)
        except Exception as e:
            text_z = tr(user_id, "link_error_yz", chat_name="Z", error=str(e))

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text_z,
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("day_"))
def callback_day(call):
    user_id = call.from_user.id

    # Ещё раз проверяем бронь
    if user_has_future_booking(user_id):
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=tr(user_id, "already_booked_msg")
        )
        return

    offset_str = call.data.split("_", 1)[1]
    offset = int(offset_str)

    now_moscow = datetime.now(moscow_tz)
    chosen_date = now_moscow.date() + timedelta(days=offset)
    chosen_date_str = chosen_date.strftime("%Y-%m-%d")

    markup = InlineKeyboardMarkup(row_width=4)
    count_of_buttons = 0

    # Генерируем слоты заново (ALL_TIME_SLOTS — для сегодняшней даты, но формат HH:MM тот же)
    # Мы просто перебирать будем и смотреть actual datetime (вместе с chosen_date)
    for slot in ALL_TIME_SLOTS:
        # Парсим "HH:MM"
        dt_naive = datetime.strptime(f"{chosen_date_str} {slot}", "%Y-%m-%d %H:%M")
        dt_moscow = moscow_tz.localize(dt_naive)
        # Слот только если сейчас < dt_moscow
        if dt_moscow > now_moscow:
            # Проверяем, не занято ли
            if (chosen_date_str, slot) not in booked_sessions:
                markup.add(
                    InlineKeyboardButton(text=slot, callback_data=f"slot_{chosen_date_str}_{slot}")
                )
                count_of_buttons += 1

    markup.add(InlineKeyboardButton(text=tr(user_id, "go_back"), callback_data="go_main_menu"))

    if count_of_buttons == 0:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=tr(user_id, "no_slots"),
            reply_markup=markup
        )
        return

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=tr(user_id, "choose_time", date=chosen_date_str),
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("slot_"))
def callback_timeslot(call):
    user_id = call.from_user.id

    # Проверяем ещё раз
    if user_has_future_booking(user_id):
        bot.answer_callback_query(
            callback_query_id=call.id,
            text=tr(user_id, "already_booked_msg")
        )
        return

    _, chosen_date_str, chosen_slot = call.data.split("_", 2)

    # Проверяем, не занято ли
    if (chosen_date_str, chosen_slot) in booked_sessions:
        bot.answer_callback_query(
            callback_query_id=call.id,
            text=tr(user_id, "slot_taken")
        )
        return

    # Бронируем
    booked_sessions[(chosen_date_str, chosen_slot)] = user_id

    # Определяем datetime (начало слота) в Москве
    dt_naive = datetime.strptime(f"{chosen_date_str} {chosen_slot}", "%Y-%m-%d %H:%M")
    dt_moscow = moscow_tz.localize(dt_naive)

    # Событие 1: NOTIFY (в начало слота)
    schedule_event(user_id, dt_moscow, "NOTIFY", invite_link=None)

    # Событие 2: KICK (спустя 30 минут)
    dt_kick = dt_moscow + timedelta(minutes=30)
    schedule_event(user_id, dt_kick, "KICK", invite_link=None)

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text=tr(user_id, "go_back"), callback_data="go_main_menu"))

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=tr(user_id, "slot_booked", date=chosen_date_str, slot=chosen_slot),
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "go_main_menu")
def callback_go_main_menu(call):
    show_main_menu(call.message)

# ---------------------------------------------------------------------------------------
# ЗАПУСК
# ---------------------------------------------------------------------------------------
if __name__ == "__main__":
    print("Bot is running...")
    start_background_scheduler()
    bot.infinity_polling()
