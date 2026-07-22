import telebot
import threading
import time

TOKEN = "8898313784:AAHjuGjYKluW9sfJtfNeRZbQShKT5Wt9X1s"
bot = telebot.TeleBot("8898313784:AAHjuGjYKluW9sfJtfNeRZbQShKT5Wt9X1s")

OWNER_ID = 2107169286 # Yahan bot owner ki apni Telegram User ID aayegi
ADMINS = [OWNER_ID]  # Baad me isme aur admins add kar sakte hain

# Database ki jagah demo dictionary (Asli me SQLite use hoga)
# Store karenge ki kis group me konsi List Pinned hai
chat_pinned_lists = {} # Format: {chat_id: message_id} 

# -------------------------------------------------------------
# 1. SECURITY & ACCESS CONTROL
# -------------------------------------------------------------
def is_admin(user_id):
    return user_id in ADMINS

# Jab bot kisi naye group me add ho
@bot.message_handler(content_types=['new_chat_members'])
def check_group_authorization(message):
    for new_member in message.new_chat_members:
        if new_member.id == bot.get_me().id:
            # Bot add hua hai, check karo Owner admin hai ya nahi
            try:
                owner_status = bot.get_chat_member(message.chat.id, OWNER_ID).status
                if owner_status not in ['administrator', 'creator']:
                    bot.send_message(message.chat.id, "❌ Bot Owner is group me Admin nahi hai. Main leave kar raha hoon.")
                    bot.leave_chat(message.chat.id)
            except Exception:
                bot.leave_chat(message.chat.id)

# -------------------------------------------------------------
# 2. AUTO-DELETE NOTIFICATION FUNCTION
# -------------------------------------------------------------
def auto_delete_message(chat_id, message_id, delay=2):
    """Background me 2 second wait karke message delete karega"""
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass # Agar message pehle hi delete ho gaya ho toh ignore

# -------------------------------------------------------------
# 3. LIVE PINNED LIST UPDATE FUNCTION
# -------------------------------------------------------------
def update_live_list(chat_id, chat_title):
    # Yahan DB se saare active balances nikalenge (Demo text banaya hai)
    # List ke top par Group ka naam aayega
    new_text = f"🌟 **{chat_title} - Live Balance List** 🌟\n\n"
    new_text += "👤 Arjun : 4500\n"
    new_text += "👤 Pankaj : -500\n"
    new_text += "\n*(Auto Updating List...)*"

    if chat_id in chat_pinned_lists:
        # Purani list ko edit karna
        try:
            bot.edit_message_text(new_text, chat_id, chat_pinned_lists[chat_id], parse_mode='Markdown')
        except Exception:
            pass # Agar content same hua toh Telegram error na de
    else:
        # Agar pehli baar list ban rahi hai toh send karke pin karna
        msg = bot.send_message(chat_id, new_text, parse_mode='Markdown')
        bot.pin_chat_message(chat_id, msg.message_id)
        chat_pinned_lists[chat_id] = msg.message_id # ID save kar li aage edit karne ke liye

# -------------------------------------------------------------
# 4. TABLE TICK & BALANCE UPDATE
# -------------------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith('win_'))
def handle_winner_tick(call):
    # Button dabane wale ki permission check karna
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Sirf Admins tick laga sakte hain!", show_alert=True)
        return

    # Data alag karna: ID use karenge taaki same naam me confusion na ho
    _, winner_id, loser_id, amount = call.data.split('_')
    
    # 1. Database me balance update karna (winner me plus, loser me minus)
    # db.update_balance(winner_id, amount) 
    
    # 2. Table ko update karke ✔️✔️ lagana
    bot.edit_message_text("🏆 Result Final!\nArjun ✔️✔️\nPankaj\n500 Full", call.message.chat.id, call.message.message_id)

    # 3. Notification bhejna aur 2 second baad delete karna
    notify_msg = bot.send_message(call.message.chat.id, "✅ Balances updated successfully!")
    # Thread start karna taaki bot atke nahi aur 2 sec baad message delete ho jaye
    threading.Thread(target=auto_delete_message, args=(call.message.chat.id, notify_msg.message_id)).start()

    # 4. Live Pinned List ko Edit karke update karna
    update_live_list(call.message.chat.id, call.message.chat.title)

bot.polling(none_stop=True)
