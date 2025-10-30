import os
import logging
import sqlite3
import requests
import time
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ParseMode
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
    CallbackContext
)

# ====== CONFIG ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = "@Royalofficial143"
ADMIN_USERNAME = "Rocky_2oo"
COST_PER_SEARCH = 5
CREDIT_PER_REF = 10
DATABASE = "grupinf.db"
# ====================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== Database Setup =====
def init_db():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        username TEXT,
        name TEXT,
        credits INTEGER DEFAULT 10,
        referred_by INTEGER,
        created_at INTEGER
    )""")
    conn.commit()
    conn.close()

def get_user(chat_id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT chat_id, username, name, credits, referred_by FROM users WHERE chat_id=?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"chat_id": row[0], "username": row[1], "name": row[2], "credits": row[3], "referred_by": row[4]}
    return None

def create_user(chat_id, username, name, ref=None):
    user = get_user(chat_id)
    if user:
        return user
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (chat_id, username, name, 10, ref, int(time.time())))
    conn.commit()
    conn.close()
    if ref:
        add_credits(ref, CREDIT_PER_REF)
    return get_user(chat_id)

def add_credits(chat_id, amount):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET credits = credits + ? WHERE chat_id=?", (amount, chat_id))
    conn.commit()
    conn.close()

def deduct_credits(chat_id, amount):
    user = get_user(chat_id)
    if not user or user["credits"] < amount:
        return False
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET credits = credits - ? WHERE chat_id=?", (amount, chat_id))
    conn.commit()
    conn.close()
    return True

# ===== Bot Logic =====
def is_joined_channel(bot, user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

def start(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user
    args = context.args
    ref = None

    if args:
        try:
            if args[0].startswith("ref"):
                ref = int(args[0][3:])
        except:
            pass

    user_rec = create_user(chat.id, user.username or "", user.full_name or "", ref)

    if not is_joined_channel(context.bot, chat.id):
        join_button = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Join Channel ✅", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")]]
        )
        update.message.reply_text(
            f"⚠️ Please join our channel {CHANNEL_USERNAME} first to use the bot.",
            reply_markup=join_button,
        )
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Search Group Info", callback_data="search")],
        [InlineKeyboardButton("💰 My Credits", callback_data="credits")],
        [InlineKeyboardButton("🎁 Referral Link", callback_data="referral")]
    ])

    update.message.reply_text(
        f"👋 Hello {user.first_name}!\nWelcome to GrupInf Bot.\n\nUse the menu below:",
        reply_markup=keyboard
    )

def button(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat.id
    query.answer()

    if not is_joined_channel(context.bot, chat_id):
        query.message.reply_text("⚠️ Join our channel first: " + CHANNEL_USERNAME)
        return

    if query.data == "search":
        query.message.reply_text("🔎 Send group @username or invite link to get info (costs 5 credits).")
        context.user_data["waiting_for_search"] = True

    elif query.data == "credits":
        user_data = get_user(chat_id)
        query.message.reply_text(f"💳 Your Credits: {user_data['credits']}")

    elif query.data == "referral":
        ref_link = f"https://t.me/{context.bot.username}?start=ref{chat_id}"
        query.message.reply_text(
            f"🎁 Share your referral link:\n{ref_link}\n\nEach new user gives you {CREDIT_PER_REF} credits!"
        )

def handle_text(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if context.user_data.get("waiting_for_search"):
        user = get_user(chat_id)
        if not deduct_credits(chat_id, COST_PER_SEARCH):
            update.message.reply_text("❌ Not enough credits! Contact admin for more.")
            return

        update.message.reply_text(f"🔍 Searching info for: {text}\nPlease wait...")
        time.sleep(2)

        # Dummy result (you can later replace this with real logic)
        result = f"📊 Group Info for {text}\n• Owner: Unknown\n• Admins: 3\n• Created: Unknown"
        update.message.reply_text(result)

        context.user_data["waiting_for_search"] = False

def addcredit(update: Update, context: CallbackContext):
    user = update.effective_user
    if user.username != ADMIN_USERNAME:
        update.message.reply_text("❌ Only admin can use this command.")
        return
    try:
        target = int(context.args[0])
        amount = int(context.args[1])
        add_credits(target, amount)
        update.message.reply_text(f"✅ Added {amount} credits to {target}.")
    except:
        update.message.reply_text("Usage: /addcredit <chat_id> <amount>")

def main():
    init_db()
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("addcredit", addcredit))
    dp.add_handler(CallbackQueryHandler(button))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()