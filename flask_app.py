import os
import sqlite3
import random
import time
import re
import telebot
from telebot import types
from flask import Flask, request

# --- [ CONFIGURATION ] ---
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = 8364667153 
DB_PATH = 'kneo_base.db'
COMMANDS_URL = 'https://kneo-world.github.io/MANYAL-BOT-MANAGER/'

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

# --- [ LOCALIZATION (EN IS DEFAULT) ] ---
STRINGS = {
    'en': {
        'start': "👋 Hi, {}! I'm **Kneo**.\n\nA powerful chat manager. I track stats, moderate users, and keep your group safe.",
        'help': "❓ Command list is here:\n{}",
        'add_chat': "➕ Add to Group",
        'cmd_list': "📖 Commands",
        'settings_title': "⚙️ **Kneo Settings**\n\nConfigure bot behavior for this chat:",
        'spam': "Anti-links",
        'warn_act': "On 3/3 warns",
        'lang': "Language / Язык",
        'mute_24': "🔇 Mute 24h",
        'ban': "🔨 Ban",
        'admin_only': "❌ Only admins can do this!",
        'reply_req': "💬 Reply to a message or tag @username",
        'mute_msg': "🔇 **{}** has been muted for {} min.",
        'unmute_msg': "🔊 **{}** is now unmuted.",
        'ban_msg': "🔨 **{}** has been banned.",
        'warn_msg': "⚠️ Warning for **{}** ({}/3).",
        'warn_limit': "⛔ Limit reached! **{}** punished: {}",
        'unwarn_msg': "🗑 One warning removed from **{}**.",
        'rep_up': "💎 **{}** (+1 rep!). Total: `{}`.",
        'rep_cooldown': "⏳ Slow down! You can give rep once every 5 minutes.",
        'empty_top': "📊 Leaderboard is empty...",
        'profile': "👤 **PROFILE: {}**\n━━━━━━━━━━━━━━\n🆔 ID: `{}`\n⭐ Reputation: `{}`\n✉️ Messages: `{}`\n⚠️ Warns: `{}/3`",
        'activated': "🚀 Kneo is ready! Commands: {}",
        'kneo_ans': ["Yes", "No", "I think so", "100%", "Unlikely", "Ask later"]
    },
    'ru': {
        'start': "👋 Привет, {}! Я **Kneo**.\n\nЯ мощный менеджер для управления чатами. Могу следить за порядком, вести статистику и развлекать участников.",
        'help': "❓ Список команд доступен по ссылке:\n{}",
        'add_chat': "➕ Добавить в чат",
        'cmd_list': "📖 Команды",
        'settings_title': "⚙️ **Настройки Kneo**\n\nЗдесь можно настроить поведение бота для этого чата:",
        'spam': "Анти-ссылки",
        'warn_act': "При 3/3 варнах",
        'lang': "Язык / Language",
        'mute_24': "🔇 Мут 24ч",
        'ban': "🔨 Бан",
        'admin_only': "❌ Только админы могут это делать!",
        'reply_req': "💬 Ответьте на сообщение или тегните @username",
        'mute_msg': "🔇 **{}** отправлен в мут на {} мин.",
        'unmute_msg': "🔊 **{}** снова может говорить.",
        'ban_msg': "🔨 **{}** был забанен.",
        'warn_msg': "⚠️ Варн для **{}** ({}/3).",
        'warn_limit': "⛔ Лимит достигнут! **{}** наказан: {}",
        'unwarn_msg': "🗑 С пользователя **{}** снят варн.",
        'rep_up': "💎 **{}** (+1 реп!). Теперь у него `{}`.",
        'rep_cooldown': "⏳ Не так быстро! Повышать репутацию можно раз в 5 минут.",
        'empty_top': "📊 Тут пока пусто...",
        'profile': "👤 **ПРОФИЛЬ: {}**\n━━━━━━━━━━━━━━\n🆔 ID: `{}`\n⭐ Репутация: `{}`\n✉️ Сообщений: `{}`\n⚠️ Варны: `{}/3`",
        'activated': "🚀 Kneo готов к работе! Команды: {}",
        'kneo_ans': ["Да", "Нет", "Думаю, да", "100%", "Маловероятно", "Спроси позже"]
    }
}

