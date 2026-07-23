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

user_notifications = {}

# ==========================================
# 🌐 FLASK SERVER
# ==========================================
@app.route('/')
def home():
    return "Bot is running ultra-smoothly!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# 🗄️ DATABASE FUNCTIONS
# ==========================================
def setup_db():
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, balance REAL DEFAULT 0, user_id INTEGER DEFAULT 0)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS chat_data (chat_id INTEGER PRIMARY KEY, pinned_msg_id INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS commissions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            chat_id INTEGER,
                            amount REAL,
                            date_str TEXT,
                            timestamp REAL
                        )''')
        conn.commit()

def parse_amount(amount_str):
    amount_str = str(amount_str).lower().replace('₹', '').strip()
    try:
        if 'k' in amount_str:
            return float(amount_str.replace('k', '')) * 1000
        elif 'm' in amount_str:
            return float(amount_str.replace('m', '')) * 1000000
        return float(amount_str)
    except ValueError:
        return None

def update_balance(username, amount, user_id=0):
    clean_username = str(username).replace('@', '').strip().lower()
    if not clean_username:
        return
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT balance FROM users WHERE LOWER(username) = ?', (clean_username,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute('INSERT INTO users (username, balance, user_id) VALUES (?, ?, ?)', (clean_username, float(amount), user_id))
        else:
            new_bal = row[0] + float(amount)
            cursor.execute('UPDATE users SET balance = ?, user_id = CASE WHEN ? != 0 THEN ? ELSE user_id END WHERE LOWER(username) = ?', 
                           (new_bal, user_id, user_id, clean_username))
        conn.commit()

def get_user_balance(username):
    clean_username = str(username).replace('@', '').strip().lower()
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT balance FROM users WHERE LOWER(username) = ?', (clean_username,))
        row = cursor.fetchone()
        return row[0] if row else 0.0

def get_all_balances():
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT username, balance, user_id FROM users WHERE balance != 0 ORDER BY username COLLATE NOCASE ASC')
        return cursor.fetchall()

def get_total_group_minus():
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(balance) FROM users WHERE balance < 0')
        row = cursor.fetchone()
        return abs(row[0]) if row and row[0] else 0.0

def record_commission(chat_id, comm_amount):
    today_str = datetime.now().strftime('%Y-%m-%d')
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO commissions (chat_id, amount, date_str, timestamp) VALUES (?, ?, ?, ?)',
                       (chat_id, float(comm_amount), today_str, time.time()))
        conn.commit()

def get_7_days_commission_report(chat_id):
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        cursor = conn.cursor()
        report_lines = []
        total_7_days_comm = 0.0
        today = datetime.now()
        group_minus = get_total_group_minus()
        
        for i in range(7):
            date_obj = today - timedelta(days=i)
            date_str = date_obj.strftime('%Y-%m-%d')
            
            cursor.execute('SELECT SUM(amount), COUNT(id) FROM commissions WHERE chat_id = ? AND date_str = ?', (chat_id, date_str))
            row = cursor.fetchone()
            
            comm_sum = row[0] if row and row[0] else 0.0
            table_count = row[1] if row and row[1] else 0
            total_7_days_comm += comm_sum
            
            disp_comm = int(comm_sum) if comm_sum.is_integer() else round(comm_sum, 2)
            daily_minus = group_minus if i == 0 else 0.0
            net_profit = comm_sum - daily_minus
            disp_net = int(net_profit) if net_profit.is_integer() else round(net_profit, 2)
            disp_minus = int(daily_minus) if daily_minus.is_integer() else round(daily_minus, 2)
            
            if i == 0:
                report_lines.append(f"<b>Today ({date_str})</b>: Comm: ₹{disp_comm} | Minus: ₹{disp_minus} | <b>Net: ₹{disp_net}</b> ({table_count} Tables)")
            else:
                date_fmt = date_obj.strftime('%d %b')
                report_lines.append(f"<b>{date_fmt}</b>: Comm: ₹{disp_comm}")
                
        disp_total = int(total_7_days_comm) if total_7_days_comm.is_integer() else round(total_7_days_comm, 2)
        return report_lines, disp_total

def get_pinned_msg(chat_id):
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT pinned_msg_id FROM chat_data WHERE chat_id = ?', (chat_id,))
        result = cursor.fetchone()
        return result[0] if result else None

def set_pinned_msg(chat_id, msg_id):
    with sqlite3.connect(DB_NAME, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO chat_data (chat_id, pinned_msg_id) VALUES (?, ?)', (chat_id, msg_id))
        conn.commit()

# ==========================================
# 🛡️ SECURITY & UTILITIES
# ==========================================
def auto_delete_message(chat_id, message_id, delay=1):
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def is_admin_or_owner(chat_id, user_id):
    if user_id == OWNER_ID:
        return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception:
        return False

def make_profile_link(username):
    clean_name = str(username).replace('@', '').strip()
    return f"<a href='https://t.me/{clean_name}'>{clean_name}</a>"

# ==========================================
# 📜 ALPHABETICAL A-Z LIST GENERATOR
# ==========================================
def generate_live_list_text(chat_title):
    records = get_all_balances()
    text = f"🙏🏻 Welcome & thanks everyone playing and winning with us we are always there for you if want any kind of information please contact @Carry_Bhau\n"
    text += f"➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
    text += f"💼 <b>Balance Records (Page 1/1):</b>\n\n"
    
    if not records:
        text += "No records found.\n"
    else:
        alphabet_groups = {}
        for username, balance, u_id in records:
            first_char = username[0].upper() if username else '#'
            if not first_char.isalpha():
                first_char = '#'
            if first_char not in alphabet_groups:
                alphabet_groups[first_char] = []
            alphabet_groups[first_char].append((username, balance, u_id))
            
        count = 1
        sorted_keys = sorted(alphabet_groups.keys())
        
        for key in sorted_keys:
            for username, balance, u_id in alphabet_groups[key]:
                disp_balance = int(balance) if balance.is_integer() else round(balance, 2)
                user_link = make_profile_link(username)
                text += f"{count}. {user_link} = {disp_balance}\n"
                count += 1
            text += "➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
            
    text += "\n⏺️ Check Full Records..."
    return text

def get_list_buttons():
    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton("Check Your Balance 💵", callback_data="check_my_bal")
    btn2 = InlineKeyboardButton("Switch Inline ↗️", switch_inline_query="")
    btn3 = InlineKeyboardButton("Notification ⚙️", callback_data="toggle_notif")
    btn4 = InlineKeyboardButton("🔄 Refresh", callback_data="refresh_list")
    
    markup.row(btn1)
    markup.row(btn2, btn3)
    markup.row(btn4)
    return markup

def update_live_list(chat_id, chat_title):
    list_text = generate_live_list_text(chat_title)
    pinned_msg_id = get_pinned_msg(chat_id)
    markup = get_list_buttons()

    if pinned_msg_id:
        try:
            bot.edit_message_text(list_text, chat_id, pinned_msg_id, reply_markup=markup, parse_mode='HTML', disable_web_page_preview=True)
            return
        except Exception:
            pass

    try:
        msg = bot.send_message(chat_id, list_text, reply_markup=markup, parse_mode='HTML', disable_web_page_preview=True)
        bot.pin_chat_message(chat_id, msg.message_id)
        set_pinned_msg(chat_id, msg.message_id)
    except Exception:
        pass

# ==========================================
# 🤖 COMMANDS & HANDLERS
# ==========================================

@bot.message_handler(commands=['start'])
def handle_start(message):
    if message.chat.type == 'private':
        user_first_name = message.from_user.first_name or "User"
        username = message.from_user.username or "None"
        user_id = message.from_user.id
        
        bal = get_user_balance(username) if username != "None" else 0.0
        disp_bal = int(bal) if bal.is_integer() else round(bal, 2)
        notif_status = user_notifications.get(user_id, "Active")
        
        start_text = f"🗂️<b>{user_first_name}'s INFO:</b>\n\n"
        start_text += f"💵 <b>Balance :</b> {disp_bal}\n"
        start_text += f"📕 <b>Side Balance:</b> 0\n"
        start_text += f"♎ <b>Custom Fee:</b> Inactive\n"
        start_text += f"🗣️ <b>Chat ID:</b> {message.chat.id}\n"
        start_text += f"🔔 <b>Notification:</b> {notif_status}\n\n"
        start_text += f"📖 <b>Bot Version:</b> 2.8.70\n"
        start_text += f"📖 <b>Demo Bot:</b> @crkt3bot\n"
        start_text += f"🥷 <b>Bot Developer:</b> @molicoder"

        markup = InlineKeyboardMarkup()
        btn1 = InlineKeyboardButton("Switch Inline ↗️", switch_inline_query="")
        btn2 = InlineKeyboardButton(f"🔔 Notification: {'OFF' if notif_status == 'Active' else 'ON'}", callback_data="toggle_start_notif")
        btn3 = InlineKeyboardButton("🔄 Refresh", callback_data="refresh_start_info")
        
        markup.row(btn1)
        markup.row(btn2)
        markup.row(btn3)

        bot.send_message(message.chat.id, start_text, reply_markup=markup, parse_mode='HTML')

@bot.message_handler(content_types=['new_chat_members'])
def on_join(message):
    for member in message.new_chat_members:
        if member.id == bot.get_me().id:
            if message.from_user.id != OWNER_ID:
                bot.leave_chat(message.chat.id)
                return

@bot.message_handler(commands=['start_list'])
def manual_list_trigger(message):
    if not is_admin_or_owner(message.chat.id, message.from_user.id):
        return
    update_live_list(message.chat.id, message.chat.title)
    threading.Thread(target=auto_delete_message, args=(message.chat.id, message.message_id, 1)).start()

@bot.message_handler(commands=['add', 'minus'])
def handle_add_minus(message):
    if not is_admin_or_owner(message.chat.id, message.from_user.id):
        return

    parts = message.text.split()
    target_username = None
    target_user_id = 0
    amount_str = None

    if message.reply_to_message:
        replied_user = message.reply_to_message.from_user
        if replied_user and not replied_user.is_bot:
            target_username = replied_user.username
            target_user_id = replied_user.id
        elif message.reply_to_message.text:
            usernames = re.findall(r'@(\w+)', message.reply_to_message.text)
            if usernames:
                target_username = usernames[0]
        
        if len(parts) >= 2:
            amount_str = parts[1]

    if not target_username and len(parts) >= 3:
        amount_str = parts[1]
        target_username = parts[2].replace('@', '').strip()

    if target_username and amount_str:
        amount = parse_amount(amount_str)
        if amount is not None:
            if message.text.startswith('/minus'):
                amount = -amount

            update_balance(target_username, amount, target_user_id)
            action = "added" if amount > 0 else "deducted"
            reply_msg = bot.reply_to(message, f"✅ ₹{abs(amount)} {action} for @{target_username}")
            
            threading.Thread(target=auto_delete_message, args=(message.chat.id, reply_msg.message_id, 2)).start()
            threading.Thread(target=auto_delete_message, args=(message.chat.id, message.message_id, 2)).start()
            
            update_live_list(message.chat.id, message.chat.title)

@bot.message_handler(commands=['balance', 'balanceinfo'])
def handle_balance_check(message):
    target_username = None
    parts = message.text.split()

    if message.reply_to_message and message.reply_to_message.from_user and not message.reply_to_message.from_user.is_bot:
        target_username = message.reply_to_message.from_user.username
    elif len(parts) >= 2:
        target_username = parts[1].replace('@', '').strip()
    else:
        target_username = message.from_user.username

    if not target_username:
        msg = bot.reply_to(message, "❌ User has no telegram username set!")
        threading.Thread(target=auto_delete_message, args=(message.chat.id, msg.message_id, 3)).start()
        return

    bal = get_user_balance(target_username)
    disp_bal = int(bal) if bal.is_integer() else round(bal, 2)
    
    msg = bot.reply_to(message, f"👤 @{target_username}\n💰 Current Balance: <b>₹{disp_bal}</b>", parse_mode='HTML')
    threading.Thread(target=auto_delete_message, args=(message.chat.id, msg.message_id, 5)).start()
    threading.Thread(target=auto_delete_message, args=(message.chat.id, message.message_id, 2)).start()

@bot.message_handler(commands=['commission'])
def show_commission_report(message):
    if not is_admin_or_owner(message.chat.id, message.from_user.id):
        return

    daily_lines, total_7_days = get_7_days_commission_report(message.chat.id)
    
    report_text = "📊 <b>7-DAYS COMMISSION & LEDGER REPORT</b>\n"
    report_text += "➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
    for line in daily_lines:
        report_text += f"{line}\n\n"
    report_text += "➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
    report_text += f"💰 <b>This Week Total Commission: ₹{total_7_days}</b>"
    
    bot.send_message(message.chat.id, report_text, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data in ["check_my_bal", "toggle_notif", "refresh_list", "toggle_start_notif", "refresh_start_info"])
def handle_button_callbacks(call):
    username = call.from_user.username
    user_id = call.from_user.id

    if call.data == "check_my_bal":
        if not username:
            bot.answer_callback_query(call.id, "❌ Pehle apna Telegram Username set karein!", show_alert=True)
            return
        bal = get_user_balance(username)
        disp_bal = int(bal) if bal.is_integer() else round(bal, 2)
        bot.answer_callback_query(call.id, f"👤 @{username}\n💰 Aapka Balance: ₹{disp_bal}", show_alert=True)

    elif call.data == "refresh_list":
        update_live_list(call.message.chat.id, call.message.chat.title)
        bot.answer_callback_query(call.id, "✅ List Refreshed!")

    elif call.data == "toggle_notif":
        curr = user_notifications.get(user_id, "Active")
        user_notifications[user_id] = "Inactive" if curr == "Active" else "Active"
        bot.answer_callback_query(call.id, f"Notification Status: {user_notifications[user_id]}")

    elif call.data == "toggle_start_notif":
        curr = user_notifications.get(user_id, "Active")
        user_notifications[user_id] = "Inactive" if curr == "Active" else "Active"
        bot.answer_callback_query(call.id, f"Notifications turned {user_notifications[user_id]}")

    elif call.data == "refresh_start_info":
        bot.answer_callback_query(call.id, "ℹ️ Info Refreshed!")

# 🎲 TABLE DETECTION
@bot.message_handler(func=lambda message: message.text and ('✅' in message.text or '✔️' in message.text))
def detect_table(message):
    if not is_admin_or_owner(message.chat.id, message.from_user.id):
        return

    text = message.text.strip()
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if len(lines) >= 3:
        player1 = lines[0].replace('@', '').strip()
        player2 = lines[1].replace('@', '').strip()
        last_line_text = lines[-1]
        
        match = re.search(r'(\d+)', last_line_text)
        
        if match:
            try:
                amount = float(match.group(1))
                
                p1_link = make_profile_link(player1)
                p2_link = make_profile_link(player2)
                
                markup = InlineKeyboardMarkup()
                btn1 = InlineKeyboardButton("#1 won", callback_data=f"w|1|{player1}|{player2}|{amount}|{last_line_text}")
                btn2 = InlineKeyboardButton("#2 won", callback_data=f"w|2|{player2}|{player1}|{amount}|{last_line_text}")
                markup.row(btn1, btn2)
                
                bot.send_message(message.chat.id, f"🎲 <b>Table Set!</b>\n\n(1). {p1_link}\n(2). {p2_link}\n💰 {last_line_text}", reply_markup=markup, parse_mode='HTML', disable_web_page_preview=True)
                
                try:
                    bot.delete_message(message.chat.id, message.message_id)
                except Exception:
                    pass

            except ValueError:
                pass

# 🏆 WINNER CLICK HANDLER
@bot.callback_query_handler(func=lambda call: call.data.startswith('w|'))
def process_winner(call):
    bot.answer_callback_query(call.id, "Updating Result...")

    if not is_admin_or_owner(call.message.chat.id, call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Only Admins can set result!", show_alert=True)
        return

    try:
        data_parts = call.data.split('|')
        won_choice = data_parts[1]
        winner = data_parts[2]
        loser = data_parts[3]
        full_amount = float(data_parts[4])
        last_line_text = data_parts[5]
        
        commission_cut = (full_amount * COMMISSION_RATE) / 100.0
        winner_net_amount = full_amount - commission_cut
        
        update_balance(winner, winner_net_amount)
        update_balance(loser, -full_amount)
        record_commission(call.message.chat.id, commission_cut)
        
        winner_link = make_profile_link(winner)
        loser_link = make_profile_link(loser)

        if won_choice == '1':
            p1_str = f"(1). {winner_link} ✔️✔️"
            p2_str = f"(2). {loser_link}"
        else:
            p1_str = f"(1). {loser_link}"
            p2_str = f"(2). {winner_link} ✔️✔️"

        result_msg_text = f"🎲 <i>Table Status</i>\n\n{p1_str}\n\n{p2_str}\n\n{last_line_text}"
        
        bot.send_message(call.message.chat.id, result_msg_text, parse_mode='HTML', disable_web_page_preview=True)
        
        try:
            bot.delete_messag
