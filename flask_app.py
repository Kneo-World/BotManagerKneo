import os
import sqlite3
import random
import time
import re
import telebot
from telebot import types
from flask import Flask, request

# --- [ КОНФИГУРАЦИЯ И ПЕРЕМЕННЫЕ ] ---
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = 8364667153 
DB_PATH = 'kneo_base.db'
COMMANDS_URL = 'https://kneo-world.github.io/MANYAL-BOT-MANAGER/'

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

# --- [ СИСТЕМА ЛОКАЛИЗАЦИИ ] ---
# Мы вынесли всё в один словарь, чтобы бот был "красивым" внутри кода
STRINGS = {
    'ru': {
        'start': "👋 Привет, {}! Я **Kneo**. Помогу тебе навести порядок в чате.",
        'help': "❓ Список команд бота доступен по ссылке:\n{}",
        'add_chat': "➕ Добавить в чат",
        'cmd_list': "📖 Команды бота",
        'settings_title': "⚙️ **Настройки чата Kneo**\n\nВыберите нужный пункт для изменения конфигурации:",
        'spam': "Анти-ссылки",
        'warn_act': "Действие при 3/3 варнах",
        'lang': "Язык / Language",
        'mute_24': "🔇 Мут 24ч",
        'ban': "🔨 Бан",
        'admin_only': "❌ Эта команда доступна только администраторам!",
        'reply_req': "💬 Команда должна быть ответом на сообщение или содержать @username.",
        'mute_msg': "🔇 Пользователь **{}** ограничен в общении на {} мин.",
        'unmute_msg': "🔊 С пользователя **{}** сняты все ограничения.",
        'ban_msg': "🔨 Пользователь **{}** был изгнан из чата.",
        'warn_msg': "⚠️ Выдано предупреждение **{}** ({}/3).",
        'warn_limit': "⛔ Лимит варнов (3/3) для **{}** достигнут. Применено: {}",
        'unwarn_msg': "🗑 С пользователя **{}** снято одно предупреждение.",
        'rep_up': "💎 Репутация пользователя **{}** повышена!",
        'empty_top': "📊 В этом чате пока нет данных для топа.",
        'profile': "👤 **Профиль: {}**\n━━━━━━━━━━━━━━\n⭐ Репутация: `{}`\n✉️ Сообщений: `{}`\n⚠️ Варны: `{}/3`",
        'activated': "🚀 Kneo успешно запущен! Ознакомьтесь с управлением: {}",
        'kneo_ans': ['Да', 'Нет', 'Весьма вероятно', '100%', 'Не думаю', 'Спроси позже']
    },
    'en': {
        'start': "👋 Hello, {}! I'm **Kneo**. I'll help you keep your chat organized.",
        'help': "❓ Bot command list is available here:\n{}",
        'add_chat': "➕ Add to group",
        'cmd_list': "📖 Bot commands",
        'settings_title': "⚙️ **Kneo Chat Settings**\n\nSelect a feature to configure:",
        'spam': "Anti-links",
        'warn_act': "Action on 3/3 warns",
        'lang': "Language / Язык",
        'mute_24': "🔇 Mute 24h",
        'ban': "🔨 Ban",
        'admin_only': "❌ This command is for admins only!",
        'reply_req': "💬 You must reply to a message or tag @username.",
        'mute_msg': "🔇 User **{}** has been muted for {} min.",
        'unmute_msg': "🔊 User **{}** has been unmuted.",
        'ban_msg': "🔨 User **{}** has been banned from the chat.",
        'warn_msg': "⚠️ Warning issued to **{}** ({}/3).",
        'warn_limit': "⛔ Warn limit (3/3) for **{}** reached. Applied: {}",
        'unwarn_msg': "🗑 One warning removed from **{}**.",
        'rep_up': "💎 **{}**'s reputation has increased!",
        'empty_top': "📊 No data for the leaderboard yet.",
        'profile': "👤 **Profile: {}**\n━━━━━━━━━━━━━━\n⭐ Rep: `{}`\n✉️ Messages: `{}`\n⚠️ Warns: `{}/3`",
        'activated': "🚀 Kneo activated! Check bot commands here: {}",
        'kneo_ans': ['Yes', 'No', 'Most likely', '100%', 'I don't think so', 'Ask later']
    }
}

# --- [ ЯДРО БАЗЫ ДАННЫХ ] ---
def db_query(sql, params=(), fetch=False, fetch_all=False):
    try:
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params)
            if fetch: return cursor.fetchone()
            if fetch_all: return cursor.fetchall()
            conn.commit()
    except Exception as e: 
        print(f"🆘 DATABASE ERROR: {e}")
    return None