# --- [ DATABASE CORE ] ---
def db_query(sql, params=(), fetch=False, fetch_all=False):
    try:
        with sqlite3.connect(DB_PATH, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params)
            if fetch: return cursor.fetchone()
            if fetch_all: return cursor.fetchall()
            conn.commit()
    except Exception as e: print(f"DB Error: {e}")
    return None

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users (
        chat_id int, user_id int, username text, name text, 
        warns int DEFAULT 0, messages int DEFAULT 0, rep int DEFAULT 0, 
        last_rep_time int DEFAULT 0, PRIMARY KEY (chat_id, user_id))''')
    db_query('CREATE TABLE IF NOT EXISTS chat_settings (chat_id int PRIMARY KEY, antispam int DEFAULT 0, warn_limit_action text DEFAULT "mute", lang text DEFAULT "en")')
    db_query('CREATE TABLE IF NOT EXISTS chats_info (chat_id int PRIMARY KEY, title text, member_count int)')

init_db()

# --- [ UTILS ] ---
def get_lang(chat_id):
    res = db_query("SELECT lang FROM chat_settings WHERE chat_id=?", (chat_id,), fetch=True)
    if not res:
        db_query("INSERT OR IGNORE INTO chat_settings (chat_id, lang) VALUES (?, 'en')", (chat_id,))
        return 'en'
    return res['lang']

def is_admin(m):
    if m.chat.type == 'private': return True
    try:
        member = bot.get_chat_member(m.chat.id, m.from_user.id)
        return member.status in ['administrator', 'creator']
    except: return False

def send(m, text, markup=None):
    tid = getattr(m, 'message_thread_id', None)
    return bot.send_message(m.chat.id, text, reply_to_message_id=m.message_id, reply_markup=markup, parse_mode="Markdown", message_thread_id=tid)

# --- [ SETTINGS MENU ] ---
def get_settings_markup(cid):
    l = get_lang(cid)
    st = db_query("SELECT antispam, warn_limit_action, lang FROM chat_settings WHERE chat_id=?", (cid,), fetch=True)
    if not st: return None
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    if bot.get_chat(cid).type != 'private':
        markup.add(
            types.InlineKeyboardButton(f"{STRINGS[l]['spam']}: {'✅' if st['antispam'] else '❌'}", callback_data=f"cfg_spam_{cid}"),
            types.InlineKeyboardButton(f"{STRINGS[l]['warn_act']}: {STRINGS[l]['mute_24'] if st['warn_limit_action'] == 'mute' else STRINGS[l]['ban']}", callback_data=f"cfg_warn_{cid}")
        )
    markup.add(types.InlineKeyboardButton(f"{STRINGS[l]['lang']}: {st['lang'].upper()}", callback_data=f"cfg_lang_{cid}"))
    return markup

@bot.message_handler(commands=['settings'])
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['настройки', 'settings'])
def cmd_settings(m):
    if not is_admin(m): return send(m, STRINGS[get_lang(m.chat.id)]['admin_only'])
    l = get_lang(m.chat.id)
    send(m, STRINGS[l]['settings_title'], markup=get_settings_markup(m.chat.id))

@bot.callback_query_handler(func=lambda c: c.data.startswith('cfg_'))
def cb_settings(c):
    cid = int(c.data.split('_')[-1])
    if bot.get_chat(cid).type != 'private':
        if bot.get_chat_member(cid, c.from_user.id).status not in ['administrator', 'creator']:
            return bot.answer_callback_query(c.id, "No access")

    if "cfg_spam" in c.data:
        db_query("UPDATE chat_settings SET antispam = 1 - antispam WHERE chat_id=?", (cid,))
    elif "cfg_warn" in c.data:
        curr = db_query("SELECT warn_limit_action FROM chat_settings WHERE chat_id=?", (cid,), fetch=True)['warn_limit_action']
        db_query("UPDATE chat_settings SET warn_limit_action = ? WHERE chat_id=?", ("ban" if curr == "mute" else "mute", cid))
    elif "cfg_lang" in c.data:
        curr = db_query("SELECT lang FROM chat_settings WHERE chat_id=?", (cid,), fetch=True)['lang']
        db_query("UPDATE chat_settings SET lang = ? WHERE chat_id=?", ("ru" if curr == "en" else "en", cid))

    bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=get_settings_markup(cid))
    bot.answer_callback_query(c.id, "Updated!")

# --- [ MESSAGE HANDLER ] ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'sticker', 'video', 'document'])
def handle_all(m):
    uid, cid = m.from_user.id, m.chat.id
    l = get_lang(cid)
    raw_text = m.text or ""
    txt = raw_text.lower().strip()

    # DB Logic
    if m.chat.type != 'private':
        db_query("INSERT OR IGNORE INTO chat_settings (chat_id, lang) VALUES (?, 'en')", (cid,))
        db_query("INSERT OR IGNORE INTO users (chat_id, user_id, username, name) VALUES (?,?,?,?)", (cid, uid, (m.from_user.username or "none").lower(), m.from_user.first_name))
        db_query("UPDATE users SET messages = messages + 1, name = ? WHERE chat_id=? AND user_id=?", (m.from_user.first_name, cid, uid))
        
        # Anti-Spam
        st = db_query("SELECT antispam FROM chat_settings WHERE chat_id=?", (cid,), fetch=True)
        if st and st['antispam'] and not is_admin(m):
            if re.search(r'http[s]?://|t\.me/', txt):
                try: return bot.delete_message(cid, m.message_id)
                except: pass

    # Commands logic
    if txt == '/start':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(STRINGS[l]['add_chat'], url=f"https://t.me/{bot.get_me().username}?startgroup=true"))
        return send(m, STRINGS[l]['start'].format(m.from_user.first_name), markup=markup)

    if txt == '/help': return send(m, STRINGS[l]['help'].format(COMMANDS_URL))

    # Rep System (Handles "+", "thanks", etc.)
    rep_triggers = ['+', 'спасибо', 'сяп', 'thanks', 'ty', 'thank you']
    if m.reply_to_message and any(trigger == txt for trigger in rep_triggers):
        target = m.reply_to_message.from_user
        if target.id != uid and not target.is_bot:
            u_data = db_query("SELECT last_rep_time FROM users WHERE chat_id=? AND user_id=?", (cid, uid), fetch=True)
            if u_data and (int(time.time()) - u_data['last_rep_time'] < 300):
                return send(m, STRINGS[l]['rep_cooldown'])
            
            db_query("UPDATE users SET rep = rep + 1 WHERE chat_id=? AND user_id=?", (cid, target.id))
            db_query("UPDATE users SET last_rep_time = ? WHERE chat_id=? AND user_id=?", (int(time.time()), cid, uid))
            res = db_query("SELECT rep FROM users WHERE chat_id=? AND user_id=?", (cid, target.id), fetch=True)
            send(m, STRINGS[l]['rep_up'].format(target.first_name, res['rep']))

    # Profile & Stats
    elif txt in ['profile', 'stats', 'профиль', 'стата']:
        u = db_query("SELECT warns, messages, rep FROM users WHERE chat_id=? AND user_id=?", (cid, uid), fetch=True)
        if u: send(m, STRINGS[l]['profile'].format(m.from_user.first_name, uid, u['rep'], u['messages'], u['warns']))

    # Tops
    elif txt in ['top', 'reptop', 'топ', 'репотоп']:
        is_rep = 'rep' in txt or 'репо' in txt
        col = "rep" if is_rep else "messages"
        res = db_query(f"SELECT name, {col} FROM users WHERE chat_id=? AND {col} > 0 ORDER BY {col} DESC LIMIT 10", (cid,), fetch_all=True)
        if not res: return send(m, STRINGS[l]['empty_top'])
        out = f"📊 **{'REPTOP' if is_rep else 'TOP'}**\n━━━━━━━━━━━━━━\n"
        for i, r in enumerate(res, 1): out += f"{i}. {r[0]} — `{r[1]}`\n"
        send(m, out)

    # Magic Ball
    elif txt.startswith(('kneo', 'кнео')):
        send(m, f"🔮 {random.choice(STRINGS[l]['kneo_ans'])}")

    # Admin Moderation
    elif txt.split() and txt.split()[0] in ['mute', 'ban', 'warn', 'unmute', 'unwarn', 'мут', 'бан', 'варн', 'размут', 'анварн']:
        if is_admin(m): handle_mod(m, txt.split(), l)

def handle_mod(m, words, l):
    cmd = words[0]
    target_id, target_name = None, None
    if m.reply_to_message:
        target_id, target_name = m.reply_to_message.from_user.id, m.reply_to_message.from_user.first_name
    else:
        match = re.search(r'@(\w+)', m.text)
        if match:
            res = db_query("SELECT user_id, name FROM users WHERE chat_id=? AND LOWER(username)=?", (m.chat.id, match.group(1).lower()), fetch=True)
            if res: target_id, target_name = res['user_id'], res['name']
    
    if not target_id: return send(m, STRINGS[l]['reply_req'])

    try:
        if cmd in ['mute', 'мут']:
            m_time = re.search(r'(\d+)([mмhчdд])', m.text.lower())
            sec = int(m_time.group(1)) * (60 if m_time.group(2) in ['m','м'] else 3600 if m_time.group(2) in ['h','ч'] else 86400) if m_time else 3600
            bot.restrict_chat_member(m.chat.id, target_id, until_date=int(time.time()) + sec)
            send(m, STRINGS[l]['mute_msg'].format(target_name, sec//60))
        elif cmd in ['ban', 'бан']:
            bot.ban_chat_member(m.chat.id, target_id)
            send(m, STRINGS[l]['ban_msg'].format(target_name))
        elif cmd in ['warn', 'варн']:
            db_query("UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?", (m.chat.id, target_id))
            u = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (m.chat.id, target_id), fetch=True)
            if u['warns'] >= 3:
                db_query("UPDATE users SET warns = 0 WHERE chat_id=? AND user_id=?", (m.chat.id, target_id))
                st = db_query("SELECT warn_limit_action FROM chat_settings WHERE chat_id=?", (m.chat.id,), fetch=True)
                if st['warn_limit_action'] == 'mute':
                    bot.restrict_chat_member(m.chat.id, target_id, until_date=int(time.time()) + 86400)
                    send(m, STRINGS[l]['warn_limit'].format(target_name, STRINGS[l]['mute_24']))
                else:
                    bot.ban_chat_member(m.chat.id, target_id)
                    send(m, STRINGS[l]['warn_limit'].format(target_name, STRINGS[l]['ban']))
            else: send(m, STRINGS[l]['warn_msg'].format(target_name, u['warns']))
    except Exception as e: print(e)

@bot.message_handler(content_types=['new_chat_members'])
def on_enter(m):
    l = get_lang(m.chat.id)
    for u in m.new_chat_members:
        if u.id == bot.get_me().id: send(m, STRINGS[l]['activated'].format(COMMANDS_URL))

# --- [ WEBHOOK ] ---
@app.route('/' + (TOKEN if TOKEN else "default"), methods=['POST'])
def get_update():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    bot.set_webhook(url=f"https://{request.host}/{TOKEN}")
    return "KNEO ONLINE", 200
