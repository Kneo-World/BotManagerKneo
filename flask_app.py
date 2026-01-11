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
ADMIN_ID = 8364667153 
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

# Инициализация таблиц
db_query('CREATE TABLE IF NOT EXISTS users (chat_id int, user_id int, username text, name text, warns int DEFAULT 0, messages int DEFAULT 0, rep int DEFAULT 0, last_rep_time int DEFAULT 0, PRIMARY KEY (chat_id, user_id))')
db_query('CREATE TABLE IF NOT EXISTS messages_log (chat_id int, user_id int, timestamp int)')
db_query('CREATE TABLE IF NOT EXISTS chats_info (chat_id int PRIMARY KEY, title text, member_count int)')

# --- [ ФУНКЦИЯ БЕЗОПАСНОЙ ОТПРАВКИ ] ---
def safe_send(chat_id, text, reply_to=None, markup=None, parse_mode="Markdown"):
    try:
        return bot.send_message(
            chat_id, text, 
            reply_to_message_id=reply_to if reply_to else None,
            reply_markup=markup,
            parse_mode=parse_mode
        )
    except telebot.apihelper.ApiTelegramException as e:
        if "TOPIC_CLOSED" in e.description:
            print(f"⚠️ Тема закрыта в чате {chat_id}, сообщение не отправлено.")
        else:
            print(f"🆘 Ошибка отправки: {e}")
        return None

# --- [ АДМИН-КОМАНДА: СПИСОК ЧАТОВ ] ---
@bot.message_handler(commands=['chats'])
def list_chats(message):
    if message.from_user.id == ADMIN_ID and message.chat.type == 'private':
        res = db_query("SELECT title, chat_id, member_count FROM chats_info", fetch_all=True)
        if not res: return safe_send(message.chat.id, "📭 Список чатов пуст.")
        text = "📂 **Список всех чатов Kneo:**\n━━━━━━━━━━━━━━\n"
        for i, row in enumerate(res, 1):
            text += f"{i}. **{row['title']}**\n   ID: `{row['chat_id']}`\n   Юзеров: {row['member_count']}\n\n"
        safe_send(message.chat.id, text)

# --- [ ПРИВЕТСТВИЯ ] ---
@bot.message_handler(commands=['start'])
def send_start(message):
    if message.chat.type == 'private':
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("➕ Добавить в чат", url=f"https://t.me/{bot.get_me().username}?startgroup=true"),
                   types.InlineKeyboardButton("📖 Инструкция", url=MANUAL_URL))
        safe_send(message.chat.id, f"👋 Привет, {message.from_user.first_name}! Я Kneo.", markup=markup)

@bot.message_handler(commands=['help'])
def send_help(message):
    safe_send(message.chat.id, f"❓ Мануал: {MANUAL_URL}", reply_to=message.message_id)

@bot.message_handler(content_types=['new_chat_members'])
def on_user_join(message):
    db_query("INSERT OR REPLACE INTO chats_info (chat_id, title, member_count) VALUES (?,?,?)", 
             (message.chat.id, message.chat.title, bot.get_chat_member_count(message.chat.id)))
    for user in message.new_chat_members:
        if user.id == bot.get_me().id:
            safe_send(message.chat.id, f"🚀 Kneo запущен! Мануал: {MANUAL_URL}")
        else:
            safe_send(message.chat.id, f"👋 Привет, {user.first_name}! Инфо: /help", reply_to=message.message_id)

