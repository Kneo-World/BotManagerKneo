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
    try: return bot.get_chat_member(message.chat.id, message.from_user.id).status in ['administrator', 'creator']
    except: return False

# --- [ КНОПКИ И ПРИВЕТСТВИЕ В ЛС ] ---
@bot.message_handler(commands=['start'])
def send_welcome_lp(message):
    if message.chat.type == 'private':
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_add = types.InlineKeyboardButton("➕ Добавить в чат", url=f"https://t.me/{bot.get_me().username}?startgroup=true")
        btn_manual = types.InlineKeyboardButton("📖 Инструкция (Мануал)", url=MANUAL_URL)
        markup.add(btn_add, btn_manual)
        
        bot.send_message(message.chat.id, 
            f"👋 Привет, **{message.from_user.first_name}**!\n\n"
            "Я — **Kneo**, продвинутый менеджер для управления твоим чатом.\n"
            "Я умею следить за порядком, вести статистику и строить топы активности.\n\n"
            "Жми кнопки ниже, чтобы начать! 👇", 
            parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = (
        "❓ **Список команд:**\n\n"
        "🔹 `топ` / `денотоп` / `неделотоп` — статистика сообщений\n"
        "🔹 `репотоп` — рейтинг уважения\n"
        "🔹 `профиль` — твоя статистика\n"
        "🔹 `+` (в ответе) — поднять репутацию\n\n"
        "🛠 **Для админов:** мут, бан, варн, разбан.\n\n"
        f"📍 Подробный мануал: [КЛИК ТУТ]({MANUAL_URL})"
    )
    bot.reply_to(message, help_text, parse_mode="Markdown", disable_web_page_preview=True)

# --- [ ПРИВЕТСТВИЕ В ЧАТЕ (НОВЫЕ И БОТ) ] ---
@bot.message_handler(content_types=['new_chat_members'])
def greeting(message):
    for user in message.new_chat_members:
        if user.id == bot.get_me().id:
            # Если в чат зашел сам бот
            bot.send_message(message.chat.id, 
                "🚀 **Kneo подключен к системе!**\n\n"
                "Всем привет! Я буду следить за порядком и статистикой в этом чате.\n"
                f"Обязательно прочитайте мой мануал: [САЙТ]({MANUAL_URL})\n"
                "Если забудете команды, просто напишите `/help`.", 
                parse_mode="Markdown")
        else:
            # Если зашел обычный пользователь
            bot.send_message(message.chat.id, 
                f"👋 Добро пожаловать, {user.first_name}!\n"
                "Приятного общения. Не нарушай правила и пиши `/help`, чтобы узнать мои возможности!", 
                parse_mode="Markdown")

# --- [ ЛОГИКА ТОПОВ ] ---
def get_top_messages(chat_id, period_days=None):
    if period_days:
        since_time = int(time.time()) - (period_days * 86400)
        sql = '''SELECT u.name, COUNT(l.timestamp) as cnt FROM messages_log l 
                 JOIN users u ON l.user_id = u.user_id AND l.chat_id = u.chat_id
                 WHERE l.chat_id = ? AND l.timestamp > ? GROUP BY l.user_id ORDER BY cnt DESC LIMIT 10'''
        return db_query(sql, (chat_id, since_time), fetch_all=True)
    return db_query("SELECT name, messages as cnt FROM users WHERE chat_id=? ORDER BY messages DESC LIMIT 10", (chat_id,), fetch_all=True)

@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['топ', 'денотоп', 'неделотоп', 'месятоп', 'репотоп'])
def show_tops(message):
    cmd = message.text.lower()
    res = []
    title, unit = "", "сообщ."
    if cmd == 'репотоп':
        res, title, unit = db_query("SELECT name, rep FROM users WHERE chat_id=? AND rep > 0 ORDER BY rep DESC LIMIT 10", (message.chat.id,), fetch_all=True), "💎 РЕПОТОП", "⭐"
    elif cmd == 'денотоп': res, title = get_top_messages(message.chat.id, 1), "📅 ДЕНОТОП"
    elif cmd == 'неделотоп': res, title = get_top_messages(message.chat.id, 7), "⏳ НЕДЕЛОТОП"
    elif cmd == 'месятоп': res, title = get_top_messages(message.chat.id, 30), "📈 МЕСЯТОП"
    else: res, title = get_top_messages(message.chat.id), "🏆 ОБЩИЙ ТОП"

    if not res: return bot.reply_to(message, "Пока пусто!")
    text = f"**{title}**\n━━━━━━━━━━━━━━\n"
    for i, r in enumerate(res, 1): text += f"{i}. {r[0]} — `{r[1]}` {unit}\n"
    bot.reply_to(message, text, parse_mode="Markdown")

