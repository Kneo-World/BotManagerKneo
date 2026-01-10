import os
import sqlite3
import random
import time
import re
import telebot
from flask import Flask, request
from datetime import datetime, timedelta

# --- [ КОНФИГУРАЦИЯ ] ---
TOKEN = '8202182875:AAEecFwxWQFBjny1-5VrGa9jDKsJaYOKxnA'
DB_PATH = 'kneo_base.db'

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

# --- [ РАБОТА С БД ] ---
def db_query(sql, params=(), fetch=False, fetch_all=False):
    try:
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params)
            if fetch: return cursor.fetchone()
            if fetch_all: return cursor.fetchall()
            conn.commit()
    except Exception as e: print(f"🆘 БД Ошибка: {e}")
    return None

# Инициализация таблиц
db_query('''CREATE TABLE IF NOT EXISTS users 
    (chat_id int, user_id int, username text, name text, warns int DEFAULT 0, messages int DEFAULT 0, rep int DEFAULT 0, 
    PRIMARY KEY (chat_id, user_id))''')

db_query('''CREATE TABLE IF NOT EXISTS messages_log 
    (chat_id int, user_id int, timestamp int)''')

def check_admin(message):
    if message.chat.type == 'private': return True
    try: return bot.get_chat_member(message.chat.id, message.from_user.id).status in ['administrator', 'creator']
    except: return False

# --- [ ЛОГИКА ТОПОВ ] ---
def get_top_messages(chat_id, period_days=None):
    if period_days:
        # Топ за период (день, неделя, месяц)
        since_time = int(time.time()) - (period_days * 86400)
        sql = '''SELECT u.name, COUNT(l.timestamp) as cnt 
                 FROM messages_log l 
                 JOIN users u ON l.user_id = u.user_id AND l.chat_id = u.chat_id
                 WHERE l.chat_id = ? AND l.timestamp > ?
                 GROUP BY l.user_id ORDER BY cnt DESC LIMIT 10'''
        return db_query(sql, (chat_id, since_time), fetch_all=True)
    else:
        # Топ за все время
        return db_query("SELECT name, messages as cnt FROM users WHERE chat_id=? ORDER BY messages DESC LIMIT 10", (chat_id,), fetch_all=True)

# --- [ КОМАНДЫ ТОПОВ ] ---
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['топ', 'денотоп', 'неделотоп', 'месятоп', 'репотоп'])
def show_tops(message):
    chat_id = message.chat.id
    cmd = message.text.lower()
    
    if cmd == 'репотоп':
        rows = db_query("SELECT name, rep FROM users WHERE chat_id=? AND rep > 0 ORDER BY rep DESC LIMIT 10", (chat_id,), fetch_all=True)
        title = "💎 РЕПОТОП (Рейтинг уважения)"
        unit = "⭐"
    elif cmd == 'денотоп':
        rows = get_top_messages(chat_id, 1)
        title = "📅 ДЕНОТОП (За 24 часа)"
        unit = "сообщ."
    elif cmd == 'неделотоп':
        rows = get_top_messages(chat_id, 7)
        title = "⏳ НЕДЕЛОТОП (За 7 дней)"
        unit = "сообщ."
    elif cmd == 'месятоп':
        rows = get_top_messages(chat_id, 30)
        title = "📈 МЕСЯТОП (За 30 дней)"
        unit = "сообщ."
    else: # просто топ
        rows = get_top_messages(chat_id)
        title = "🏆 ТОП (За все время)"
        unit = "сообщ."

    if not rows:
        return bot.reply_to(message, "Тут пока пусто. Начинайте общаться! 💬")

    text = f"**{title}**\n━━━━━━━━━━━━━━\n"
    for i, row in enumerate(rows, 1):
        count = row[1] if len(row) > 1 else 0
        text += f"{i}. {row[0]} — `{count}` {unit}\n"
    bot.reply_to(message, text, parse_mode="Markdown")

