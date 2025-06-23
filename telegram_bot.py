import telebot
import sqlite3
from datetime import datetime, timedelta
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import logging
import requests

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = "8062458756:AAEp4dollJEMbebdb6dVRR1jpemyx1GoMF8"
DB_PATH = "database/techrevive.db"
SERVICE_CENTERS = [
    "Москва, ул. Тверская, д. 15",
    "Санкт-Петербург, Невский пр., д. 22",
    "Казань, ул. Баумана, д. 51",
    "Екатеринбург, ул. Ленина, д. 25",
    "Новосибирск, ул. Горская, д. 10",
]
AVAILABLE_HOURS = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]
WELCOME_IMAGE_URL = "https://i.yapx.cc/ZW22C.png"

# Инициализация бота
bot = telebot.TeleBot(TOKEN)

# Хранилище данных пользователя
user_data = {}

# Проверка доступности изображения
def is_image_url_valid(url):
    try:
        response = requests.head(url, timeout=5)
        return response.status_code == 200 and 'image' in response.headers.get('Content-Type', '')
    except requests.RequestException:
        return False

# Получение доступных дат
def get_available_dates():
    dates = []
    today = datetime.now()
    for i in range(7):
        date = (today + timedelta(days=i)).strftime("%Y-%m-%d")
        dates.append(date)
    return dates

# Получение доступных слотов времени
def get_available_times(date):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT time FROM appointments WHERE date = ? AND status IN ('confirmed', 'accepted')", (date,))
    booked_times = [row['time'] for row in cursor.fetchall()]
    conn.close()
    return [time for time in AVAILABLE_HOURS if time not in booked_times]

# Обработка команды /start
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    user_data[user_id] = {}
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("📞 Отправить номер телефона", request_contact=True))
    welcome_text = (
        "*Добро пожаловать в TechRevive!* 🚀\n"
        "Мы вернем вашу технику к жизни! 📱\n\n"
        "Для записи на *бесплатную диагностику* отправьте свой номер телефона 👇"
    )
    try:
        if is_image_url_valid(WELCOME_IMAGE_URL):
            bot.send_photo(
                message.chat.id,
                WELCOME_IMAGE_URL,
                caption=welcome_text,
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            bot.send_message(
                message.chat.id,
                welcome_text,
                parse_mode="Markdown",
                reply_markup=markup
            )
    except Exception as e:
        logger.error(f"Ошибка отправки изображения: {e}")
        bot.send_message(
            message.chat.id,
            welcome_text,
            parse_mode="Markdown",
            reply_markup=markup
        )

# Обработка номера телефона
@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    user_id = message.from_user.id
    phone = message.contact.phone_number
    user_data[user_id]['phone'] = phone
    user_data[user_id]['name'] = message.from_user.first_name or "Не указано"
    user_data[user_id]['user_id'] = user_id
    markup = InlineKeyboardMarkup()
    for index, center in enumerate(SERVICE_CENTERS):
        markup.add(InlineKeyboardButton(f"🏠 {center}", callback_data=f"center_{index}"))
    bot.send_message(
        message.chat.id,
        "*Выберите сервисный центр:* 🌍\n\nГде вы хотите пройти диагностику?",
        parse_mode="Markdown",
        reply_markup=markup
    )

# Обработка выбора сервисного центра
@bot.callback_query_handler(func=lambda call: call.data.startswith('center_'))
def handle_center(call):
    user_id = call.from_user.id
    center_index = int(call.data.replace('center_', ''))
    center = SERVICE_CENTERS[center_index]
    user_data[user_id]['service_center'] = center
    markup = InlineKeyboardMarkup()
    for date in get_available_dates():
        markup.add(InlineKeyboardButton(f"📅 {date}", callback_data=f"date_{date}"))
    bot.edit_message_text(
        "*Выберите дату:* 🗓️\n\nКогда вам удобно приехать?",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )

# Обработка выбора даты
@bot.callback_query_handler(func=lambda call: call.data.startswith('date_'))
def handle_date(call):
    user_id = call.from_user.id
    date = call.data.replace('date_', '')
    user_data[user_id]['date'] = date
    available_times = get_available_times(date)
    if not available_times:
        bot.edit_message_text(
            "😔 На эту дату нет свободных слотов.\n*Выберите другую дату:* 🗓️",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )
        return
    markup = InlineKeyboardMarkup()
    for time in available_times:
        markup.add(InlineKeyboardButton(f"⏰ {time}", callback_data=f"time_{time}"))
    bot.edit_message_text(
        "*Выберите время:* ⏰\n\nКакое время вам подходит?",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )

# Обработка выбора времени
@bot.callback_query_handler(func=lambda call: call.data.startswith('time_'))
def handle_time(call):
    user_id = call.from_user.id
    time = call.data.replace('time_', '')
    user_data[user_id]['time'] = time
    data = user_data[user_id]
    confirmation_text = (
        "*Подтвердите запись:* ✅\n\n"
        f"👤 *Имя*: {data['name']}\n"
        f"📞 *Телефон*: {data['phone']}\n"
        f"🏠 *Сервисный центр*: {data['service_center']}\n"
        f"🗓️ *Дата*: {data['date']}\n"
        f"⏰ *Время*: {data['time']}"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"))
    markup.add(InlineKeyboardButton("❌ Отменить", callback_data="cancel"))
    bot.edit_message_text(
        confirmation_text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )

# Обработка подтверждения или отмены
@bot.callback_query_handler(func=lambda call: call.data in ['confirm', 'cancel'])
def handle_confirmation(call):
    user_id = call.from_user.id
    if call.data == 'confirm':
        data = user_data[user_id]
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO appointments (user_id, name, phone, service_center, date, time) VALUES (?, ?, ?, ?, ?, ?)
        ''', (data['user_id'], data['name'], data['phone'], data['service_center'], data['date'], data['time']))
        conn.commit()
        appointment_id = cursor.lastrowid
        conn.close()
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("❌ Отменить запись", callback_data=f"cancel_{appointment_id}"))
        bot.edit_message_text(
            "🎉 *Запись подтверждена!* (ID: {})\n\n"
            "Вы получите *скидку 15%* на ремонт. Мы свяжемся с вами для подтверждения. Спасибо! 😊".format(appointment_id),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    else:
        bot.edit_message_text(
            "❌ *Запись отменена.*\n\n"
            "Если хотите начать заново, используйте команду /start.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )
    del user_data[user_id]

# Обработка отмены записи
@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_'))
def handle_cancel(call):
    appointment_id = int(call.data.replace('cancel_', ''))
    user_id = call.from_user.id
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM appointments WHERE id = ? AND user_id = ?", (appointment_id, user_id))
    if cursor.rowcount > 0:
        conn.commit()
        bot.edit_message_text(
            "❌ *Запись (ID: {}) успешно отменена.*\n\n"
            "Для новой записи используйте /start.".format(appointment_id),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )
    else:
        bot.edit_message_text(
            "😔 Запись не найдена или уже отменена.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )
    conn.close()

# Запуск бота
if __name__ == '__main__':
    bot.infinity_polling()