# Инициализация структуры
def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users (
        chat_id int, user_id int, username text, name text, 
        warns int DEFAULT 0, messages int DEFAULT 0, rep int DEFAULT 0, 
        last_rep_time int DEFAULT 0, PRIMARY KEY (chat_id, user_id))''')
    db_query('CREATE TABLE IF NOT EXISTS messages_log (chat_id int, user_id int, timestamp int)')
    db_query('CREATE TABLE IF NOT EXISTS chats_info (chat_id int PRIMARY KEY, title text, member_count int)')
    db_query('CREATE TABLE IF NOT EXISTS chat_settings (chat_id int PRIMARY KEY, antispam int DEFAULT 0, warn_limit_action text DEFAULT "mute", lang text DEFAULT "ru")')

init_db()

# --- [ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ] ---
def get_lang(chat_id):
    res = db_query("SELECT lang FROM chat_settings WHERE chat_id=?", (chat_id,), fetch=True)
    return res['lang'] if res else 'ru'

def is_admin(message):
    if message.chat.type == 'private': return True
    try:
        status = bot.get_chat_member(message.chat.id, message.from_user.id).status
        return status in ['administrator', 'creator']
    except: return False

def send_msg(chat_id, text, reply_to=None, markup=None):
    try:
        return bot.send_message(chat_id, text, reply_to_message_id=reply_to, reply_markup=markup, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        print(f"⚠️ Send Error: {e}")
        return None

# --- [ ЛОГИКА НАСТРОЕК (МЕНЮ) ] ---
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['настройки', 'settings'])
def show_settings(message):
    if not is_admin(message) or message.chat.type == 'private': return
    
    sid, l = message.chat.id, get_lang(message.chat.id)
    st = db_query("SELECT antispam, warn_limit_action, lang FROM chat_settings WHERE chat_id=?", (sid,), fetch=True)
    if not st:
        db_query("INSERT INTO chat_settings (chat_id) VALUES (?)", (sid,))
        st = {'antispam': 0, 'warn_limit_action': 'mute', 'lang': 'ru'}

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_spam = types.InlineKeyboardButton(f"{STRINGS[l]['spam']}: {'✅' if st['antispam'] else '❌'}", callback_data=f"toggle_spam_{sid}")
    btn_warn = types.InlineKeyboardButton(f"{STRINGS[l]['warn_act']}: {STRINGS[l]['mute_24'] if st['warn_limit_action'] == 'mute' else STRINGS[l]['ban']}", callback_data=f"toggle_warn_{sid}")
    btn_lang = types.InlineKeyboardButton(f"{STRINGS[l]['lang']}: {st['lang'].upper()}", callback_data=f"toggle_lang_{sid}")
    
    markup.add(btn_spam, btn_warn, btn_lang)
    send_msg(sid, STRINGS[l]['settings_title'], markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('toggle_'))
def handle_callbacks(call):
    if not is_admin(call.message):
        return bot.answer_callback_query(call.id, "❌ No access")
    
    sid = int(call.data.split('_')[-1])
    if "toggle_spam" in call.data:
        db_query("UPDATE chat_settings SET antispam = 1 - antispam WHERE chat_id=?", (sid,))
    elif "toggle_warn" in call.data:
        res = db_query("SELECT warn_limit_action FROM chat_settings WHERE chat_id=?", (sid,), fetch=True)
        new_act = "ban" if res['warn_limit_action'] == "mute" else "mute"
        db_query("UPDATE chat_settings SET warn_limit_action = ? WHERE chat_id=?", (new_act, sid))
    elif "toggle_lang" in call.data:
        res = db_query("SELECT lang FROM chat_settings WHERE chat_id=?", (sid,), fetch=True)
        new_lang = "en" if res['lang'] == "ru" else "ru"
        db_query("UPDATE chat_settings SET lang = ? WHERE chat_id=?", (new_lang, sid))

    # Обновляем интерфейс
    l = get_lang(sid)
    st = db_query("SELECT antispam, warn_limit_action, lang FROM chat_settings WHERE chat_id=?", (sid,), fetch=True)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"{STRINGS[l]['spam']}: {'✅' if st['antispam'] else '❌'}", callback_data=f"toggle_spam_{sid}"),
        types.InlineKeyboardButton(f"{STRINGS[l]['warn_act']}: {STRINGS[l]['mute_24'] if st['warn_limit_action'] == 'mute' else STRINGS[l]['ban']}", callback_data=f"toggle_warn_{sid}"),
        types.InlineKeyboardButton(f"{STRINGS[l]['lang']}: {st['lang'].upper()}", callback_data=f"toggle_lang_{sid}")
    )
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id, "Done!")

# --- [ КОМАНДЫ МОДЕРАЦИИ ] ---
def run_mod_action(message):
    l = get_lang(message.chat.id)
    text = message.text.lower()
    cmd = text.split()[0]
    target_id, target_name = None, None

    if message.reply_to_message:
        target_id, target_name = message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name
    else:
        match = re.search(r'@(\w+)', message.text)
        if match:
            res = db_query("SELECT user_id, name FROM users WHERE chat_id=? AND LOWER(username)=?", (message.chat.id, match.group(1).lower()), fetch=True)
            if res: target_id, target_name = res['user_id'], res['name']
    
    if not target_id: return send_msg(message.chat.id, STRINGS[l]['reply_req'])

    try:
        if cmd in ['мут', 'mute']:
            m = re.search(r'(\d+)([mмhчdд])', text)
            sec = int(m.group(1)) * (60 if m.group(2) in ['m','м'] else 3600 if m.group(2) in ['h','ч'] else 86400) if m else 3600
            bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + sec)
            send_msg(message.chat.id, STRINGS[l]['mute_msg'].format(target_name, sec//60))
        elif cmd in ['бан', 'ban']:
            bot.ban_chat_member(message.chat.id, target_id)
            send_msg(message.chat.id, STRINGS[l]['ban_msg'].format(target_name))
        elif cmd in ['размут', 'unmute']:
            bot.restrict_chat_member(message.chat.id, target_id, permissions=types.ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True, can_invite_users=True))
            send_msg(message.chat.id, STRINGS[l]['unmute_msg'].format(target_name))
        elif cmd in ['варн', 'warn']:
            db_query("UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            u = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (message.chat.id, target_id), fetch=True)
            st = db_query("SELECT warn_limit_action FROM chat_settings WHERE chat_id=?", (message.chat.id,), fetch=True)
            if u['warns'] >= 3:
                db_query("UPDATE users SET warns = 0 WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
                act_str = STRINGS[l]['mute_24'] if st['warn_limit_action'] == 'mute' else STRINGS[l]['ban']
                if st['warn_limit_action'] == 'mute': bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + 86400)
                else: bot.ban_chat_member(message.chat.id, target_id)
                send_msg(message.chat.id, STRINGS[l]['warn_limit'].format(target_name, act_str))
            else: send_msg(message.chat.id, STRINGS[l]['warn_msg'].format(target_name, u['warns']))
        elif cmd in ['анварн', 'unwarn']:
            db_query("UPDATE users SET warns = CASE WHEN warns > 0 THEN warns - 1 ELSE 0 END WHERE chat_id=? AND user_id=?", (message.chat.id, target_id))
            send_msg(message.chat.id, STRINGS[l]['unwarn_msg'].format(target_name))
    except Exception as e:
        send_msg(message.chat.id, f"⚠️ Error: {e}")

# --- [ ТОПЫ ] ---
def get_leaderboard(message):
    l = get_lang(message.chat.id)
    cmd, cid, now = message.text.lower(), message.chat.id, int(time.time())
    
    if cmd in ['репотоп', 'reptop']:
        res = db_query("SELECT name, rep FROM users WHERE chat_id=? AND rep > 0 ORDER BY rep DESC LIMIT 10", (cid,), fetch_all=True)
        title, unit = "💎 REPUTATION TOP" if l=='en' else "💎 ТОП РЕПУТАЦИИ", "⭐"
    else:
        res = db_query("SELECT name, messages FROM users WHERE chat_id=? ORDER BY messages DESC LIMIT 10", (cid,), fetch_all=True)
        title, unit = "🏆 ACTIVITY TOP" if l=='en' else "🏆 ТОП АКТИВНОСТИ", "✉️"

    if not res: return send_msg(cid, STRINGS[l]['empty_top'])
    
    body = f"📊 **{title}**\n━━━━━━━━━━━━━━\n"
    for i, row in enumerate(res, 1):
        body += f"{i}. {row[0]} — `{row[1]}` {unit}\n"
    send_msg(cid, body)

# --- [ ОБРАБОТКА ВСЕХ СООБЩЕНИЙ ] ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'sticker', 'video', 'document'])
def main_handler(message):
    l = get_lang(message.chat.id)
    uid, cid = message.from_user.id, message.chat.id
    text = (message.text or "").lower()

    # Приватные команды
    if message.chat.type == 'private':
        if text == '/start':
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(STRINGS[l]['add_chat'], url=f"https://t.me/{bot.get_me().username}?startgroup=true"))
            markup.add(types.InlineKeyboardButton(STRINGS[l]['cmd_list'], url=COMMANDS_URL))
            return send_msg(cid, STRINGS[l]['start'].format(message.from_user.first_name), markup=markup)
        elif text == '/help':
            return send_msg(cid, STRINGS[l]['help'].format(COMMANDS_URL))
        elif text == '/chats' and uid == ADMIN_ID:
            res = db_query("SELECT title, chat_id, member_count FROM chats_info", fetch_all=True)
            out = "📂 **Active Chats:**\n" + "\n".join([f"• {r[0]} (`{r[1]}`) | {r[2]} users" for r in res]) if res else "No chats yet."
            return send_msg(cid, out)
        return

    # --- [ ГРУППОВАЯ ЛОГИКА ] ---
    
    # 1. Антиспам
    st = db_query("SELECT antispam FROM chat_settings WHERE chat_id=?", (cid,), fetch=True)
    if st and st['antispam'] and not is_admin(message):
        if re.search(r'http[s]?://|t\.me/', text):
            try: return bot.delete_message(cid, message.message_id)
            except: pass

    # 2. Обновление БД
    db_query("INSERT OR REPLACE INTO chats_info (chat_id, title, member_count) VALUES (?,?,?)", (cid, message.chat.title, bot.get_chat_member_count(cid)))
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id, username, name) VALUES (?,?,?,?)", (cid, uid, (message.from_user.username or "none").lower(), message.from_user.first_name))
    db_query("UPDATE users SET messages = messages + 1, name = ? WHERE chat_id=? AND user_id=?", (message.from_user.first_name, cid, uid))
    db_query("INSERT INTO messages_log (chat_id, user_id, timestamp) VALUES (?,?,?)", (cid, uid, int(time.time())))

    # 3. Обработка триггеров
    words = text.split()
    if not words: return

    # Репутация
    if message.reply_to_message and text in ['+', 'спасибо', 'сяп', 'thanks', 'ty']:
        target = message.reply_to_message.from_user
        if target.id != uid and not target.is_bot:
            db_query("UPDATE users SET rep = rep + 1 WHERE chat_id=? AND user_id=?", (cid, target.id))
            send_msg(cid, STRINGS[l]['rep_up'].format(target.first_name), reply_to=message.message_id)

    # Профиль
    elif text in ['профиль', 'стата', 'profile', 'stats']:
        u = db_query("SELECT warns, messages, rep FROM users WHERE chat_id=? AND user_id=?", (cid, uid), fetch=True)
        send_msg(cid, STRINGS[l]['profile'].format(message.from_user.first_name, u['rep'], u['messages'], u['warns']), reply_to=message.message_id)

    # Топы
    elif text in ['топ', 'репотоп', 'top', 'reptop']:
        get_leaderboard(message)

    # Предсказание (Кнео)
    elif text.startswith(('кнео', 'kneo')):
        send_msg(cid, f"🔮 {random.choice(STRINGS[l]['kneo_ans'])}", reply_to=message.message_id)

    # Модерация
    elif words[0] in ['мут', 'mute', 'бан', 'ban', 'варн', 'warn', 'размут', 'unmute', 'анварн', 'unwarn']:
        if is_admin(message): run_mod_action(message)

# --- [ ВСТУПЛЕНИЕ В ГРУППУ ] ---
@bot.message_handler(content_types=['new_chat_members'])
def welcome(message):
    l = get_lang(message.chat.id)
    for u in message.new_chat_members:
        if u.id == bot.get_me().id:
            send_msg(message.chat.id, STRINGS[l]['activated'].format(COMMANDS_URL))
        else:
            send_msg(message.chat.id, f"👋 {u.first_name}! {STRINGS[l]['cmd_list']}: /help", reply_to=message.message_id)

# --- [ FLASK & WEBHOOK ] ---
@app.route('/' + (TOKEN if TOKEN else "default"), methods=['POST'])
def get_update():
    if not TOKEN: return "!", 400
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    if not TOKEN: return "No Token", 500
    bot.set_webhook(url=f"https://{request.host}/{TOKEN}")
    return "ONLINE", 200
