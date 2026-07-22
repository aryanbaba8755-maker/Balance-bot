import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import threading
import time
import os
from flask import Flask

# ==========================================
# ⚙️ CONFIGURATION (Yahan apni details daalein)
# ==========================================
TOKEN = "8898313784:AAHjuGjYKluW9sfJtfNeRZbQShKT5Wt9X1s" # Apna Telegram Bot Token daalein
OWNER_ID = 2107169286           # Apni Telegram User ID daalein (Admin access ke liye)
DB_NAME = 'group_balance.db'

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ==========================================
# 🌐 FLASK SERVER (Render Web Service ke liye)
# ==========================================
@app.route('/')
def home():
    return "Bot is active and running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# 🗄️ DATABASE FUNCTIONS (SQLite)
# ==========================================
def setup_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Users table
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, balance INTEGER DEFAULT 0)''')
    # Chat data table (Pinned list ka message ID save karne ke liye)
    cursor.execute('''CREATE TABLE IF NOT EXISTS chat_data (chat_id INTEGER PRIMARY KEY, pinned_msg_id INTEGER)''')
    conn.commit()
    conn.close()

def update_balance(username, amount):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Agar user naya hai toh pehle use 0 balance ke sath add karega
    cursor.execute('INSERT OR IGNORE INTO users (username, balance) VALUES (?, 0)', (username,))
    # Fir balance update karega
    cursor.execute('UPDATE users SET balance = balance + ? WHERE username = ?', (amount, username))
    conn.commit()
    conn.close()

def get_all_balances():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT username, balance FROM users ORDER BY username COLLATE NOCASE ASC')
    records = cursor.fetchall()
    conn.close()
    return records

def get_pinned_msg(chat_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT pinned_msg_id FROM chat_data WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def set_pinned_msg(chat_id, msg_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO chat_data (chat_id, pinned_msg_id) VALUES (?, ?)', (chat_id, msg_id))
    conn.commit()
    conn.close()

# ==========================================
# 🛠️ UTILITY FUNCTIONS
# ==========================================
def is_admin(user_id):
    return user_id == OWNER_ID

def auto_delete_message(chat_id, message_id, delay=2):
    """Background mein wait karke message delete karega"""
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def generate_live_list_text(chat_title):
    """Group list ka design exactly aapke format jaisa"""
    records = get_all_balances()
    text = f"✨ Thanks everyone for playing with us! Your support means a lot ❤️\n"
    text += f"➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
    text += f"👉 For Rules : Contact Admins\n\n"
    text += f"💾 Balance Records (Page 1/1) - **{chat_title}**:\n\n"
    
    if not records:
        text += "No records found.\n"
    else:
        count = 1
        for i, (username, balance) in enumerate(records):
            text += f"{count}. {username} = {balance}\n"
            
            # Har 3 users ke baad separator add karna (Last user ke baad nahi)
            if count % 3 == 0 and i != len(records) - 1:
                text += "≕≔≕≔≕≔≕≔≕≔≕≔≕≔≕≔≕≔\n"
            count += 1
            
    text += "\n➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
    text += "⏺️ Check Full Records..."
    return text

def update_live_list(chat_id, chat_title):
    """Pinned list ko update ya nayi list create karna"""
    list_text = generate_live_list_text(chat_title)
    pinned_msg_id = get_pinned_msg(chat_id)
    
    if pinned_msg_id:
        try:
            bot.edit_message_text(list_text, chat_id, pinned_msg_id, parse_mode='Markdown')
        except Exception:
            pass # Ignore agar text completely same hai
    else:
        # Nayi list bhejna aur pin karna
        msg = bot.send_message(chat_id, list_text, parse_mode='Markdown')
        try:
            bot.pin_chat_message(chat_id, msg.message_id)
            set_pinned_msg(chat_id, msg.message_id)
        except Exception:
            bot.send_message(chat_id, "⚠️ List pin karne ke liye bot ko Admin banayein!")

# ==========================================
# 🤖 BOT COMMANDS & HANDLERS
# ==========================================

# Pehli baar list start karne ke liye owner yeh command use karega
@bot.message_handler(commands=['start_list'])
def manual_list_trigger(message):
    if not is_admin(message.from_user.id):
        return
    update_live_list(message.chat.id, message.chat.title)
    bot.delete_message(message.chat.id, message.message_id) # Command delete 
   # 1️⃣ Auto Table Detection (Space aur @ Auto Clean ke saath)
@bot.message_handler(func=lambda message: True)
def detect_table(message):
    text = message.text.strip()
    lines = [line.strip() for line in text.split('\n') if line.strip()] # Blank lines hata dega
    
    # Check karega ki kam se kam 3 lines hon aur aakhri line me ✔️ ho
    if len(lines) >= 3 and '✔️' in lines[-1]:
        # '@' symbol hata kar clean name nikalna
        player1 = lines[0].replace('@', '').strip()
        player2 = lines[1].replace('@', '').strip()
        
        try:
            # Amounts se ✔️ hata kar number nikalna
            amount_str = lines[-1].replace('✔️', '').replace('full', '').strip()
            amount = int(amount_str)
            
            # Clickable Buttons (Short data format: win_player1_player2_amount)
            markup = InlineKeyboardMarkup()
            btn1 = InlineKeyboardButton("1 Won", callback_data=f"w_{player1}_{player2}_{amount}")
            btn2 = InlineKeyboardButton("2 Won", callback_data=f"w_{player2}_{player1}_{amount}")
            markup.row(btn1, btn2)
            
            bot.reply_to(message, f"🎲 **Table Set!**\n1. {player1}\n2. {player2}\n💰 Amount: {amount}", reply_markup=markup, parse_mode='Markdown')
            
        except ValueError:
            pass # Agar amount sahi number nahi hai toh ignore karega

# 2️⃣ Winner Selection & Balance Update
@bot.callback_query_handler(func=lambda call: call.data.startswith('w_'))
def process_winner(call):
    # Security: Sirf Owner/Admin result set kar sakein
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Sirf Admins result set kar sakte hain!", show_alert=True)
        return

    data_parts = call.data.split('_')
    winner = data_parts[1]
    loser = data_parts[2]
    amount = int(data_parts[3])
    
    # Balance update
    update_balance(winner, amount)
    update_balance(loser, -amount)
    
    # Message par result update karna
    bot.edit_message_text(f"🏆 **Table Result**\n\n1. {winner} ✔️✔️\n2. {loser}\n💰 Amount: {amount}", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    
    # Result msg ko 2 second me delete karna
    threading.Thread(target=auto_delete_message, args=(call.message.chat.id, call.message.message_id, 2)).start()
    
    # Live List ko update karna
    update_live_list(call.message.chat.id, call.message.chat.title)
    
    bot.answer_callback_query(call.id, f"✅ Updated: {winner} +{amount} | {loser} -{amount}")
    
    # Admin ko choti notification dena (Screen ke upar)
    bot.answer_callback_query(call.id, f"✅ Balance Updated: {winner} won {amount}!")

# ==========================================
# 🚀 MAIN RUNNER
# ==========================================
if __name__ == "__main__":
    setup_db() # Database tables banayega
    threading.Thread(target=run_flask).start() # Flask server start karega (Port error theek karne ke liye)
    
    print("Bot is successfully running...")
    bot.polling(none_stop=True)
