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
    if message.reply_to_message:
        return message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name
    match = re.search(r'@(\w+)', message.text)
    if match:
        target_username = match.group(1).lower()
        res = db_query("SELECT user_id FROM users WHERE chat_id=? AND LOWER(username)=?", (message.chat.id, target_username), fetch=True)
        if res: return res['user_id'], f"@{target_username}"
        else: bot.reply_to(message, f"❌ Я не знаю @{target_username}"); return None, None
    return None, None

# --- [ 1. РЕПУТАЦИЯ ] ---
@bot.message_handler(func=lambda m: m.reply_to_message and m.text and m.text.lower() in ['+', 'спасибо', 'сяп', 'респект', 'благодарю'])
def rep_logic(message):
    target = message.reply_to_message.from_user
    if target.id == message.from_user.id:
        return bot.reply_to(message, "самолайк — это грех 🙃")
    if target.is_bot:
        return bot.reply_to(message, "Ботам репутация ни к чему 🤖")

    db_query("INSERT OR IGNORE INTO users (chat_id, user_id, username) VALUES (?,?,?)", 
             (message.chat.id, target.id, target.username.lower() if target.username else "none"))
    db_query("UPDATE users SET rep = rep + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target.id))
    
    bot.reply_to(message, f"💎 Репутация **{target.first_name}** повышена!", parse_mode="Markdown")

# --- [ 2. МОДЕРАЦИЯ ] ---
@bot.message_handler(func=lambda m: m.text and m.text.lower().split()[0] in ['мут', 'бан', 'кик', 'варн', 'размут', 'разбан', 'анварн'])
def moder_commands(message):
    if not check_admin(message): return
    cmd = message.text.lower().split()[0]
    target_id, target_name = get_target_id(message)
    if not target_id: return

    try:
        t_status = bot.get_chat_member(message.chat.id, target_id).status
        if t_status in ['administrator', 'creator'] and cmd not in ['разбан', 'размут', 'анварн']:
            return bot.reply_to(message, "❌ Админы неприкосновенны!")

        if cmd == 'бан':
            bot.ban_chat_member(message.chat.id, target_id)
            bot.reply_to(message, f"🔨 **{target_name}** забанен!")
        elif cmd == 'разбан':
            bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
            bot.reply_to(message, f"✅ **{target_name}** разбанен!")
        elif cmd == 'мут':
            sec = parse_time(message.text)
            bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + sec)
            bot.reply_to(message, f"🔇 **{target_name}** в муте на {sec//60} мин.")
        elif cmd == 'размут':
            bot.restrict_chat_member(message.chat.id, target_id, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)
            bot.reply_to(message, f"🔊 Мут с **{target_name}** снят.")
        elif cmd == 'варн':
            db_query("INSERT OR IGNORE INTO users (chat_id, user_id) VALUES (?,?)", (message.chat.id, target_id))
            db_query("UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            data = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, target_id), fetch=True)
            if data['warns'] >= 3:
                bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + 86400)
                db_query("UPDATE users SET warns = 0 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
                bot.reply_to(message, f"⛔ **{target_name}** (3/3 варна) — мут на 24ч!")
            else:
                bot.reply_to(message, f"⚠️ **{target_name}** получил варн! ({data['warns']}/3)")
        elif cmd == 'анварн':
            db_query("UPDATE users SET warns = MAX(0, warns - 1) WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            bot.reply_to(message, f"🗑 У **{target_name}** снят варн.")
    except Exception as e: bot.reply_to(message, f"❌ Ошибка: {e}")

# --- [ 3. СТАТИСТИКА И КНЕО ] ---
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['профиль', 'стата'])
def profile(message):
    res = db_query("SELECT warns, messages, rep FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, message.from_user.id), fetch=True)
    if res:
        bot.reply_to(message, f"👤 **{message.from_user.first_name}**\n⭐ Репутация: `{res['rep']}`\n✉️ Сообщений: `{res['messages']}`\n⚠️ Варны: `{res['warns']}/3`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def global_logic(message):
    un = message.from_user.username.lower() if message.from_user.username else "none"
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id, username) VALUES (?,?,?)", (message.chat.id, message.from_user.id, un))
    db_query("UPDATE users SET messages = messages + 1, username = ? WHERE chat_id=? AND user_id=?", (un, message.chat.id, message.from_user.id))
    if message.text and message.text.lower().startswith('кнео'):
        bot.reply_to(message, f"🔮 {random.choice(['Да', 'Нет', '100%', 'Нет иди на хуй', 'Я хз даже', 'Мб да', 'Мб нет', 'Возможно', 'Неее ты че'])}")

# --- [ WEBHOOK ] ---
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    bot.set_webhook(url=f"https://{request.host}/{TOKEN}")
    return "ONLINE", 200
