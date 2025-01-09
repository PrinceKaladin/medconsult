import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta, time
import schedule
import threading
import time as time_sleep

# ===== НАСТРОЙКИ И КОНСТАНТЫ =====
TOKEN = "7376605355:AAHGXDRBWVjTiwW0uAZFF70B0ggYIu7SU3Q"
bot = telebot.TeleBot(TOKEN)

X_CHAT_ID = -1002345604697
Y_CHAT_ID = -1002282039816
Z_CHAT_ID = -1002402983187

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
        "notify_time": (
            "Напоминаем, что сейчас {time_str}.\n"
            "Вот ваша ссылка для входа в чат X:\n{invite_link}"
        ),
        "link_error": "Ошибка при получении ссылки на чат X: {error}",
        "already_booked_msg": (
            "У вас уже есть активная бронь.\n"
            "Дождитесь окончания текущего сеанса, прежде чем бронировать заново."
        ),
        # Тексты для Y/Z
        "link_to_chat": "Ссылка на чат {chat_name}: {link}",
        "link_error_yz": "Ошибка при получении ссылки для {chat_name}: {error}",
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
        "notify_time": (
            "Eslatma, hozir {time_str}.\n"
            "Mana siz uchun X chatiga havola:\n{invite_link}"
        ),
        "link_error": "X chatiga havola olishda xatolik: {error}",
        "already_booked_msg": (
            "Sizda allaqachon faol bron mavjud.\n"
            "Yangi bron qilishdan oldin avvalgi seans tugashini kuting."
        ),
        # Тексты для Y/Z
        "link_to_chat": "{chat_name} chatiga havola: {link}",
        "link_error_yz": "{chat_name} chatiga havola olishda xatolik: {error}",
    }
}

# Выбранный язык: user_id -> "Русский"/"Узбекский"
user_language = {}

# Бронирования: (дата, слот) -> user_id
booked_sessions = {}

# Запланированные уведомления о начале сеанса (для X):
scheduled_notifications = []

# -------------------------------------------------------------------
# ФУНКЦИИ ДЛЯ ПЕРЕВОДА И ПРОВЕРКИ ЯЗЫКА
# -------------------------------------------------------------------
def get_lang(user_id):
    return user_language.get(user_id, "Русский")

def tr(user_id, key, **kwargs):
    lang = get_lang(user_id)
    template = LANG_TEXTS[lang].get(key, "")
    if kwargs:
        return template.format(**kwargs)
    return template

# -------------------------------------------------------------------
# ГЕНЕРАЦИЯ СЛОТОВ (каждые 30 минут с 11:00 до 22:00)
# -------------------------------------------------------------------
def generate_time_slots():
    slots = []
    start_time = time(11, 0)
    end_time   = time(22, 0)
    current = datetime.combine(datetime.today(), start_time)
    end_dt = datetime.combine(datetime.today(), end_time)

    while current < end_dt:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=30)
    return slots

ALL_TIME_SLOTS = generate_time_slots()

# -------------------------------------------------------------------
# ПРОВЕРКА, ЕСТЬ ЛИ У ПОЛЬЗОВАТЕЛЯ ЕЩЁ НЕ ИСТЕКШАЯ БРОНЬ
# -------------------------------------------------------------------
def user_has_future_booking(user_id):
    """
    Если в словаре booked_sessions найдётся слот (дата+время),
    которое ещё не наступило, значит у пользователя уже есть бронь в будущем.
    """
    now = datetime.now()
    for (ds, sl), uid in booked_sessions.items():
        if uid == user_id:
            dt = datetime.strptime(f"{ds} {sl}", "%Y-%m-%d %H:%M")
            # Проверяем, не прошло ли уже время
            if dt >= now:
                return True
    return False

# -------------------------------------------------------------------
# ГЛАВНОЕ МЕНЮ
# -------------------------------------------------------------------
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

# -------------------------------------------------------------------
# ФОНОВАЯ ПРОВЕРКА ЗАПЛАНИРОВАННЫХ УВЕДОМЛЕНИЙ
# -------------------------------------------------------------------
def check_scheduled_events():
    now = datetime.now()
    for task in scheduled_notifications:
        if not task["sent"] and now >= task["notify_dt"]:
            user_id = task["user_id"]
            # Пробуем получить ссылку на чат X
            try:
                link = bot.export_chat_invite_link(X_CHAT_ID)
                time_str = task["notify_dt"].strftime("%H:%M")
                text_final = tr(
                    user_id, 
                    "notify_time", 
                    time_str=time_str, 
                    invite_link=link
                )
            except Exception as e:
                text_final = tr(
                    user_id, 
                    "link_error", 
                    error=str(e)
                )

            # Отправим пользователю личное сообщение
            try:
                bot.send_message(chat_id=user_id, text=text_final)
            except Exception as err:
                print(f"Не удалось отправить ссылку пользователю {user_id}: {err}")

            task["sent"] = True

