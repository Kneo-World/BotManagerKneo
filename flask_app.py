import os
import sqlite3
import random
import time
import telebot
from flask import Flask, request

# --- КОНФИГУРАЦИЯ ---
TOKEN = '8202182875:AAEecFwxWQFBjny1-5VrGa9jDKsJaYOKxnA'
DB_PATH = 'kneo_base.db'

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

def db_query(sql, params=(), fetch=False):
    try:
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            if fetch: return cursor.fetchone()
            conn.commit()
    except Exception as e: print(f"DB Error: {e}")
    return None

db_query("CREATE TABLE IF NOT EXISTS users (chat_id int, user_id int, warns int DEFAULT 0, messages int DEFAULT 0, rep int DEFAULT 0, PRIMARY KEY (chat_id, user_id))")

def is_admin(chat_id, user_id):
    if chat_id > 0: return True
    try:
        status = bot.get_chat_member(chat_id, user_id).status
        return status in ['administrator', 'creator']
    except: return False

# --- КОМАНДЫ ---

# 1. МУТ и РАЗМУТ
@bot.message_handler(func=lambda m: m.reply_to_message and m.text and m.text.lower().split()[0] in ['мут', 'размут', '/mute', '/unmute'])
def mute_logic(message):
    if not is_admin(message.chat.id, message.from_user.id): return
    
    target_id = message.reply_to_message.from_user.id
    if is_admin(message.chat.id, target_id):
        bot.reply_to(message, "❌ Нельзя мутить админа!")
        return

    cmd = message.text.lower().split()[0]
    
    if cmd in ['мут', '/mute']:
        # По умолчанию мут на 1 час (3600 сек)
        bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + 3600)
        bot.reply_to(message, f"🔇 {message.reply_to_message.from_user.first_name} замучен на 1 час.")
    
    elif cmd in ['размут', '/unmute']:
        bot.restrict_chat_member(message.chat.id, target_id, 
            can_send_messages=True, can_send_media_messages=True, 
            can_send_other_messages=True, can_add_web_page_previews=True)
        bot.reply_to(message, f"🔊 {message.reply_to_message.from_user.first_name} снова может говорить.")

# 2. ПРОФИЛЬ
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['профиль', 'стата'])
def show_profile(message):
    data = db_query("SELECT warns, messages, rep FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, message.from_user.id), fetch=True)
    w, m, r = data if data else (0, 0, 0)
    bot.reply_to(message, f"👤 **{message.from_user.first_name}**\n⭐ Репутация: {r}\n✉️ Сообщений: {m}\n⚠️ Варны: {w}/5", parse_mode="Markdown")

# 3. БАН и ВАРН
@bot.message_handler(func=lambda m: m.reply_to_message and m.text and m.text.lower().split()[0] in ['бан', 'варн'])
def moder_logic(message):
    if not is_admin(message.chat.id, message.from_user.id): return
    target_id = message.reply_to_message.from_user.id
    cmd = message.text.lower().split()[0]

    if cmd == 'бан':
        bot.ban_chat_member(message.chat.id, target_id)
        bot.reply_to(message, "🔨 Бан!")
    elif cmd == 'варн':
        db_query("INSERT OR IGNORE INTO users (chat_id, user_id) VALUES (?,?)", (message.chat.id, target_id))
        db_query("UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
        res = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, target_id), fetch=True)
        bot.reply_to(message, f"⚠️ Варн! ({res[0]}/5)")

# 4. РЕПУТАЦИЯ (+)
@bot.message_handler(func=lambda m: m.reply_to_message and m.text and m.text.lower() in ['+', 'спасибо'])
def rep_logic(message):
    target = message.reply_to_message.from_user
    if target.id == message.from_user.id or target.is_bot: return
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id) VALUES (?,?)", (message.chat.id, target.id))
    db_query("UPDATE users SET rep = rep + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target.id))
    bot.reply_to(message, f"💎 Репутация {target.first_name} повышена!")

# 5. КНЕО и СЧЁТЧИК
@bot.message_handler(func=lambda m: True)
def all_msg(message):
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id) VALUES (?,?)", (message.chat.id, message.from_user.id))
    db_query("UPDATE users SET messages = messages + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, message.from_user.id))
    if message.text and message.text.lower().startswith('кнео'):
        bot.reply_to(message, random.choice(['Да', 'Нет', '100%']))

# --- WEBHOOK ---
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    webhook_url = f"https://{request.host}/{TOKEN}"
    bot.set_webhook(url=webhook_url)
    return "ONLINE", 200
