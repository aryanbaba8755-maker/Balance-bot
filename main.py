import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import threading
import time
import os
from flask import Flask

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
TOKEN = "8898313784:AAH1oqsItqzvgrgVsbKvodjxei0l6uYbARY"
OWNER_ID = 2107169286           # Bot Owner ki Telegram User ID
COMMISSION_RATE = 5             # Fixed 5% Commission
DB_NAME = 'group_balance.db'

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ==========================================
# 🌐 FLASK SERVER (Fast Deployment)
# ==========================================
@app.route('/')
def home():
    return "Bot is running ultra-fast!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# 🗄️ DATABASE FUNCTIONS
# ==========================================
def setup_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, balance REAL DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS chat_data (chat_id INTEGER PRIMARY KEY, pinned_msg_id INTEGER)''')
    conn.commit()
    conn.close()

def update_balance(username, amount):
    clean_username = username.replace('@', '').strip()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (username, balance) VALUES (?, 0)', (clean_username,))
    cursor.execute('UPDATE users SET balance = balance + ? WHERE username = ?', (amount, clean_username))
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
# 🛡️ SECURITY & VERIFICATION FUNCTIONS
# ==========================================
def auto_delete_message(chat_id, message_id, delay=2):
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def check_group_eligibility(chat_id):
    """Check karega ki Bot aur Owner dono Group me Admin hain ya nahi"""
    try:
        # 1. Check Bot Admin Status
        bot_member = bot.get_chat_member(chat_id, bot.get_me().id)
        if bot_member.status not in ['administrator', 'creator']:
            return False
        
        # 2. Check Owner Admin Status
        owner_member = bot.get_chat_member(chat_id, OWNER_ID)
        if owner_member.status not in ['administrator', 'creator']:
            return False

        return True
    except Exception:
        return False

def handle_ineligible_group(chat_id):
    """Agar eligibility fail hoti hai toh List Delete kar dega"""
    pinned_msg_id = get_pinned_msg(chat_id)
    if pinned_msg_id:
        try:
            bot.delete_message(chat_id, pinned_msg_id)
            set_pinned_msg(chat_id, None)
        except Exception:
            pass

def is_chat_admin(chat_id, user_id):
    """Check karega ki Command dene wala banda Group ka Admin hai ya nahi"""
    if user_id == OWNER_ID:
        return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception:
        return False

# ==========================================
# 📜 LIST GENERATOR (Zero Links)
# ==========================================
def generate_live_list_text(chat_title):
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
            # Display balance upto 2 decimal places if fractional
            disp_balance = int(balance) if balance.is_integer() else round(balance, 2)
            text += f"{count}. {username} = {disp_balance}\n"
            if count % 3 == 0 and i != len(records) - 1:
                text += "≕≔≕≔≕≔≕≔≕≔≕≔≕≔≕≔≕≔\n"
            count += 1
            
    text += "\n➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
    text += "⏺️ Check Full Records..."
    return text

def update_live_list(chat_id, chat_title):
    if not check_group_eligibility(chat_id):
        handle_ineligible_group(chat_id)
        return

    list_text = generate_live_list_text(chat_title)
    pinned_msg_id = get_pinned_msg(chat_id)
    
    if pinned_msg_id:
        try:
            bot.edit_message_text(list_text, chat_id, pinned_msg_id, parse_mode='Markdown')
        except Exception:
            pass
    else:
        msg = bot.send_message(chat_id, list_text, parse_mode='Markdown')
        try:
            bot.pin_chat_message(chat_id, msg.message_id)
            set_pinned_msg(chat_id, msg.message_id)
        except Exception:
            pass

# ==========================================
# 🤖 EVENT HANDLERS & COMMANDS
# ==========================================

# 🚪 Group Join Security Guard (Owner Only Addition)
@bot.message_handler(content_types=['new_chat_members'])
def on_join(message):
    for member in message.new_chat_members:
        if member.id == bot.get_me().id:
            # Check kisne add kiya
            adder_id = message.from_user.id
            if adder_id != OWNER_ID:
                # Owner ke alawa kisi aur ne add kiya toh LEFT!
                bot.leave_chat(message.chat.id)
                return

# 1️⃣ Start List Command
@bot.message_handler(commands=['start_list'])
def manual_list_trigger(message):
    if not check_group_eligibility(message.chat.id):
        handle_ineligible_group(message.chat.id)
        return
        
    if not is_chat_admin(message.chat.id, message.from_user.id):
        return

    update_live_list(message.chat.id, message.chat.title)
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass

# 2️⃣ Manual /add aur /minus Commands
@bot.message_handler(commands=['add', 'minus'])
def handle_add_minus(message):
    if not check_group_eligibility(message.chat.id):
        handle_ineligible_group(message.chat.id)
        return

    if not is_chat_admin(message.chat.id, message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) >= 3:
        try:
            amount = float(parts[1])
            username = parts[2]
            
            if message.text.startswith('/minus'):
                amount = -amount
            
            update_balance(username, amount)
            action = "added" if amount > 0 else "deducted"
            
            reply_msg = bot.reply_to(message, f"✅ {abs(amount)} {action} for @{username.replace('@', '')}")
            
            threading.Thread(target=auto_delete_message, args=(message.chat.id, reply_msg.message_id, 2)).start()
            threading.Thread(target=auto_delete_message, args=(message.chat.id, message.message_id, 2)).start()
            
            update_live_list(message.chat.id, message.chat.title)
            
        except ValueError:
            pass

# 3️⃣ AUTO TABLE DETECTION (5% Commission Logic)
@bot.message_handler(func=lambda message: message.text and ('✅' in message.text or '✔️' in message.text))
def detect_table(message):
    if not check_group_eligibility(message.chat.id):
        handle_ineligible_group(message.chat.id)
        return

    if not is_chat_admin(message.chat.id, message.from_user.id):
        return

    text = message.text.strip()
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if len(lines) >= 3:
        player1 = lines[0].replace('@', '').strip()
        player2 = lines[1].replace('@', '').strip()
        
        try:
            amount_str = lines[-1].replace('✅', '').replace('✔️', '').replace('full', '').strip()
            amount = float(amount_str)
            
            markup = InlineKeyboardMarkup()
            btn1 = InlineKeyboardButton("#1 won", callback_data=f"w_{player1}_{player2}_{amount}")
            btn2 = InlineKeyboardButton("#2 won", callback_data=f"w_{player2}_{player1}_{amount}")
            markup.row(btn1, btn2)
            
            bot.reply_to(message, f"🎲 **Table Set!**\n\n1. @{player1}\n2. @{player2}\n💰 Amount: {amount}", reply_markup=markup, parse_mode='Markdown')
            
        except ValueError:
            pass

# 4️⃣ WINNER CLICK HANDLER (With 5% Cut Math)
@bot.callback_query_handler(func=lambda call: call.data.startswith('w_'))
def process_winner(call):
    if not check_group_eligibility(call.message.chat.id):
        handle_ineligible_group(call.message.chat.id)
        return

    if not is_chat_admin(call.message.chat.id, call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Sirf Group Admins result set kar sakte hain!", show_alert=True)
        return

    data_parts = call.data.split('_')
    winner = data_parts[1]
    loser = data_parts[2]
    full_amount = float(data_parts[3])
    
    # 💥 5% Commission Cut Calculation
    commission_cut = (full_amount * COMMISSION_RATE) / 100
    winner_net_amount = full_amount - commission_cut
    
    # Update Balances: Winner gets (Amount - 5%), Loser loses Full Amount
    update_balance(winner, winner_net_amount)
    update_balance(loser, -full_amount)
    
    bot.edit_message_text(f"🏆 **Table Result**\n\n1. @{winner} ✔️✔️\n2. @{loser}\n💰 Amount: {full_amount}\n📉 (5% Cut: {commission_cut})", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
    
    threading.Thread(target=auto_delete_message, args=(call.message.chat.id, call.message.message_id, 2)).start()
    
    # Live List Edit Update
    update_live_list(call.message.chat.id, call.message.chat.title)
    
    bot.answer_callback_query(call.id, f"✅ Updated! {winner} won +{winner_net_amount} (5% cut)")

# ==========================================
# 🚀 MAIN RUNNER
# ==========================================
if __name__ == "__main__":
    setup_db()
    threading.Thread(target=run_flask).start()
    
    print("Bot running with strict rules & 5% commission cut...")
    bot.polling(none_stop=True)
            
