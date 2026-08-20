import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import re
from datetime import datetime, timedelta
import pytz
import os

# ========================================================
# CONFIGURATION
# ========================================================
BOT_TOKEN = '8763676531:AAGSTFXVVEsWL08Wx97lGIlst0leBxxsoP0'
ADMIN_ID = 8549494164

CHANNEL_ID = '@venila_project'  # আপনার চ্যানেলের ইউজারনেম দিন
GROUP_ID = '@venila_group'      # আপনার গ্রুপের ইউজারনেম দিন

# Country to TXT File Mapping (Exact Requirement)
SERVER_FILES = {
    'bd': ('Bangladesh', 'BD_Guest.txt'),
    'in': ('India', 'Ind_Guest.txt'),
    'pk': ('Pakistan', 'PK_Guest.txt'),
    'np': ('Nepal', 'NP_Guest.txt')
}

# TZ = Asia/Dhaka as default
timezone = pytz.timezone("Asia/Dhaka")

bot = telebot.TeleBot(BOT_TOKEN)

# ========================================================
# DATABASE INITIALIZATION
# ========================================================
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        chat_id INTEGER PRIMARY KEY,
                        status TEXT DEFAULT 'ACTIVE',
                        total_claims INTEGER DEFAULT 0
                    )''')
                    
    cursor.execute('''CREATE TABLE IF NOT EXISTS claims (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER,
                        server TEXT,
                        search_uid TEXT,
                        game_name TEXT,
                        main_uid TEXT,
                        main_password TEXT,
                        claim_timestamp REAL,
                        date TEXT,
                        time TEXT
                    )''')
    conn.commit()
    conn.close()

init_db()

# Database Helper Functions
def add_or_get_user(chat_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT status, total_claims FROM users WHERE chat_id=?", (chat_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (chat_id, status, total_claims) VALUES (?, 'ACTIVE', 0)", (chat_id,))
        conn.commit()
        user = ('ACTIVE', 0)
    conn.close()
    return user

def is_banned(chat_id):
    user = add_or_get_user(chat_id)
    return user[0] == 'BANNED'

# ========================================================
# TXT PARSER & ACCOUNT STOCK SYSTEM
# ========================================================
def get_parsed_accounts(file_name):
    accounts = []
    if not os.path.exists(file_name):
        return accounts
        
    with open(file_name, 'r', encoding='utf-8') as f:
        content = f.read()
    
    blocks = content.split(',,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,')
    
    for block in blocks:
        if not block.strip():
            continue
            
        try:
            chak_uid = re.search(r'Chak Uid\s*:\s*(.*)', block, re.IGNORECASE).group(1).strip()
            game_name = re.search(r'Game name\s*:\s*(.*)', block, re.IGNORECASE).group(1).strip()
            main_uid = re.search(r'Main UID\s*:\s*(.*)', block, re.IGNORECASE).group(1).strip()
            password = re.search(r'Main Password\s*:\s*(.*)', block, re.IGNORECASE).group(1).strip()
            
            accounts.append({
                'search_uid': chak_uid,  
                'game_name': game_name,
                'main_uid': main_uid,
                'main_password': password
            })
        except AttributeError:
            pass 
            
    return accounts

def get_available_stock():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    stocks = {}
    total_available = 0
    for server_key, (server_name, file_name) in SERVER_FILES.items():
        parsed_accs = get_parsed_accounts(file_name)
        
        cursor.execute("SELECT search_uid FROM claims WHERE server=?", (server_name,))
        claimed_uids = [row[0] for row in cursor.fetchall()]
        
        available = len([acc for acc in parsed_accs if acc['search_uid'] not in claimed_uids])
        stocks[server_name] = available
        total_available += available
        
    conn.close()
    return stocks, total_available

def claim_unused_account(server_name, file_name, chat_id):
    parsed_accs = get_parsed_accounts(file_name)
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT search_uid FROM claims WHERE server=?", (server_name,))
    claimed_uids = [row[0] for row in cursor.fetchall()]
    
    unused_account = None
    for acc in parsed_accs:
        if acc['search_uid'] not in claimed_uids:
            unused_account = acc
            break
            
    if unused_account:
        now = datetime.now(timezone)
        d_str = now.strftime('%d/%m/%Y')
        t_str = now.strftime('%I:%M:%S %p')
        timestamp = now.timestamp()
        
        cursor.execute("""
            INSERT INTO claims (chat_id, server, search_uid, game_name, main_uid, main_password, claim_timestamp, date, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (chat_id, server_name, unused_account['search_uid'], unused_account['game_name'], unused_account['main_uid'], unused_account['main_password'], timestamp, d_str, t_str))
        
        cursor.execute("UPDATE users SET total_claims = total_claims + 1 WHERE chat_id = ?", (chat_id,))
        conn.commit()
    conn.close()
    return unused_account

def get_cooldown_remaining(chat_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT claim_timestamp FROM claims WHERE chat_id=? ORDER BY id DESC LIMIT 1", (chat_id,))
    res = cursor.fetchone()
    conn.close()
    
    if res:
        last_time = res[0]
        now = datetime.now(timezone).timestamp()
        passed_time = now - last_time
        if passed_time < 300: 
            remaining = int(300 - passed_time)
            mins, secs = divmod(remaining, 60)
            return f"{mins:02}:{secs:02}"
    return None

# ========================================================
# JOIN VERIFICATION & WELCOME
# ========================================================
def check_join(user_id):
    try:
        status_ch = bot.get_chat_member(CHANNEL_ID, user_id).status
        status_gr = bot.get_chat_member(GROUP_ID, user_id).status
        valid_status = ['member', 'creator', 'administrator']
        if status_ch in valid_status and status_gr in valid_status:
            return True
        return False
    except Exception:
        return False

@bot.message_handler(commands=['start'])
def start_handler(message):
    chat_id = message.chat.id
    add_or_get_user(chat_id)

    if is_banned(chat_id):
        bot.send_message(chat_id, "🔴 <b>Banned</b>\n\nদুঃখিত, আপনাকে এই বটটি ব্যবহার করা থেকে সাময়িক বা স্থায়ীভাবে বরখাস্ত করা হয়েছে।", parse_mode='html')
        return

    text = (
        "✨ <b>স্বাগতম আমাদের Guest Account Bot-এ!</b>\n\n"
        "সবচেয়ে সহজে এবং দ্রুত প্রিমিয়াম সার্ভার ভিত্তিক\n"
        "গেস্ট অ্যাকাউন্টগুলো এখান থেকে ক্লাইম করুন।\n"
        "এগিয়ে যাওয়ার আগে নিচে দেওয়া চ্যানেল এবং\n"
        "গ্রুপে যুক্ত হওয়া বাধ্যতামূলক।\n\n"
        "✅ <i>দয়া করে যুক্ত হওয়ার পর 'Continue' চাপুন।</i>"
    )
    
    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton("📢 Channel", url=f"https://t.me/{CHANNEL_ID.replace('@','')}")
    btn2 = InlineKeyboardButton("👥 Group", url=f"https://t.me/{GROUP_ID.replace('@','')}")
    btn3 = InlineKeyboardButton("✅ Continue", callback_data="verify_join")
    markup.row(btn1, btn2)
    markup.row(btn3)
    
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode='html')

@bot.callback_query_handler(func=lambda call: call.data == "verify_join")
def verify_join_call(call):
    chat_id = call.message.chat.id
    if check_join(chat_id):
        show_main_menu(chat_id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "দয়া করে উপরের দুটি Channel/Group-এ আগে Join করুন!", show_alert=True)


# ========================================================
# CLEANUP HANDLER: DUEL MESSAGE JUNK FIXER
# ========================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("clean_menu_"))
def clean_and_return_main_menu(call):
    chat_id = call.message.chat.id
    # ডিলিট করছে ওই উপরের মেসেজটি (Message 1) যা হিস্টোরি তৈরি করতো
    try:
        old_msg_id = int(call.data.split('_')[2])
        bot.delete_message(chat_id, old_msg_id)
    except Exception:
        pass
    # এরপর নিজের Message 2 টিকে মেইন মেন্যুতে কনভার্ট করছে 
    show_main_menu(chat_id, call.message.message_id)


# ========================================================
# MAIN MENU
# ========================================================
def show_main_menu(chat_id, message_id=None):
    if is_banned(chat_id): return
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🌍 Select Your Region", callback_data="select_region"),
        InlineKeyboardButton("🕘 History", callback_data="history_menu")
    )
    
    if chat_id == ADMIN_ID:
        markup.row(InlineKeyboardButton("⚙️ Admin", callback_data="admin_panel"))

    text = "🔥 <b>Main Menu</b>\n\nদয়া করে আপনার পছন্দসই কাজ বেছে নিন:"
    
    if message_id:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup, parse_mode='html')
        except:
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode='html')
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode='html')

@bot.callback_query_handler(func=lambda call: call.data == "main_menu")
def return_main_menu(call):
    show_main_menu(call.message.chat.id, call.message.message_id)


# ========================================================
# SELECT YOUR REGION (4 SERVER COMPACT)
# ========================================================
@bot.callback_query_handler(func=lambda call: call.data == "select_region")
def region_selector(call):
    chat_id = call.message.chat.id
    if is_banned(chat_id): return
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🇧🇩 Bangladesh", callback_data="server_bd"),
        InlineKeyboardButton("🇮🇳 India", callback_data="server_in")
    )
    markup.row(
        InlineKeyboardButton("🇵🇰 Pakistan", callback_data="server_pk"),
        InlineKeyboardButton("🇳🇵 Nepal", callback_data="server_np")
    )
    markup.row(InlineKeyboardButton("🔙 Back", callback_data="main_menu"))
    
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text="🌍 <b>আপনার পছন্দমতো রিজিয়ন সার্ভার নির্বাচন করুন:</b>", reply_markup=markup, parse_mode='html')

@bot.callback_query_handler(func=lambda call: call.data.startswith("server_"))
def show_claim_page(call):
    chat_id = call.message.chat.id
    if is_banned(chat_id): return
    
    server_code = call.data.split('_')[1]
    server_name = SERVER_FILES[server_code][0]
    
    markup = InlineKeyboardMarkup()
    cooldown = get_cooldown_remaining(chat_id)
    
    if cooldown:
        markup.row(InlineKeyboardButton(f"⏳ {cooldown} (Please Wait)", callback_data="cd_alert"))
    else:
        markup.row(InlineKeyboardButton("🎁 Claim Your Guest Account", callback_data=f"claim_{server_code}"))
        
    markup.row(InlineKeyboardButton("🔙 Back to Region", callback_data="select_region"))

    text = f"🌐 <b>Server:</b> {server_name}\n\nস্টক চেক করে ক্লাইম করুন!"
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                          text=text, reply_markup=markup, parse_mode='html')


@bot.callback_query_handler(func=lambda call: call.data == "cd_alert")
def cd_alert(call):
    rem = get_cooldown_remaining(call.message.chat.id)
    if rem:
        bot.answer_callback_query(call.id, f"অনুগ্রহ করে অপেক্ষা করুন। আরো {rem} মিনিট বাকি।", show_alert=True)
    else:
        show_claim_page(call) 


# ========================================================
# ACCOUNT CLAIM LOGIC & RESULT MESSAGE (SEPARATE MSGS)
# ========================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("claim_"))
def process_claim(call):
    chat_id = call.message.chat.id
    if is_banned(chat_id): return
    
    server_code = call.data.split('_')[1]
    server_name, file_name = SERVER_FILES[server_code]
    
    cooldown = get_cooldown_remaining(chat_id)
    if cooldown:
        bot.answer_callback_query(call.id, "Cooldown Active! You can't claim yet.", show_alert=True)
        return
        
    acc = claim_unused_account(server_name, file_name, chat_id)
    
    # [আপডেট]: Out of stock মেসেজও এখন চ্যাটে ঝুলে থাকবে না, ডাইরেক্ট এডিট হবে!
    if not acc:
        bot.answer_callback_query(call.id, "দুঃখিত, বর্তমানে এই সার্ভারের কোনো Guest Account নেই।", show_alert=True)
        out_txt = f"🚫 <b>{server_name} Server Out of Stock.</b>\n\nদুঃখিত, বর্তমানে এই সার্ভারের কোনো আনইউজড Guest Account নেই।"
        mk_out = InlineKeyboardMarkup()
        mk_out.row(InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu"))
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=out_txt, reply_markup=mk_out, parse_mode='html')
        return
        
    bot.delete_message(chat_id, call.message.message_id) 
    
    now = datetime.now(timezone)
    
    msg_1_txt = (
        "🎁 <b>Guest Account Success!</b>\n\n"
        f"🌍 Server: {server_name}\n\n"
        f"🎮 Game Name: {acc['game_name']}\n\n"
        f"🔎 Search UID: <code>{acc['search_uid']}</code>\n\n"
        f"📅 Date: {now.strftime('%d/%m/%Y')}\n"
        f"⏰ Time: {now.strftime('%I:%M:%S %p')}"
    )
    
    msg_2_txt = (
        "🔑 <b>Account Credentials:</b>\n\n"
        f"🔢 Main UID: <code>{acc['main_uid']}</code>\n\n"
        f"🔐 Main Password: <code>{acc['main_password']}</code>"
    )
    
    # 1. প্রথম মেসেজটি সেন্ড করা হলো এবং সেটার আইডি ট্র্যাক (সেভ) করে রাখা হলো।
    msg_1_obj = bot.send_message(chat_id, msg_1_txt, parse_mode='html')
    
    markup = InlineKeyboardMarkup()
    
    # 2. মেন্যু বাটনে প্রথম মেসেজটার ID যোগ করে দেয়া হলো, যাতে ক্লিক করলেই সেটা অটো ডিলিট হয়ে যায়। 
    markup.row(InlineKeyboardButton("🔙 Menu", callback_data=f"clean_menu_{msg_1_obj.message_id}"))
    
    bot.send_message(chat_id, msg_2_txt, reply_markup=markup, parse_mode='html')


# ========================================================
# USER SPECIFIC HISTORY
# ========================================================
@bot.callback_query_handler(func=lambda call: call.data == "history_menu")
def display_history(call):
    chat_id = call.message.chat.id
    if is_banned(chat_id): return
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT server, game_name, search_uid, main_uid, main_password, date, time FROM claims WHERE chat_id=? ORDER BY id DESC LIMIT 5", (chat_id,))
    histories = cursor.fetchall()
    conn.close()
    
    if not histories:
        bot.answer_callback_query(call.id, "আপনার কোনো History নেই।", show_alert=True)
        return
        
    text = "🕘 <b>Your Last 5 Claimed Accounts History:</b>\n\n"
    for i, h in enumerate(histories, start=1):
        text += (f"<b>#{i} | Server:</b> {h[0]}\n"
                 f"🎮 <b>Name:</b> {h[1]}\n"
                 f"🔎 <b>S-UID:</b> <code>{h[2]}</code>\n"
                 f"🔢 <b>M-UID:</b> <code>{h[3]}</code>\n"
                 f"🔐 <b>Pass:</b> <code>{h[4]}</code>\n"
                 f"🕒 {h[5]} • {h[6]}\n"
                 "---------------------------\n")
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
    bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode='html')


# ========================================================
# ADMIN PANEL (PROTECTED)
# ========================================================
@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def admin_panel(call):
    if call.message.chat.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⚠️ Access Denied", show_alert=True)
        return
        
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("👥 User Status", callback_data="admin_user_status"))
    markup.row(InlineKeyboardButton("🎁 Guest Account Status", callback_data="admin_account_status"))
    markup.row(InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
    
    bot.edit_message_text(chat_id=ADMIN_ID, message_id=call.message.message_id, text="⚙️ <b>ADMIN DASHBOARD</b>\n\nআপনি কী করতে চান তা নির্বাচন করুন:", reply_markup=markup, parse_mode='html')

# ==================== STOCK CHECK ====================
@bot.callback_query_handler(func=lambda call: call.data == "admin_account_status")
def admin_account_status(call):
    if call.message.chat.id != ADMIN_ID: return
    
    stocks, total = get_available_stock()
    
    bd_count = f"{stocks['Bangladesh']} Accounts" if stocks['Bangladesh'] > 0 else "Out of Stock"
    in_count = f"{stocks['India']} Accounts" if stocks['India'] > 0 else "Out of Stock"
    pk_count = f"{stocks['Pakistan']} Accounts" if stocks['Pakistan'] > 0 else "Out of Stock"
    np_count = f"{stocks['Nepal']} Accounts" if stocks['Nepal'] > 0 else "Out of Stock"
    
    text = (
        "🎁 <b>GUEST ACCOUNT STOCK DETAILS</b>\n\n"
        f"🇧🇩 Bangladesh — {bd_count}\n"
        f"🇮🇳 India — {in_count}\n"
        f"🇵🇰 Pakistan — {pk_count}\n"
        f"🇳🇵 Nepal — {np_count}\n\n"
        f"📊 <b>Total Available</b> — {total} Accounts"
    )
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🔙 Back", callback_data="admin_panel"))
    bot.edit_message_text(chat_id=ADMIN_ID, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode='html')

# ==================== USER MANAGEMENT ====================
@bot.callback_query_handler(func=lambda call: call.data == "admin_user_status")
def admin_user_list(call):
    if call.message.chat.id != ADMIN_ID: return
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT chat_id, total_claims, status FROM users ORDER BY total_claims DESC LIMIT 20")
    top_users = cursor.fetchall()
    conn.close()
    
    text = f"👥 <b>Total Users:</b> {total_users}\n\n(Showing top latest users, Ban/Unban via Panel Below)\n\n"
    
    markup = InlineKeyboardMarkup()
    for i, u in enumerate(top_users, start=1):
        uid = u[0]
        c_claims = u[1]
        c_stat = u[2]
        
        status_dot = "🟢 ACTIVE" if c_stat == 'ACTIVE' else "🔴 BANNED"
        btn_action = "BAN" if c_stat == 'ACTIVE' else "UNBAN"
        call_code = f"user_{btn_action}_{uid}"
        
        display_text = f"{i:02} | {uid} | {c_claims} Cl. | {status_dot}"
        text += display_text + "\n"
        
        markup.add(InlineKeyboardButton(f"Tap here to {btn_action} => {uid}", callback_data=call_code))

    markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel"))
    bot.edit_message_text(chat_id=ADMIN_ID, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode='html')

@bot.callback_query_handler(func=lambda call: call.data.startswith("user_"))
def handle_ban_unban(call):
    if call.message.chat.id != ADMIN_ID: return
    action = call.data.split('_')[1]
    targ_id = int(call.data.split('_')[2])
    
    new_stat = 'BANNED' if action == 'BAN' else 'ACTIVE'
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status=? WHERE chat_id=?", (new_stat, targ_id))
    conn.commit()
    conn.close()
    
    bot.answer_callback_query(call.id, f"User {targ_id} updated to {new_stat}", show_alert=False)
    admin_user_list(call)


# ========================================================
# TEXT AUTO DELETION MANAGER
# ========================================================
@bot.message_handler(func=lambda message: True)
def delete_all_text(message):
    try:
        if not message.text.startswith('/start'):
            bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except:
        pass

# ========================================================
# POLLING 
# ========================================================
print("Bot is successfully running... [Version 4.0 / Fully Clean Auto UI Cleanup Mode]")
bot.infinity_polling()