# --- [ РЕПУТАЦИЯ И МОДЕРАЦИЯ ] ---
@bot.message_handler(func=lambda m: m.reply_to_message and m.text and m.text.lower() in ['+', 'спасибо', 'сяп', 'респект'])
def rep_logic(message):
    target = message.reply_to_message.from_user
    if target.id == message.from_user.id or target.is_bot: return
    db_query("UPDATE users SET rep = rep + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target.id))
    bot.reply_to(message, f"💎 Репутация **{target.first_name}** повышена!")

@bot.message_handler(func=lambda m: m.text and m.text.lower().split()[0] in ['мут', 'бан', 'варн', 'разбан', 'размут', 'анварн'])
def moder_commands(message):
    if not check_admin(message): return
    cmd = message.text.lower().split()[0]
    target_id, target_name = None, None
    if message.reply_to_message:
        target_id, target_name = message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name
    else:
        match = re.search(r'@(\w+)', message.text)
        if match:
            res = db_query("SELECT user_id, name FROM users WHERE chat_id=? AND LOWER(username)=?", (message.chat.id, match.group(1).lower()), fetch=True)
            if res: target_id, target_name = res['user_id'], res['name']
    
    if not target_id: return
    try:
        if cmd == 'бан': bot.ban_chat_member(message.chat.id, target_id); bot.reply_to(message, f"🔨 **{target_name}** забанен!")
        elif cmd == 'разбан': bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True); bot.reply_to(message, f"✅ **{target_name}** разбанен!")
        elif cmd == 'мут':
            bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + 3600)
            bot.reply_to(message, f"🔇 **{target_name}** в муте на час.")
        elif cmd == 'варн':
            db_query("UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            d = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, target_id), fetch=True)
            if d['warns'] >= 3:
                bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + 86400)
                db_query("UPDATE users SET warns = 0 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
                bot.reply_to(message, f"⛔ **{target_name}** (3/3) — мут 24ч!")
            else: bot.reply_to(message, f"⚠️ Варн **{target_name}** ({d['warns']}/3)")
    except Exception as e: bot.reply_to(message, f"❌ Ошибка: {e}")

# --- [ СТАТА И ГЛОБАЛ ] ---
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['профиль', 'стата'])
def profile(message):
    res = db_query("SELECT warns, messages, rep FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, message.from_user.id), fetch=True)
    if res: bot.reply_to(message, f"👤 **{message.from_user.first_name}**\n⭐ Репутация: `{res['rep']}`\n✉️ Сообщений: `{res['messages']}`\n⚠️ Варны: `{res['warns']}/3`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def global_logic(message):
    un, nm = (message.from_user.username or "none").lower(), message.from_user.first_name
    uid, cid, now = message.from_user.id, message.chat.id, int(time.time())
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id, username, name) VALUES (?,?,?,?)", (cid, uid, un, nm))
    db_query("UPDATE users SET messages = messages + 1, username = ?, name = ? WHERE chat_id=? AND user_id=?", (un, nm, cid, uid))
    db_query("INSERT INTO messages_log (chat_id, user_id, timestamp) VALUES (?,?,?)", (cid, uid, now))
    if message.text and message.text.lower().startswith('кнео'):
        bot.reply_to(message, f"🔮 {random.choice(['Да', 'Нет', '100%', 'Может быть', 'Конечно да!', 'Конечно нет!'])}")

# --- [ WEBHOOK ] ---
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    bot.set_webhook(url=f"https://{request.host}/{TOKEN}")
    return "<h1>KNEO ONLINE</h1>", 200
