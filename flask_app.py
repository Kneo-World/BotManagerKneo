import os
import sqlite3
import random
import time
import re
import telebot
from telebot import types
from flask import Flask, request

# --- [ КОНФИГУРАЦИЯ ] ---
TOKEN = os.environ.get('BOT_TOKEN')
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

# Инициализация всех таблиц
db_query('CREATE TABLE IF NOT EXISTS users (chat_id int, user_id int, username text, name text, warns int DEFAULT 0, messages int DEFAULT 0, rep int DEFAULT 0, last_rep_time int DEFAULT 0, PRIMARY KEY (chat_id, user_id))')
db_query('CREATE TABLE IF NOT EXISTS messages_log (chat_id int, user_id int, timestamp int)')
db_query('CREATE TABLE IF NOT EXISTS chats_info (chat_id int PRIMARY KEY, title text, member_count int)')
db_query('CREATE TABLE IF NOT EXISTS chat_settings (chat_id int PRIMARY KEY, antispam int DEFAULT 0, warn_limit_action text DEFAULT "mute")')

# --- [ УТИЛИТЫ ] ---
def check_admin(message):
    if message.chat.type == 'private': return True
    try:
        status = bot.get_chat_member(message.chat.id, message.from_user.id).status
        return status in ['administrator', 'creator']
    except: return False

def safe_send(chat_id, text, reply_to=None, markup=None, parse_mode="Markdown"):
    try:
        return bot.send_message(chat_id, text, reply_to_message_id=reply_to, reply_markup=markup, parse_mode=parse_mode, disable_web_page_preview=True)
    except Exception as e:
        if "TOPIC_CLOSED" in str(e): print(f"⚠️ Тема закрыта в {chat_id}")
        return None

def parse_time(text):
    match = re.search(r'(\d+)([мчд])', text.lower())
    if not match: return 3600
    amount, unit = int(match.group(1)), match.group(2)
    return amount * (60 if unit == 'м' else 3600 if unit == 'ч' else 86400)

# --- [ МЕНЮ НАСТРОЕК (ДЛЯ АДМИНОВ ЧАТОВ) ] ---
@bot.message_handler(func=lambda m: m.text and m.text.lower() == 'настройки')
def chat_settings_menu(message):
    if message.chat.type == 'private' or not check_admin(message): return
    
    sid = message.chat.id
    settings = db_query("SELECT antispam, warn_limit_action FROM chat_settings WHERE chat_id=?", (sid,), fetch=True)
    if not settings:
        db_query("INSERT INTO chat_settings (chat_id) VALUES (?)", (sid,))
        settings = {'antispam': 0, 'warn_limit_action': 'mute'}

    markup = types.InlineKeyboardMarkup()
    spam_status = "✅ Вкл" if settings['antispam'] else "❌ Выкл"
    warn_mode = "🔇 Мут 24ч" if settings['warn_limit_action'] == 'mute' else "🔨 Бан"

    markup.add(types.InlineKeyboardButton(f"Анти-ссылки: {spam_status}", callback_data=f"set_spam_{sid}"))
    markup.add(types.InlineKeyboardButton(f"При 3/3 варнах: {warn_mode}", callback_data=f"set_warn_{sid}"))
    
    safe_send(sid, "⚙️ **Настройки чата Kneo**\nУправляйте функциями бота в этой группе:", markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_'))
def settings_callback(call):
    try:
        status = bot.get_chat_member(call.message.chat.id, call.from_user.id).status
        if status not in ['administrator', 'creator']:
            return bot.answer_callback_query(call.id, "❌ Только для админов!")
    except: return

    sid = int(call.data.split('_')[-1])
    if "set_spam" in call.data:
        db_query("UPDATE chat_settings SET antispam = 1 - antispam WHERE chat_id=?", (sid,))
    elif "set_warn" in call.data:
        curr = db_query("SELECT warn_limit_action FROM chat_settings WHERE chat_id=?", (sid,), fetch=True)
        new_mode = "ban" if curr['warn_limit_action'] == "mute" else "mute"
        db_query("UPDATE chat_settings SET warn_limit_action = ? WHERE chat_id=?", (new_mode, sid))

    settings = db_query("SELECT antispam, warn_limit_action FROM chat_settings WHERE chat_id=?", (sid,), fetch=True)
    markup = types.InlineKeyboardMarkup()
    spam_status = "✅ Вкл" if settings['antispam'] else "❌ Выкл"
    warn_mode = "🔇 Мут 24ч" if settings['warn_limit_action'] == 'mute' else "🔨 Бан"
    markup.add(types.InlineKeyboardButton(f"Анти-ссылки: {spam_status}", callback_data=f"set_spam_{sid}"))
    markup.add(types.InlineKeyboardButton(f"При 3/3 варнах: {warn_mode}", callback_data=f"set_warn_{sid}"))
    
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id, "Настройки обновлены!")

