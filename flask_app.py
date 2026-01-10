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
    (chat_id int, user_id int, warns int DEFAULT 0, messages int DEFAULT 0, rep int DEFAULT 0, 
    PRIMARY KEY (chat_id, user_id))''')

# --- [ ПРОВЕРКА ПРАВ ] ---
def check_admin(message):
    if message.chat.type == 'private': return True
    status = bot.get_chat_member(message.chat.id, message.from_user.id).status
    return status in ['administrator', 'creator']

# --- [ КОМАНДЫ МОДЕРАЦИИ (ПОЛНЫЙ НАБОР) ] ---

@bot.message_handler(func=lambda m: m.text and m.text.lower().split()[0] in ['мут', 'бан', 'кик', 'варн', 'размут', 'разбан', 'анварн'])
def moder_commands(message):
    if not check_admin(message):
        return bot.reply_to(message, "⚠️ **Доступ запрещен.** Команда только для админов.")

    chat_id = message.chat.id
    cmd = message.text.lower().split()[0]
    
    # Для команд, требующих ответ (реплай)
    if not message.reply_to_message and cmd not in ['разбан']:
        return bot.reply_to(message, "💬 Ответьте на сообщение пользователя этой командой!")

    target = message.reply_to_message.from_user if message.reply_to_message else None
    
    try:
        # --- БАН И РАЗБАН ---
        if cmd == 'бан':
            bot.ban_chat_member(chat_id, target.id)
            bot.reply_to(message, f"🔨 **{target.first_name}** забанен.")
            
        elif cmd == 'разбан':
            # Разбан работает либо по реплаю, либо если админ знает ID (но тут сделаем по реплаю для простоты)
            bot.unban_chat_member(chat_id, target.id, only_if_banned=True)
            bot.reply_to(message, f"✅ **{target.first_name}** разбанен.")

        # --- МУТ И РАЗМУТ ---
        elif cmd == 'мут':
            bot.restrict_chat_member(chat_id, target.id, until_date=int(time.time()) + 3600)
            bot.reply_to(message, f"🔇 **{target.first_name}** в муте на 1 час.")
            
        elif cmd == 'размут':
            bot.restrict_chat_member(chat_id, target.id, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)
            bot.reply_to(message, f"🔊 Мут с пользователя **{target.first_name}** снят.")

        # --- ВАРН И АНВАРН ---
        elif cmd == 'варн':
            db_query("INSERT OR IGNORE INTO users (chat_id, user_id) VALUES (?,?)", (chat_id, target.id))
            db_query("UPDATE users SET warns = warns + 1 WHERE chat_id=? AND user_id=?", (chat_id, target.id))
            data = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (chat_id, target.id), fetch=True)
            bot.reply_to(message, f"⚠️ Варн выдан! Всего: `{data['warns']}/3`", parse_mode="Markdown")
            
        elif cmd == 'анварн':
            db_query("UPDATE users SET warns = MAX(0, warns - 1) WHERE chat_id=? AND user_id=?", (chat_id, target.id))
            data = db_query("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (chat_id, target.id), fetch=True)
            bot.reply_to(message, f"🗑 Один варн снят. Текущий счет: `{data['warns']}/3`", parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: Убедитесь, что я админ и у меня есть права на это действие. \n`{e}`")

# --- [ ОСТАЛЬНЫЕ ФУНКЦИИ (ПРОФИЛЬ, КНЕО) ] ---

@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['профиль', 'стата'])
def profile(message):
    uid, cid = message.from_user.id, message.chat.id
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id) VALUES (?,?)", (cid, uid))
    res = db_query("SELECT warns, messages, rep FROM users WHERE chat_id=? AND user_id=?", (cid, uid), fetch=True)
    bot.reply_to(message, f"👤 **{message.from_user.first_name}**\n⭐ Репутация: `{res['rep']}`\n✉️ Сообщений: `{res['messages']}`\n⚠️ Варны: `{res['warns']}/3`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def global_handler(message):
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id) VALUES (?,?)", (message.chat.id, message.from_user.id))
    db_query("UPDATE users SET messages = messages + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, message.from_user.id))
    if message.text and message.text.lower().startswith('кнео'):
        bot.reply_to(message, f"🔮 Ответ: {random.choice(['Да', 'Нет', 'Думаю, да', '100%', 'Нет иди нахуй', 'Я думаю тебе лутче пойти нахуй])}")

# --- [ WEBHOOK ] ---
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    bot.set_webhook(url=f"https://{request.host}/{TOKEN}")
    return "<h1>KNEO SYSTEM ONLINE</h1>", 200