def run_schedule_checker():
    while True:
        schedule.run_pending()
        time_sleep.sleep(10)

def start_background_scheduler():
    schedule.every(1).minutes.do(check_scheduled_events)
    t = threading.Thread(target=run_schedule_checker, daemon=True)
    t.start()

# -------------------------------------------------------------------
# ХЕНДЛЕРЫ
# -------------------------------------------------------------------
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
        # Проверяем, нет ли у пользователя уже активной (будущей) брони
        if user_has_future_booking(user_id):
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=tr(user_id, "already_booked_msg")  # "У вас уже есть активная бронь..."
            )
            return

        markup = InlineKeyboardMarkup()
        days_labels = LANG_TEXTS[get_lang(user_id)]["days"]
        for i, day_name in enumerate(days_labels):
            markup.add(InlineKeyboardButton(text=day_name, callback_data=f"day_{i}"))

        markup.add(
            InlineKeyboardButton(text=tr(user_id, "go_back"), callback_data="go_main_menu")
        )

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=tr(user_id, "choose_day"),
            reply_markup=markup
        )

    # --- ФУНКЦИЯ Y ---
    elif call.data == "func_Y":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(text=tr(user_id, "go_back"), callback_data="go_main_menu")
        )

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
        markup.add(
            InlineKeyboardButton(text=tr(user_id, "go_back"), callback_data="go_main_menu")
        )

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

    # Повторно проверяем — вдруг пользователь быстро нажал кнопку, пока мы не вернулись в главное меню
    if user_has_future_booking(user_id):
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=tr(user_id, "already_booked_msg")
        )
        return

    offset_str = call.data.split("_", 1)[1]
    offset = int(offset_str)

    chosen_date = (datetime.now() + timedelta(days=offset)).date()
    chosen_date_str = chosen_date.strftime("%Y-%m-%d")

    markup = InlineKeyboardMarkup(row_width=4)
    count_of_buttons = 0

    for slot in ALL_TIME_SLOTS:
        date_time_str = f"{chosen_date_str} {slot}"
        date_time_obj = datetime.strptime(date_time_str, "%Y-%m-%d %H:%M")
        if date_time_obj < datetime.now():
            continue
        if (chosen_date_str, slot) not in booked_sessions:
            markup.add(
                InlineKeyboardButton(
                    text=slot,
                    callback_data=f"slot_{chosen_date_str}_{slot}"
                )
            )
            count_of_buttons += 1

    markup.add(
        InlineKeyboardButton(text=tr(user_id, "go_back"), callback_data="go_main_menu")
    )

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

    # На всякий случай ещё раз проверяем
    if user_has_future_booking(user_id):
        bot.answer_callback_query(
            callback_query_id=call.id,
            text=tr(user_id, "already_booked_msg")
        )
        return

    _, chosen_date_str, chosen_slot = call.data.split("_", 2)

    # Проверяем, не занято ли (на всякий случай)
    if (chosen_date_str, chosen_slot) in booked_sessions:
        bot.answer_callback_query(
            callback_query_id=call.id,
            text=tr(user_id, "slot_taken")
        )
        return

    # Бронируем
    booked_sessions[(chosen_date_str, chosen_slot)] = user_id

    # Запланируем уведомление
    date_time_obj = datetime.strptime(f"{chosen_date_str} {chosen_slot}", "%Y-%m-%d %H:%M")
    scheduled_notifications.append({
        "user_id": user_id,
        "notify_dt": date_time_obj,
        "sent": False
    })

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton(text=tr(user_id, "go_back"), callback_data="go_main_menu")
    )

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=tr(user_id, "slot_booked", date=chosen_date_str, slot=chosen_slot),
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "go_main_menu")
def callback_go_main_menu(call):
    show_main_menu(call.message)

# -------------------------------------------------------------------
# ЗАПУСК
# -------------------------------------------------------------------
if __name__ == "__main__":
    print("Bot is running...")
    start_background_scheduler()
    bot.infinity_polling()