# --- [ МОДЕРАЦИЯ ] ---
def moder_commands(message):
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
            else: return safe_send(message.chat.id, "❌ Юзер не найден в базе.")

    if not target_id: return safe_send(message.chat.id, "💬 Ответьте на сообщение или тегните @username")

    try:
        if cmd == 'мут':
            sec = parse_time(text)
            bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + sec)
            safe_send(message.chat.id, f"🔇 **{target_name}** в муте на {sec//60} мин.")
        elif cmd == 'размут':
            bot.restrict_chat_member(message.chat.id, target_id, permissions=types.ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True, can_invite_users=True))
            safe_send(message.chat.id, f"🔊 **{target_name}** размучен.")
        elif cmd == 'бан':
            bot.ban_chat_member(message.chat.id, target_id)
            safe_send(message.chat.id, f"🔨 **{target_name}** забанен.")
        elif cmd == 'варн':
            db_query("UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            d = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, target_id), fetch=True)
            settings = db_query("SELECT warn_limit_action FROM chat_settings WHERE chat_id=?", (message.chat.id,), fetch=True)
            action = settings['warn_limit_action'] if settings else 'mute'
            
            if d['warns'] >= 3:
                db_query("UPDATE users SET warns = 0 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
                if action == 'mute':
                    bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + 86400)
                    safe_send(message.chat.id, f"⛔ **{target_name}** (3/3 варна) -> Мут 24ч.")
                else:
                    bot.ban_chat_member(message.chat.id, target_id)
                    safe_send(message.chat.id, f"🔨 **{target_name}** (3/3 варна) -> Бан.")
            else: safe_send(message.chat.id, f"⚠️ Варн **{target_name}** ({d['warns']}/3)")
        elif cmd == 'анварн':
            db_query("UPDATE users SET warns = CASE WHEN warns > 0 THEN warns - 1 ELSE 0 END WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            safe_send(message.chat.id, f"🗑 У **{target_name}** снят варн.")
    except Exception as e: safe_send(message.chat.id, "❌ Ошибка прав.")

# --- [ ТОПЫ И РЕПУТАЦИЯ ] ---
def plus_rep(message):
    uid, cid, now = message.from_user.id, message.chat.id, int(time.time())
    target = message.reply_to_message.from_user
    if target.id == uid or target.is_bot: return
    user_data = db_query("SELECT last_rep_time FROM users WHERE chat_id=? AND user_id=?", (cid, uid), fetch=True)
    if user_data and (now - user_data['last_rep_time'] < 30): return
    db_query("UPDATE users SET rep = rep + 1 WHERE chat_id=? AND user_id=?", (cid, target.id))
    db_query("UPDATE users SET last_rep_time = ? WHERE chat_id=? AND user_id=?", (now, cid, uid))
    safe_send(cid, f"💎 Репутация **{target.first_name}** повышена!", reply_to=message.message_id)

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
    if not res: return safe_send(cid, "📊 Пока пусто.")
    out = f"**{title}**\n━━━━━━━━━━━━━━\n"
    for i, r in enumerate(res, 1): out += f"{i}. {r[0]} — `{r[1]}` {unit}\n"
    safe_send(cid, out)

# --- [ ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ] ---
@bot.message_handler(commands=['start', 'help', 'chats'])
def base_commands(message):
    if message.chat.type == 'private':
        if message.text == '/start':
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("➕ Добавить в чат", url=f"https://t.me/{bot.get_me().username}?startgroup=true"),
                       types.InlineKeyboardButton("📖 Инструкция", url=MANUAL_URL))
            safe_send(message.chat.id, f"👋 Привет, {message.from_user.first_name}! Я Kneo.", markup=markup)
        elif message.text == '/help': safe_send(message.chat.id, f"❓ Мануал: {MANUAL_URL}")
        elif message.text == '/chats' and message.from_user.id == ADMIN_ID:
            res = db_query("SELECT title, chat_id, member_count FROM chats_info", fetch_all=True)
            if not res: return safe_send(message.chat.id, "📂 Список чатов пуст.")
            text = "📂 **Чаты Kneo:**\n"
            for i, r in enumerate(res, 1): text += f"{i}. {r['title']} (`{r['chat_id']}`) - {r['member_count']} чел.\n"
            safe_send(message.chat.id, text)

@bot.message_handler(content_types=['new_chat_members'])
def on_join(message):
    for user in message.new_chat_members:
        if user.id == bot.get_me().id: safe_send(message.chat.id, f"🚀 Kneo запущен! Инфо: /help")
        else: safe_send(message.chat.id, f"👋 Привет, {user.first_name}! Мануал: /help", reply_to=message.message_id)

@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'video', 'document'])
def global_handler(message):
    if message.chat.type == 'private': return
    uid, cid = message.from_user.id, message.chat.id
    m_text = message.text.lower() if message.text else ""

    # Анти-спам
    settings = db_query("SELECT antispam FROM chat_settings WHERE chat_id=?", (cid,), fetch=True)
    if settings and settings['antispam'] and not check_admin(message):
        if re.search(r'http[s]?://|t\.me/', m_text):
            try: return bot.delete_message(cid, message.message_id)
            except: pass

    # Статистика
    un, nm = (message.from_user.username or "none").lower(), message.from_user.first_name
    db_query("INSERT OR REPLACE INTO chats_info (chat_id, title, member_count) VALUES (?,?,?)", (cid, message.chat.title, bot.get_chat_member_count(cid)))
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id, username, name) VALUES (?,?,?,?)", (cid, uid, un, nm))
    db_query("UPDATE users SET messages = messages + 1, username = ?, name = ? WHERE chat_id=? AND user_id=?", (un, nm, cid, uid))
    db_query("INSERT INTO messages_log (chat_id, user_id, timestamp) VALUES (?,?,?)", (cid, uid, int(time.time())))

    # Логика ответов
    if message.reply_to_message and m_text in ['+', 'спасибо', 'сяп']: plus_rep(message)
    elif m_text == 'профиль' or m_text == 'стата':
        res = db_query("SELECT warns, messages, rep FROM users WHERE chat_id=? AND user_id=?", (cid, uid), fetch=True)
        if res: safe_send(cid, f"👤 **{nm}**\n⭐ Реп: `{res['rep']}`\n✉️ Сообщ: `{res['messages']}`\n⚠️ Варны: `{res['warns']}/3`", reply_to=message.message_id)
    elif m_text.startswith('кнео'): safe_send(cid, f"🔮 {random.choice(['Да', 'Нет', '100%'])}", reply_to=message.message_id)
    elif m_text.split()[0] in ['мут', 'бан', 'варн', 'разбан', 'размут', 'анварн'] and check_admin(message):
        moder_commands(message)

# --- [ WEBHOOK ] ---
@app.route('/' + (TOKEN if TOKEN else "default"), methods=['POST'])
def getMessage():
    if not TOKEN: return "No Token", 400
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    if not TOKEN: return "Error: BOT_TOKEN not found", 500
    bot.set_webhook(url=f"https://{request.host}/{TOKEN}")
    return "Kneo Bot Online", 200