# --- [ МОДЕРАЦИЯ ] ---
@bot.message_handler(func=lambda m: m.text and m.text.lower().split()[0] in ['мут', 'бан', 'варн', 'разбан', 'размут', 'анварн', 'кик'])
def moder_commands(message):
    # Команды модерации работают только если бот — админ и юзер — админ
    try:
        status = bot.get_chat_member(message.chat.id, message.from_user.id).status
        if status not in ['administrator', 'creator'] and message.chat.type != 'private': return
    except: return

    text = message.text.lower()
    cmd = text.split()[0]
    target_id, target_name = None, None

    if message.reply_to_message:
        target_id, target_name = message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name
    else:
        match = re.search(r'@(\w+)', message.text)
        if match:
            un = match.group(1).lower()
            res = db_query("SELECT user_id, name FROM users WHERE chat_id=? AND LOWER(username)=?", (message.chat.id, un), fetch=True)
            if res: target_id, target_name = res['user_id'], res['name']
            else: return safe_send(message.chat.id, "❌ Юзер не найден в базе.", reply_to=message.message_id)

    if not target_id: return safe_send(message.chat.id, "💬 Ответь на сообщение или тегни юзера.", reply_to=message.message_id)

    try:
        if cmd == 'мут':
            match_t = re.search(r'(\d+)([мчд])', text)
            sec = int(match_t.group(1)) * (60 if match_t.group(2)=='м' else 3600 if match_t.group(2)=='ч' else 86400) if match_t else 3600
            bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + sec)
            safe_send(message.chat.id, f"🔇 **{target_name}** в муте на {sec//60} мин.")
        elif cmd == 'размут':
            bot.restrict_chat_member(message.chat.id, target_id, permissions=types.ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True, can_invite_users=True))
            safe_send(message.chat.id, f"🔊 **{target_name}** размучен!")
        elif cmd == 'бан':
            bot.ban_chat_member(message.chat.id, target_id)
            safe_send(message.chat.id, f"🔨 **{target_name}** забанен.")
        elif cmd == 'варн':
            db_query("UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            d = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, target_id), fetch=True)
            if d['warns'] >= 3:
                bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + 86400)
                db_query("UPDATE users SET warns = 0 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
                safe_send(message.chat.id, f"⛔ **{target_name}** (3/3 варна) -> мут 24ч.")
            else: safe_send(message.chat.id, f"⚠️ Варн **{target_name}** ({d['warns']}/3)")
    except Exception as e: print(f"Error in moderation: {e}")

# --- [ ТОПЫ ] ---
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['топ', 'денотоп', 'неделотоп', 'месятоп', 'репотоп'])
def show_tops(message):
    cmd = message.text.lower()
    cid, now = message.chat.id, int(time.time())
    res, title, unit = [], "", "сообщ."
    if cmd == 'репотоп':
        res = db_query("SELECT name, rep FROM users WHERE chat_id=? AND rep > 0 ORDER BY rep DESC LIMIT 10", (cid,), fetch_all=True)
        title, unit = "💎 РЕПОТОП", "⭐"
    elif cmd in ['денотоп', 'неделотоп', 'месятоп']:
        days = 1 if cmd == 'денотоп' else 7 if cmd == 'неделотоп' else 30
        res = db_query("SELECT u.name, COUNT(l.timestamp) as c FROM messages_log l JOIN users u ON l.user_id = u.user_id AND l.chat_id = u.chat_id WHERE l.chat_id=? AND l.timestamp>? GROUP BY l.user_id ORDER BY c DESC LIMIT 10", (cid, now - days*86400), fetch_all=True)
        title = f"📅 ТОП ЗА {days} Дн."
    else:
        res = db_query("SELECT name, messages FROM users WHERE chat_id=? ORDER BY messages DESC LIMIT 10", (cid,), fetch_all=True)
        title = "🏆 ОБЩИЙ ТОП"

    if not res: return safe_send(cid, "📊 Пусто.")
    out = f"**{title}**\n━━━━━━━━━━━━━━\n"
    for i, r in enumerate(res, 1): out += f"{i}. {r[0]} — `{r[1]}` {unit}\n"
    safe_send(cid, out)

# --- [ РЕПУТАЦИЯ И ГЛОБАЛ ] ---
@bot.message_handler(func=lambda m: m.reply_to_message and m.text and m.text.lower() in ['+', 'спасибо', 'сяп'])
def plus_rep(message):
    uid, cid, now = message.from_user.id, message.chat.id, int(time.time())
    target = message.reply_to_message.from_user
    if target.id == uid or target.is_bot: return
    user_data = db_query("SELECT last_rep_time FROM users WHERE chat_id=? AND user_id=?", (cid, uid), fetch=True)
    if user_data and (now - user_data['last_rep_time'] < 30): return
    db_query("UPDATE users SET rep = rep + 1 WHERE chat_id=? AND user_id=?", (cid, target.id))
    db_query("UPDATE users SET last_rep_time = ? WHERE chat_id=? AND user_id=?", (now, cid, uid))
    safe_send(cid, f"💎 Репутация **{target.first_name}** повышена!", reply_to=message.message_id)

@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['профиль', 'стата'])
def show_profile(message):
    res = db_query("SELECT warns, messages, rep FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, message.from_user.id), fetch=True)
    if res: safe_send(message.chat.id, f"👤 **{message.from_user.first_name}**\n⭐ Реп: `{res['rep']}`\n✉️ Сообщ: `{res['messages']}`\n⚠️ Варны: `{res['warns']}/3`", reply_to=message.message_id)

@bot.message_handler(func=lambda m: True)
def global_handler(message):
    if message.chat.type == 'private': return
    un, nm = (message.from_user.username or "none").lower(), message.from_user.first_name
    uid, cid = message.from_user.id, message.chat.id
    db_query("INSERT OR REPLACE INTO chats_info (chat_id, title, member_count) VALUES (?,?,?)", (cid, message.chat.title, bot.get_chat_member_count(cid)))
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id, username, name) VALUES (?,?,?,?)", (cid, uid, un, nm))
    db_query("UPDATE users SET messages = messages + 1, username = ?, name = ? WHERE chat_id=? AND user_id=?", (un, nm, cid, uid))
    db_query("INSERT INTO messages_log (chat_id, user_id, timestamp) VALUES (?,?,?)", (cid, uid, int(time.time())))
    if message.text and message.text.lower().startswith('кнео'):
        safe_send(cid, f"🔮 {random.choice(['Да', 'Нет', '100%'])}", reply_to=message.message_id)

# --- [ WEBHOOK ] ---
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    bot.set_webhook(url=f"https://{request.host}/{TOKEN}")
    return "ONLINE", 200
