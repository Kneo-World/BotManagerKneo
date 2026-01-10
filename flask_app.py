import os
import sqlite3
import random
import time
import re
import telebot
from telebot import types
from flask import Flask, request

# --- [ КОНФИГУРАЦИЯ ] ---
TOKEN = '8202182875:AAEecFwxWQFBjny1-5VrGa9jDKsJaYOKxnA'
DB_PATH = 'kneo_base.db'
MANUAL_URL = 'https://kneo-world.github.io/MANYAL-BOT-MANAGER/'

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

db_query('''CREATE TABLE IF NOT EXISTS users 
    (chat_id int, user_id int, username text, name text, warns int DEFAULT 0, messages int DEFAULT 0, rep int DEFAULT 0, 
    PRIMARY KEY (chat_id, user_id))''')

db_query('''CREATE TABLE IF NOT EXISTS messages_log 
    (chat_id int, user_id int, timestamp int)''')

def check_admin(message):
    if message.chat.type == 'private': return True
    try:
        status = bot.get_chat_member(message.chat.id, message.from_user.id).status
        return status in ['administrator', 'creator']
    except: return False

# --- [ СИСТЕМА МОДЕРАЦИИ ] ---

@bot.message_handler(func=lambda m: m.text and m.text.lower().split()[0] in ['мут', 'бан', 'варн', 'разбан', 'размут', 'анварн', 'кик'])
def moder_commands(message):
    if not check_admin(message): return
    
    cmd = message.text.lower().split()[0]
    target_id, target_name = None, None

    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.first_name
    else:
        match = re.search(r'@(\w+)', message.text)
        if match:
            username = match.group(1).lower()
            res = db_query("SELECT user_id, name FROM users WHERE chat_id=? AND LOWER(username)=?", (message.chat.id, username), fetch=True)
            if res:
                target_id, target_name = res['user_id'], res['name']
            else:
                return bot.reply_to(message, f"❌ Юзер @{username} не найден в базе.")

    if not target_id:
        return bot.reply_to(message, "💬 Ответь на сообщение или укажи @username")

    try:
        if cmd == 'размут':
            # Исправленный размут: выдаем все права доступа
            permissions = types.ChatPermissions(
                can_send_messages=True, 
                can_send_media_messages=True, 
                can_send_polls=True, 
                can_send_other_messages=True, 
                can_add_web_page_previews=True, 
                can_invite_users=True
            )
            bot.restrict_chat_member(message.chat.id, target_id, permissions=permissions)
            bot.reply_to(message, f"🔊 **{target_name}** размучен! Теперь он снова может писать.")

        elif cmd == 'бан':
            bot.ban_chat_member(message.chat.id, target_id)
            bot.reply_to(message, f"🔨 **{target_name}** забанен.")

        elif cmd == 'разбан':
            bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
            bot.reply_to(message, f"✅ **{target_name}** разбанен.")

        elif cmd == 'варн':
            db_query("UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            data = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, target_id), fetch=True)
            if data and data['warns'] >= 3:
                bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + 86400)
                db_query("UPDATE users SET warns = 0 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
                bot.reply_to(message, f"⛔ **{target_name}** (3/3 варна) — мут на 24 часа.")
            else:
                bot.reply_to(message, f"⚠️ **{target_name}**, вы получили варн! ({data['warns'] if data else 1}/3)")

        elif cmd == 'анварн':
            db_query("UPDATE users SET warns = CASE WHEN warns > 0 THEN warns - 1 ELSE 0 END WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            bot.reply_to(message, f"🗑 У **{target_name}** снят один варн.")

        elif cmd == 'мут':
            # Мут на 1 час
            bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + 3600)
            bot.reply_to(message, f"🔇 **{target_name}** в муте на 1 час.")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка прав: `{e}`")

# --- [ ТОПЫ И СТАТИСТИКА ] ---

@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['топ', 'денотоп', 'неделотоп', 'месятоп', 'репотоп'])
def show_tops(message):
    cmd = message.text.lower()
    cid = message.chat.id
    res, title, unit = [], "", "сообщ."
    
    now = int(time.time())
    if cmd == 'репотоп':
        res = db_query("SELECT name, rep FROM users WHERE chat_id=? AND rep > 0 ORDER BY rep DESC LIMIT 10", (cid,), fetch_all=True)
        title, unit = "💎 РЕПОТОП", "⭐"
    elif cmd == 'денотоп':
        res = db_query("SELECT u.name, COUNT(l.timestamp) as c FROM messages_log l JOIN users u ON l.user_id=u.user_id AND l.chat_id=u.chat_id WHERE l.chat_id=? AND l.timestamp>? GROUP BY l.user_id ORDER BY c DESC LIMIT 10", (cid, now - 86400), fetch_all=True)
        title = "📅 ДЕНОТОП"
    elif cmd == 'неделотоп':
        res = db_query("SELECT u.name, COUNT(l.timestamp) as c FROM messages_log l JOIN users u ON l.user_id=u.user_id AND l.chat_id=u.chat_id WHERE l.chat_id=? AND l.timestamp>? GROUP BY l.user_id ORDER BY c DESC LIMIT 10", (cid, now - 604800), fetch_all=True)
        title = "⏳ НЕДЕЛОТОП"
    elif cmd == 'месятоп':
        res = db_query("SELECT u.name, COUNT(l.timestamp) as c FROM messages_log l JOIN users u ON l.user_id=u.user_id AND l.chat_id=u.chat_id WHERE l.chat_id=? AND l.timestamp>? GROUP BY l.user_id ORDER BY c DESC LIMIT 10", (cid, now - 2592000), fetch_all=True)
        title = "📈 МЕСЯТОП"
    elif cmd == 'топ':
        res = db_query("SELECT name, messages FROM users WHERE chat_id=? ORDER BY messages DESC LIMIT 10", (cid,), fetch_all=True)
        title = "🏆 ОБЩИЙ ТОП"

    if not res: return bot.reply_to(message, "📊 Статистика пока пуста.")
    text = f"**{title}**\n━━━━━━━━━━━━━━\n"
    for i, r in enumerate(res, 1):
        # r[1] - это количество (сообщения или репутация)
        text += f"{i}. {r[0]} — `{r[1]}` {unit}\n"
    bot.reply_to(message, text, parse_mode="Markdown")

