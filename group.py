import os
import telebot
from telebot import types
import sqlite3
from datetime import datetime

# 🔹 Bot token from environment (Render se lega)
BOT_TOKEN = os.getenv("BOT_TOKEN")

# 🔹 Channel username (join check ke liye)
CHANNEL_USERNAME = "@Royalofficial143"

# 🔹 Create bot instance
bot = telebot.TeleBot(BOT_TOKEN)

# 🔹 Database setup
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        credits INTEGER DEFAULT 10
    )""")
    conn.commit()
    conn.close()

init_db()


# 🔹 Helper function: Get or create user
def get_user(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    data = c.fetchone()
    if not data:
        c.execute("INSERT INTO users (user_id, credits) VALUES (?, 10)", (user_id,))
        conn.commit()
        conn.close()
        return (user_id, 10)
    conn.close()
    return data


# 🔹 Update credits
def update_credits(user_id, amount):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()


# 🔹 Channel join check
def is_user_joined(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False


# 🔹 Start command
@bot.message_handler(commands=["start"])
def start(message):
    user = get_user(message.from_user.id)
    keyboard = types.InlineKeyboardMarkup()
    join_btn = types.InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")
    verify_btn = types.InlineKeyboardButton("🔍 Verify Join", callback_data="verify_join")
    keyboard.add(join_btn)
    keyboard.add(verify_btn)
    bot.reply_to(
        message,
        f"👋 Hello {message.from_user.first_name}!\n\n"
        "Before using the bot, please join our channel 👇",
        reply_markup=keyboard,
    )


# 🔹 Verify join
@bot.callback_query_handler(func=lambda call: call.data == "verify_join")
def verify_join(call):
    user_id = call.from_user.id
    if is_user_joined(user_id):
        bot.answer_callback_query(call.id, "✅ Verified! You can now use the bot.")
        bot.send_message(
            user_id,
            "🎉 Verification successful!\nYou can now use the bot.\n\nUse /search <group_name> to search group info.",
        )
    else:
        bot.answer_callback_query(call.id, "❌ You must join the channel first!", show_alert=True)


# 🔹 Search command
@bot.message_handler(commands=["search"])
def search_group(message):
    user_id = message.from_user.id
    user = get_user(user_id)

    # Check join
    if not is_user_joined(user_id):
        bot.reply_to(message, "⚠️ Please join the channel first using /start.")
        return

    # Check credits
    if user[1] < 5:
        bot.reply_to(message, "💰 You don’t have enough credits (need 5 per search). Contact admin to buy more.")
        return

    # Extract search term
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❗ Usage: /search <group_name>")
        return

    group_name = parts[1]
    update_credits(user_id, -5)
    bot.reply_to(
        message,
        f"🔎 Searching for group info related to: {group_name}\n"
        "⏳ Please wait...\n(This is demo mode — add your logic here)",
    )

    # 🔹 Here you can add your Telethon or API logic to get group info
    bot.send_message(
        user_id,
        f"✅ Demo result for: {group_name}\n"
        f"👑 Owner: @Rocky_2oo\n"
        f"📅 Created: {datetime.now().strftime('%Y-%m-%d')}\n"
        f"💰 5 credits used. Remaining: {user[1] - 5}",
    )


# 🔹 Admin add credits
@bot.message_handler(commands=["addcredits"])
def add_credits(message):
    if message.from_user.username != "Rocky_2oo":  # Only admin can add credits
        bot.reply_to(message, "⛔ You are not authorized to use this command.")
        return

    try:
        parts = message.text.split()
        user_id = int(parts[1])
        amount = int(parts[2])
        update_credits(user_id, amount)
        bot.reply_to(message, f"✅ Added {amount} credits to {user_id}")
    except:
        bot.reply_to(message, "❗ Usage: /addcredits <user_id> <amount>")


# 🔹 Run bot
print("🤖 Bot is running...")
bot.infinity_polling()