# --- [ РЕПУТАЦИЯ ] ---
@bot.message_handler(func=lambda m: m.reply_to_message and m.text and m.text.lower() in ['+', 'спасибо', 'сяп', 'респект'])
def rep_logic(message):
    target = message.reply_to_message.from_user
    if target.id == message.from_user.id: return bot.reply_to(message, "Самолайк — это не круто 🙃")
    if target.is_bot: return 
    
    db_query("UPDATE users SET rep = rep + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target.id))
    bot.reply_to(message, f"💎 Репутация **{target.first_name}** повышена!", parse_mode="Markdown")

# --- [ МОДЕРАЦИЯ ] ---
@bot.message_handler(func=lambda m: m.text and m.text.lower().split()[0] in ['мут', 'бан', 'кик', 'варн', 'размут', 'разбан', 'анварн'])
def moder_commands(message):
    if not check_admin(message): return
    cmd = message.text.lower().split()[0]
    
    # Поиск цели (реплай или @user)
    target_id = None
    target_name = None
    if message.reply_to_message:
        target_id, target_name = message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name
    else:
        match = re.search(r'@(\w+)', message.text)
        if match:
            res = db_query("SELECT user_id, name FROM users WHERE chat_id=? AND LOWER(username)=?", (message.chat.id, match.group(1).lower()), fetch=True)
            if res: target_id, target_name = res['user_id'], res['name']
    
    if not target_id: return bot.reply_to(message, "💬 Ответьте на сообщение или укажите @username")

    try:
        if cmd == 'бан':
            bot.ban_chat_member(message.chat.id, target_id)
            bot.reply_to(message, f"🔨 **{target_name}** забанен!")
        elif cmd == 'разбан':
            bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
            bot.reply_to(message, f"✅ **{target_name}** разбанен!")
        elif cmd == 'мут':
            bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + 3600)
            bot.reply_to(message, f"🔇 **{target_name}** в муте на 1 час.")
        elif cmd == 'размут':
            bot.restrict_chat_member(message.chat.id, target_id, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)
            bot.reply_to(message, f"🔊 Мут с **{target_name}** снят.")
        elif cmd == 'варн':
            db_query("UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            data = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, target_id), fetch=True)
            if data['warns'] >= 3:
                bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + 86400)
                db_query("UPDATE users SET warns = 0 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
                bot.reply_to(message, f"⛔ **{target_name}** (3/3 варна) — мут на 24ч!")
            else: bot.reply_to(message, f"⚠️ **{target_name}** получил варн! ({data['warns']}/3)")
    except Exception as e: bot.reply_to(message, f"❌ Ошибка: {e}")

# --- [ СТАТА И ОСНОВНАЯ ЛОГИКА ] ---
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['профиль', 'стата'])
def profile(message):
    res = db_query("SELECT warns, messages, rep FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, message.from_user.id), fetch=True)
    if res: bot.reply_to(message, f"👤 **{message.from_user.first_name}**\n⭐ Репутация: `{res['rep']}`\n✉️ Сообщений: `{res['messages']}`\n⚠️ Варны: `{res['warns']}/3`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def global_logic(message):
    un = (message.from_user.username or "none").lower()
    nm = message.from_user.first_name
    uid, cid = message.from_user.id, message.chat.id
    now = int(time.time())

    # Обновляем профиль
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id, username, name) VALUES (?,?,?,?)", (cid, uid, un, nm))
    db_query("UPDATE users SET messages = messages + 1, username = ?, name = ? WHERE chat_id=? AND user_id=?", (un, nm, cid, uid))
    
    # Логируем сообщение для временных топов
    db_query("INSERT INTO messages_log (chat_id, user_id, timestamp) VALUES (?,?,?)", (cid, uid, now))
    
    # Очистка старых логов (раз в 100 сообщений, чтобы не тормозить)
    if random.randint(1, 100) == 1:
        month_ago = now - 2592000
        db_query("DELETE FROM messages_log WHERE timestamp < ?", (month_ago,))

    if message.text and message.text.lower().startswith('кнео'):
        bot.reply_to(message, f"🔮 {random.choice(['Да', 'Нет', '100%', 'Маловероятно', 'Неее ты че', 'Дааа ты че', 'Кнш'])}")

# --- [ WEBHOOK ] ---
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    bot.set_webhook(url=f"https://{request.host}/{TOKEN}")
    return "<h1>KNEO MULTI-TOP SYSTEM ONLINE</h1>", 200
