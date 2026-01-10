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

# Таблица пользователей (добавили username для поиска)
db_query('''CREATE TABLE IF NOT EXISTS users 
    (chat_id int, user_id int, username text, warns int DEFAULT 0, messages int DEFAULT 0, rep int DEFAULT 0, 
    PRIMARY KEY (chat_id, user_id))''')

# --- [ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ] ---
def check_admin(message):
    if message.chat.type == 'private': return True
    status = bot.get_chat_member(message.chat.id, message.from_user.id).status
    return status in ['administrator', 'creator']

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
    if message.reply_to_message:
        return message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name
    
    # Ищем юзернейм в тексте
    match = re.search(r'@(\w+)', message.text)
    if match:
        username = match.group(1).lower()
        res = db_query("SELECT user_id, username FROM users WHERE chat_id=? AND LOWER(username)=?", (message.chat.id, username), fetch=True)
        if res:
            return res['user_id'], f"@{res['username']}"
    return None, None

# --- [ ГЛАВНЫЙ ОБРАБОТЧИК МОДЕРАЦИИ ] ---

@bot.message_handler(func=lambda m: m.text and m.text.lower().split()[0] in ['мут', 'бан', 'кик', 'варн', 'размут', 'разбан', 'анварн'])
def moder_commands(message):
    if not check_admin(message):
        return bot.reply_to(message, "⚠️ Команда только для админов!")

    cmd = message.text.lower().split()[0]
    target_id, target_name = get_target_id(message)

    if not target_id:
        return bot.reply_to(message, "💬 Укажите пользователя (ответ на сообщение или @упоминание).")

    try:
        if cmd == 'бан':
            bot.ban_chat_member(message.chat.id, target_id)
            bot.reply_to(message, f"🔨 **{target_name}** забанен!")

        elif cmd == 'разбан':
            bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
            bot.reply_to(message, f"✅ **{target_name}** разбанен!")

        elif cmd == 'мут':
            seconds = parse_time(message.text)
            bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + seconds)
            bot.reply_to(message, f"🔇 **{target_name}** в муте на {seconds//60} мин.")

        elif cmd == 'размут':
            bot.restrict_chat_member(message.chat.id, target_id, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)
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
        bot.reply_to(message, f"❌ Ошибка: `{e}`")

# --- [ ОБЩИЕ ФУНКЦИИ ] ---

@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['профиль', 'стата'])
def profile(message):
    res = db_query("SELECT warns, messages, rep FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, message.from_user.id), fetch=True)
    bot.reply_to(message, f"👤 **{message.from_user.first_name}**\n⭐ Репутация: `{res['rep']}`\n✉️ Сообщений: `{res['messages']}`\n⚠️ Варны: `{res['warns']}/3`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def global_logic(message):
    # Сохраняем/обновляем данные пользователя в БД (включая username)
    uname = message.from_user.username if message.from_user.username else "None"
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id, username) VALUES (?,?,?)", (message.chat.id, message.from_user.id, uname))
    db_query("UPDATE users SET messages = messages + 1, username = ? WHERE chat_id=? AND user_id=?", (uname, message.chat.id, message.from_user.id))
    
    if message.text and message.text.lower().startswith('кнео'):
        bot.reply_to(message, f"🔮 {random.choice(['Да', 'Нет', 'Возможно', '100%'])}")

# --- [ WEBHOOK ] ---
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    bot.set_webhook(url=f"https://{request.host}/{TOKEN}")
    return "ONLINE", 200