# --- [ ПРИВЕТСТВИЕ И ХЕЛП ] ---

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.chat.type == 'private':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Добавить в чат", url=f"https://t.me/{bot.get_me().username}?startgroup=true"))
        markup.add(types.InlineKeyboardButton("📖 Мануал", url=MANUAL_URL))
        bot.send_message(message.chat.id, "👋 Привет! Я Kneo. Помогу управлять твоим чатом!", reply_markup=markup)

@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.reply_to(message, f"❓ Все команды в мануале:\n{MANUAL_URL}", disable_web_page_preview=True)

@bot.message_handler(content_types=['new_chat_members'])
def on_join(message):
    for user in message.new_chat_members:
        if user.id == bot.get_me().id:
            bot.send_message(message.chat.id, f"🚀 Бот активирован! Мануал: {MANUAL_URL}")
        else:
            bot.send_message(message.chat.id, f"👋 Привет, {user.first_name}! Пиши /help для списка команд.")

# --- [ ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ] ---

@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['профиль', 'стата'])
def show_profile(message):
    res = db_query("SELECT warns, messages, rep FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, message.from_user.id), fetch=True)
    if res: bot.reply_to(message, f"👤 **{message.from_user.first_name}**\n⭐ Репутация: `{res['rep']}`\n✉️ Сообщений: `{res['messages']}`\n⚠️ Варны: `{res['warns']}/3`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.reply_to_message and m.text and m.text.lower() in ['+', 'спасибо', 'сяп'])
def plus_rep(message):
    target = message.reply_to_message.from_user
    if target.id == message.from_user.id or target.is_bot: return
    db_query("UPDATE users SET rep = rep + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target.id))
    bot.reply_to(message, f"💎 Репутация **{target.first_name}** повышена!")

@bot.message_handler(func=lambda m: True)
def global_handler(message):
    if message.chat.type == 'private': return
    un = (message.from_user.username or "none").lower()
    nm = message.from_user.first_name
    uid, cid = message.from_user.id, message.chat.id
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id, username, name) VALUES (?,?,?,?)", (cid, uid, un, nm))
    db_query("UPDATE users SET messages = messages + 1, username = ?, name = ? WHERE chat_id=? AND user_id=?", (un, nm, cid, uid))
    db_query("INSERT INTO messages_log (chat_id, user_id, timestamp) VALUES (?,?,?)", (cid, uid, int(time.time())))
    if message.text and message.text.lower().startswith('кнео'):
        bot.reply_to(message, f"🔮 {random.choice(['Да', 'Нет', '100%'])}")

# --- [ WEBHOOK ] ---
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    bot.set_webhook(url=f"https://{request.host}/{TOKEN}")
    return "ONLINE", 200
