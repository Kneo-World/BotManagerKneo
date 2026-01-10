import os
import sqlite3
import random
from flask import Flask, request
import telebot

# --- НАСТРОЙКИ ---
TOKEN = '8202182875:AAEecFwxWQFBjny1-5VrGa9jDKsJaYOKxnA'
DB_PATH = 'kneo_base.db'

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

def db_query(sql, params=(), fetch=False):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=20)
        cursor = conn.cursor()
        cursor.execute(sql, params)
        if fetch: return cursor.fetchone()
        conn.commit()
    except Exception as e: print(f"DB Error: {e}")
    finally:
        if conn: conn.close()
    return None

# Инициализация БД
db_query('''CREATE TABLE IF NOT EXISTS users 
    (chat_id int, user_id int, warns int DEFAULT 0, messages int DEFAULT 0, PRIMARY KEY (chat_id, user_id))''')

@bot.message_handler(func=lambda m: m.text and m.text.lower() in ['профиль', 'стата'])
def get_profile(message):
    data = db_query("SELECT warns, messages FROM users WHERE chat_id=? AND user_id=?", 
                    (message.chat.id, message.from_user.id), fetch=True)
    w, m = data if data else (0, 0)
    bot.reply_to(message, f"👤 {message.from_user.first_name}\n⚠️ Варны: {w}/5\n✉️ Сообщений: {m}")

@bot.message_handler(func=lambda m: True)
def main_handler(message):
    db_query("INSERT OR IGNORE INTO users (chat_id, user_id) VALUES (?,?)", (message.chat.id, message.from_user.id))
    db_query("UPDATE users SET messages = messages + 1 WHERE chat_id=? AND user_id=?", (message.chat.id, message.from_user.id))
    if message.text and message.text.lower().startswith('кнео'):
        bot.reply_to(message, random.choice(['Да', 'Нет', 'Конечно!']))

@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@app.route('/')
def setup():
    # Render сам выдаст нам домен, мы привяжем его при первом посещении
    webhook_url = f"https://{request.host}/{TOKEN}"
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    return f"Бот запущен! Webhook установлен на: {webhook_url}", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
