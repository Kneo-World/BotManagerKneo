import os
import sqlite3
import random
import time
import re
import telebot
from flask import Flask, request

# --- [ КОНФИГУРАЦИЯ ] ---
TOKEN = '8202182875:AAEecFwxWQFBjny1-5VrGa9jDKsJaYOKxnA'
DB_PATH = 'kneo_base.db'

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

# --- [ СИСТЕМА БАЗЫ ДАННЫХ ] ---
def db_query(sql, params=(), fetch=False):
    try:
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params)
            if fetch: return cursor.fetchone()
            conn.commit()
    except Exception as e:
        print(f"🆘 Ошибка БД: {e}")
    return None

# Таблица пользователей
db_query('''CREATE TABLE IF NOT EXISTS users 
    (chat_id int, user_id int, username text, warns int DEFAULT 0, messages int DEFAULT 0, rep int DEFAULT 0, 
    PRIMARY KEY (chat_id, user_id))''')

# --- [ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ] ---
def check_admin(message):
    if message.chat.type == 'private': return True
    try:
        status = bot.get_chat_member(message.chat.id, message.from_user.id).status
        return status in ['administrator', 'creator']
    except: return False

def parse_time(text):
    match = re.search(r'(\d+)([мчд])', text.lower())
    if not match: return 3600
    amount, unit = int(match.group(1)), match.group(2)
    if unit == 'м': return amount * 60
    if unit == 'ч': return amount * 3600
    if unit == 'д': return amount * 86400
    return 3600

def get_target_id(message):
    """Определяет ID цели: через реплай или через @упоминание."""
    # 1. Если есть реплай
    if message.reply_to_message:
        return message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name
    
    # 2. Если есть упоминание через @
    # Ищем в тексте сообщения или в entities (метаданных телеграма)
    target_username = None
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                target_username = message.text[entity.offset+1:entity.offset+entity.length].lower()
                break
    
    if not target_username:
        # Поиск через регулярку, если entities не сработали
        match = re.search(r'@(\w+)', message.text)
        if match:
            target_username = match.group(1).lower()

    if target_username:
        # Ищем ID в нашей базе по юзернейму
        res = db_query("SELECT user_id FROM users WHERE chat_id=? AND LOWER(username)=?", (message.chat.id, target_username), fetch=True)
        if res:
            return res['user_id'], f"@{target_username}"
        else:
            bot.reply_to(message, f"❌ Я еще не знаю пользователя @{target_username}. Он должен написать хоть одно сообщение!")
    
    return None, None

# --- [ ГЛАВНЫЙ ОБРАБОТЧИК МОДЕРАЦИИ ] ---

@bot.message_handler(func=lambda m: m.text and m.text.lower().split()[0] in ['мут', 'бан', 'кик', 'варн', 'размут', 'разбан', 'анварн'])
def moder_commands(message):
    if not check_admin(message):
        return

    cmd = message.text.lower().split()[0]
    target_id, target_name = get_target_id(message)

    if not target_id:
        return # Если не нашли цель, просто выходим (текст ошибки уже выдан в get_target_id)

    try:
        # Проверка: не пытаемся ли мы наказать админа
        target_status = bot.get_chat_member(message.chat.id, target_id).status
        if target_status in ['administrator', 'creator'] and cmd not in ['разбан', 'размут', 'анварн']:
            return bot.reply_to(message, "❌ Нельзя наказывать администраторов!")

        if cmd == 'бан':
            bot.ban_chat_member(message.chat.id, target_id)
            bot.reply_to(message, f"🔨 **{target_name}** забанен!")

        elif cmd == 'разбан':
            # Снимаем бан (разрешаем вход)
            bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
            bot.reply_to(message, f"✅ **{target_name}** разбанен! Теперь он может войти.")

        elif cmd == 'мут':
            seconds = parse_time(message.text)
            bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + seconds)
            bot.reply_to(message, f"🔇 **{target_name}** в муте на {seconds//60} мин.")

        elif cmd == 'размут':
            bot.restrict_chat_member(message.chat.id, target_id, 
                can_send_messages=True, can_send_media_messages=True, 
                can_send_other_messages=True, can_add_web_page_previews=True)
            bot.reply_to(message, f"🔊 Мут с **{target_name}** снят.")

        elif cmd == 'варн':
            db_query("UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            data = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, target_id), fetch=True)
            bot.reply_to(message, f"⚠️ **{target_name}** получил варн! ({data['warns']}/3)")

        elif cmd == 'анварн':
            db_query("UPDATE users SET warns = MAX(0, warns - 1) WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            data = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, target_id), fetch=True)
            bot.reply_to(message, f"🗑 У **{target_name}** снят варн. Всего: {data['warns']}")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка выполнения: `{e}`")

# --- [ ОБЩАЯ ЛОГИКА ] ---

@bot.message_handler(func=lambda m: True)
def global_logic(message):
    # СОХРАНЕНИЕ ЮЗЕРНЕЙМА (Важно для поиска)
    current_username = message.from_user.username.lower() if message.from_user.username else None
    
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id, username) VALUES (?,?,?)", 
             (message.chat.id, message.from_user.id, current_username))
    
    # Обновляем юзернейм при каждом сообщении (если человек его сменил)
    db_query("UPDATE users SET messages = messages + 1, username = ? WHERE chat_id=? AND user_id=?", 
             (current_username, message.chat.id, message.from_user.id))
    
    if message.text and message.text.lower().startswith('кнео'):
        bot.reply_to(message, f"🔮 {random.choice(['Да', 'Нет', '100%', 'Нет иди нахуй', 'Я думаю лутче тебе пойти нахуй')}")

# --- [ WEBHOOK ] ---
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    bot.set_webhook(url=f"https://{request.host}/{TOKEN}")
    return "ONLINE", 200
