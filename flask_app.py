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

# Создание таблиц
db_query('''CREATE TABLE IF NOT EXISTS users 
    (chat_id int, user_id int, warns int DEFAULT 0, messages int DEFAULT 0, rep int DEFAULT 0, 
    PRIMARY KEY (chat_id, user_id))''')

# --- [ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ] ---
def check_admin(message):
    """Проверяет, является ли отправитель админом."""
    if message.chat.type == 'private': return True
    status = bot.get_chat_member(message.chat.id, message.from_user.id).status
    return status in ['administrator', 'creator']

def parse_time(text):
    """Парсит время из текста (напр. 10м, 2ч, 1д)."""
    match = re.search(r'(\d+)([мчд])', text.lower())
    if not match: return 3600 # По умолчанию 1 час
    amount, unit = int(match.group(1)), match.group(2)
    if unit == 'м': return amount * 60
    if unit == 'ч': return amount * 3600
    if unit == 'д': return amount * 86400
    return 3600

# --- [ КОМАНДЫ МОДЕРАЦИИ ] ---

@bot.message_handler(func=lambda m: m.reply_to_message and m.text and m.text.lower().split()[0] in ['мут', 'бан', 'кик', 'варн', 'размут'])
def moder_commands(message):
    if not check_admin(message):
        return bot.reply_to(message, "⚠️ **У вас нет прав для этой команды!**", parse_mode="Markdown")

    chat_id = message.chat.id
    target = message.reply_to_message.from_user
    text = message.text.lower().split()
    cmd = text[0]

    # Защита от мута админов
    if bot.get_chat_member(chat_id, target.id).status in ['administrator', 'creator']:
        return bot.reply_to(message, "❌ **Я не могу наказывать администраторов!**", parse_mode="Markdown")

    try:
        if cmd == 'мут':
            seconds = parse_time(message.text)
            bot.restrict_chat_member(chat_id, target.id, until_date=int(time.time()) + seconds)
            bot.reply_to(message, f"🔇 **{target.first_name}** отправлен в мут на `{seconds//60}` мин.", parse_mode="Markdown")

        elif cmd == 'размут':
            bot.restrict_chat_member(chat_id, target.id, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)
            bot.reply_to(message, f"🔊 **{target.first_name}** снова может общаться!", parse_mode="Markdown")

        elif cmd == 'бан':
            bot.ban_chat_member(chat_id, target.id)
            bot.reply_to(message, f"🔨 **{target.first_name}** успешно забанен!", parse_mode="Markdown")

        elif cmd == 'кик':
            bot.unban_chat_member(chat_id, target.id)
            bot.reply_to(message, f"👢 **{target.first_name}** исключен из чата.", parse_mode="Markdown")

        elif cmd == 'варн':
            db_query("INSERT OR IGNORE INTO users (chat_id, user_id) VALUES (?,?)", (chat_id, target.id))
            db_query("UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?", (chat_id, target.id))
            data = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (chat_id, target.id), fetch=True)
            warns_count = data['warns']
            
            if warns_count >= 3:
                bot.restrict_chat_member(chat_id, target.id, until_date=int(time.time()) + 86400)
                db_query("UPDATE users SET warns = 0 WHERE chat_id=? AND user_id=?", (chat_id, target.id))
                bot.reply_to(message, f"⛔ **{target.first_name}** набрал 3/3 варна и получил мут на 24 часа!")
            else:
                bot.reply_to(message, f"⚠️ **{target.first_name}**, вам выдан варн! ({warns_count}/3)", parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, f"❌ **Ошибка выполнения:** `{e}`\nПроверьте, есть ли у бота права администратора!", parse_mode="Markdown")

# --- [ СИСТЕМА ПРОФИЛЯ И РЕПУТАЦИИ ] ---

@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['профиль', 'стата', 'мои данные'])
def profile(message):
    uid, cid = message.from_user.id, message.chat.id
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id) VALUES (?,?)", (cid, uid))
    res = db_query("SELECT warns, messages, rep FROM users WHERE chat_id=? AND user_id=?", (cid, uid), fetch=True)
    
    card = (
        f"💳 **ЛИЧНАЯ КАРТОЧКА**\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 **Юзер:** `{message.from_user.first_name}`\n"
        f"✉️ **Сообщений:** `{res['messages']}`\n"
        f"💎 **Репутация:** `{res['rep']}`\n"
        f"⚠️ **Варны:** `{res['warns']}/3`\n"
        f"━━━━━━━━━━━━━━"
    )
    bot.reply_to(message, card, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.reply_to_message and m.text and m.text.lower() in ['+', 'спасибо', 'сяп', 'респект'])
def plus_rep(message):
    target = message.reply_to_message.from_user
    if target.id == message.from_user.id or target.is_bot: return
    
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id) VALUES (?,?)", (message.chat.id, target.id))
    db_query("UPDATE users SET rep = rep + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, target.id))
    bot.reply_to(message, f"⭐ **{message.from_user.first_name}** поднял репутацию **{target.first_name}**!")

# --- [ ОБЩАЯ ЛОГИКА ] ---

@bot.message_handler(func=lambda m: True)
def counter_and_kneo(message):
    # Счётчик сообщений
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id) VALUES (?,?)", (message.chat.id, message.from_user.id))
    db_query("UPDATE users SET messages = messages + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, message.from_user.id))
    
    # Реакция Кнео
    if message.text and message.text.lower().startswith('кнео'):
        responses = ["Безусловно ✅", "Нет ❌", "Я так не думаю 🧐", "Это секрет 🤫", "100%!", "Маловероятно..."]
        bot.reply_to(message, f"🔮 **Ответ:** {random.choice(responses)}", parse_mode="Markdown")

# --- [ WEBHOOK ] ---
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    bot.set_webhook(url=f"https://{request.host}/{TOKEN}")
    return "<h1>KNEO ULTRA ONLINE</h1>", 200
