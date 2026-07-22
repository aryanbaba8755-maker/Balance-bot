import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import threading
import time
import os
import re
from datetime import datetime, timedelta
from flask import Flask

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
TOKEN = "8898313784:AAH1oqsItqzvgrgVsbKvodjxei0l6uYbARY"
OWNER_ID = 2107169286           
COMMISSION_RATE = 5.0             # Exact 5% Commission
DB_NAME = 'group_balance.db'

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ==========================================
# 🌐 FLASK SERVER
# ==========================================
@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# 🗄️ DATABASE FUNCTIONS (Fixed Multi-threading)
# ==========================================
def get_db():
    return sqlite3.connect(DB_NAME, timeout=10, check_same_thread=False)

def setup_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, balance REAL DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS chat_data (chat_id INTEGER PRIMARY KEY, pinned_msg_id INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS commissions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER,
                        amount REAL,
                        date_str TEXT,
                        timestamp REAL
                    )''')
    conn.commit()
    conn.close()

def update_balance(username, amount):
    clean_username = username.replace('@', '').strip().lower()
    if not clean_username:
        return
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT balance FROM users WHERE LOWER(username) = ?', (clean_username,))
        row = cursor.fetchone()
        
        if row is None:
            cursor.execute('INSERT INTO users (username, balance) VALUES (?, ?)', (clean_username, float(amount)))
        else:
            new_bal = row[0] + float(amount)
            cursor.execute('UPDATE users SET balance = ? WHERE LOWER(username) = ?', (new_bal, clean_username))
            
        conn.commit()
    except Exception as e:
        print(f"DB Update Error: {e}")
    finally:
        conn.close()

def get_user_balance(username):
    clean_username = username.replace('@', '').strip().lower()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE LOWER(username) = ?', (clean_username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0.0

def get_all_balances():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT username, balance FROM users WHERE balance != 0 ORDER BY username COLLATE NOCASE ASC')
    records = cursor.fetchall()
    conn.close()
    return records

def record_commission(chat_id, comm_amount):
    today_str = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO commissions (chat_id, amount, date_str, timestamp) VALUES (?, ?, ?, ?)',
                   (chat_id, float(comm_amount), today_str, time.time()))
    conn.commit()
    conn.close()

def get_7_days_commission_report(chat_id):
    conn = get_db()
    cursor = conn.cursor()
    
    report_lines = []
    total_7_days = 0.0
    today = datetime.now()
    
    for i in range(7):
        date_obj = today - timedelta(days=i)
        date_str = date_obj.strftime('%Y-%m-%d')
        
        cursor.execute('SELECT SUM(amount), COUNT(id) FROM commissions WHERE chat_id = ? AND date_str = ?', (chat_id, date_str))
        row = cursor.fetchone()
        
        comm_sum = row[0] if row[0] else 0.0
        table_count = row[1] if row[1] else 0
        total_7_days += comm_sum
        
        disp_comm = int(comm_sum) if comm_sum.is_integer() else round(comm_sum, 2)
        
        if i == 0:
            report_lines.append(f"<b>Today ({date_str})</b>: ₹{disp_comm} ({table_count} Tables)")
        else:
            date_fmt = date_obj.strftime('%d %b')
            report_lines.append(f"<b>{date_fmt}</b>: ₹{disp_comm} ({table_count} Tables)")
            
    conn.close()
    disp_total = int(total_7_days) if total_7_days.is_integer() else round(total_7_days, 2)
    return report_lines, disp_total

def get_pinned_msg(chat_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT pinned_msg_id FROM chat_data WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def set_pinned_msg(chat_id, msg_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO chat_data (chat_id, pinned_msg_id) VALUES (?, ?)', (chat_id, msg_id))
    conn.commit()
    conn.close()

# ==========================================
# 🛡️ UTILITY & SECURITY
# ==========================================
def auto_delete_message(chat_id, message_id, delay=2):
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def check_group_eligibility(chat_id):
    try:
        bot_member = bot.get_chat_member(chat_id, bot.get_me().id)
        if bot_member.status not in ['administrator', 'creator']:
            return False
        owner_member = bot.get_chat_member(chat_id, OWNER_ID)
        if owner_member.status not in ['administrator', 'creator']:
            return False
        return True
    except Exception:
        return False

def is_chat_admin(chat_id, user_id):
    if user_id == OWNER_ID:
        return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception:
        return False

# ==========================================
# 📜 LIST GENERATOR
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
        return

    list_text = generate_live_list_text(chat_title)
    pinned_msg_id = get_pinned_msg(chat_id)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("ℹ️ Check My Balance (/balanceinfo)", callback_data="check_my_bal"))

    if pinned_msg_id:
        try:
            bot.edit_message_text(list_text, chat_id, pinned_msg_id, reply_markup=markup, parse_mode='Markdown')
        except Exception as e:
            pass
    else:
        try:
            msg = bot.send_message(chat_id, list_text, reply_markup=markup, parse_mode='Markdown')
            bot.pin_chat_message(chat_id, msg.message_id)
            set_pinned_msg(chat_id, msg.message_id)
        except Exception as e:
            pass

# ==========================================
# 🤖 HANDLERS & COMMANDS
# ==========================================

@bot.message_handler(content_types=['new_chat_members'])
def on_join(message):
    for member in message.new_chat_members:
        if member.id == bot.get_me().id:
            if message.from_user.id != OWNER_ID:
                bot.leave_chat(message.chat.id)
                return

@bot.message_handler(commands=['start_list'])
def manual_list_trigger(message):
    if not check_group_eligibility(message.chat.id) or not is_chat_admin(message.chat.id, message.from_user.id):
        return
    update_live_list(message.chat.id, message.chat.title)
    threading.Thread(target=auto_delete_message, args=(message.chat.id, message.message_id, 1)).start()

@bot.message_handler(commands=['add', 'minus'])
def handle_add_minus(message):
    if not check_group_eligibility(message.chat.id) or not is_chat_admin(message.chat.id, message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) >= 3:
        try:
            amount = float(parts[1])
            username = parts[2].replace('@', '').strip()
            
            if message.text.startswith('/minus'):
                amount = -amount
            
            update_balance(username, amount)
            action = "added" if amount > 0 else "deducted"
            reply_msg = bot.reply_to(message, f"✅ ₹{abs(amount)} {action} for @{username}")
            
            threading.Thread(target=auto_delete_message, args=(message.chat.id, reply_msg.message_id, 2)).start()
            threading.Thread(target=auto_delete_message, args=(message.chat.id, message.message_id, 2)).start()
            
            update_live_list(message.chat.id, message.chat.title)
            
        except ValueError:
            pass

@bot.message_handler(commands=['commission'])
def show_commission_report(message):
    if not check_group_eligibility(message.chat.id) or not is_chat_admin(message.chat.id, message.from_user.id):
        return

    daily_lines, total_7_days = get_7_days_commission_report(message.chat.id)
    
    report_text = "📊 <b>7-DAYS COMMISSION REPORT</b> 📊\n"
    report_text += "➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
    for line in daily_lines:
        report_text += f"🔹 {line}\n"
    report_text += "\n➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
    report_text += f"💰 <b>This Week Total Commission: ₹{total_7_days}</b>"
    
    bot.send_message(message.chat.id, report_text, parse_mode='HTML')

# ℹ️ /balanceinfo Button Handler (Fixed Instant Response)
@bot.callback_query_handler(func=lambda call: call.data == "check_my_bal")
def callback_check_my_bal(call):
    username = call.from_user.username
    if not username:
        bot.answer_callback_query(call.id, "❌ Pehle apna Telegram Username set karein!", show_alert=True)
        return
    
    bal = get_user_balance(username)
    disp_bal = int(bal) if bal.is_integer() else round(bal, 2)
    
    # Direct Pop-up Alert
    bot.answer_callback_query(call.id, f"👤 @{username}\n💰 Aapka Balance: ₹{disp_bal}", show_alert=True)

@bot.message_handler(commands=['balanceinfo'])
def cmd_balance_info(message):
    username = message.from_user.username
    if not username:
        msg = bot.reply_to(message, "❌ Pehle apna Telegram Username set karein!")
        threading.Thread(target=auto_delete_message, args=(message.chat.id, msg.message_id, 3)).start()
        return
        
    bal = get_user_balance(username)
    disp_bal = int(bal) if bal.is_integer() else round(bal, 2)
    
    msg = bot.reply_to(message, f"👤 @{username}\n💰 Aapka Balance: <b>₹{disp_bal}</b>", parse_mode='HTML')
    threading.Thread(target=auto_delete_message, args=(message.chat.id, msg.message_id, 5)).start()
    threading.Thread(target=auto_delete_message, args=(message.chat.id, message.message_id, 2)).start()

# 🎲 Table Auto Detection
@bot.message_handler(func=lambda message: message.text and ('✅' in message.text or '✔️' in message.text or 'full' in message.text.lower()))
def detect_table(message):
    if not check_group_eligibility(message.chat.id) or not is_chat_admin(message.chat.id, message.from_user.id):
        return

    text = message.text.strip()
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if len(lines) >= 3:
        player1 = lines[0].replace('@', '').strip()
        player2 = lines[1].replace('@', '').strip()
        
        last_line = lines[-1]
        match = re.search(r'(\d+)', last_line)
        
        if match:
            try:
                amount = float(match.group(1))
                
                markup = InlineKeyboardMarkup()
                btn1 = InlineKeyboardButton("#1 won", callback_data=f"w_{player1}_{player2}_{amount}")
                btn2 = InlineKeyboardButton("#2 won", callback_data=f"w_{player2}_{player1}_{amount}")
                markup.row(btn1, btn2)
                
                bot.reply_to(message, f"🎲 <b>Table Set!</b>\n\n1. @{player1}\n2. @{player2}\n💰 Amount: ₹{amount}", reply_markup=markup, parse_mode='HTML')
                
            except ValueError:
                pass

# 🏆 Winner Click Handler (Fixed Loading Issue & Balance Sync)
@bot.callback_query_handler(func=lambda call: call.data.startswith('w_'))
def process_winner(call):
    # Turant Telegram ko response dena taaki Loading symbol hat jaye
    bot.answer_callback_query(call.id, "Processing Result...")

    if not check_group_eligibility(call.message.chat.id) or not is_chat_admin(call.message.chat.id, call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Only Admins can set result!", show_alert=True)
        return

    try:
        data_parts = call.data.split('_')
        winner = data_parts[1]
        loser = data_parts[2]
        full_amount = float(data_parts[3])
        
        # 5% Cut Calculation
        commission_cut = (full_amount * COMMISSION_RATE) / 100.0
        winner_net_amount = full_amount - commission_cut
        
        # Balance DB update
        update_balance(winner, winner_net_amount)
        update_balance(loser, -full_amount)
        record_commission(call.message.chat.id, commission_cut)
        
        disp_winner_amt = int(winner_net_amount) if winner_net_amount.is_integer() else round(winner_net_amount, 2)
        disp_comm = int(commission_cut) if commission_cut.is_integer() else round(commission_cut, 2)
        
        # Result text edit
        bot.edit_message_text(f"🏆 <b>Table Result</b>\n\n1. @{winner} ✔️✔️ (+₹{disp_winner_amt})\n2. @{loser} (-₹{full_amount})\n💰 Table: ₹{full_amount} | 📉 5% Comm: ₹{disp_comm}", 
                              call.message.chat.id, call.message.message_id, parse_mode='HTML')
        
        # INSTANT LIST EDIT
        update_live_list(call.message.chat.id, call.message.chat.title)
        
    except Exception as e:
        print(f"Error in process_winner: {e}")

# ==========================================
# 🚀 MAIN RUNNER
# ==========================================
if __name__ == "__main__":
    setup_db()
    threading.Thread(target=run_flask).start()
    
    print("Bot is 100% fixed and running...")
    bot.polling(none_stop=True)
