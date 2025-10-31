#!/usr/bin/env python3
"""
Final Group Info Bot (Render / Termux ready)

Environment variables required:
  BOT_TOKEN            - BotFather token (string)
  API_ID               - my.telegram.org API ID (int)
  API_HASH             - my.telegram.org API HASH (string)
  TELETHON_SESSION     - Telethon StringSession (string)
  CHANNEL_USERNAME     - channel to require join (default @Royalofficial143)
  ADMIN_USERNAME       - admin username without @ (default rocky_2ooo)
  COST_PER_SEARCH      - integer (default 5)
  DEFAULT_CREDITS      - integer (default 10)

Requirements (requirements.txt):
  python-telegram-bot==13.15
  telethon==1.30.0
"""

import os
import logging
import sqlite3
import time
import csv
from html import escape
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import ChannelParticipantsAdmins, Channel
from telethon.errors.rpcerrorlist import RPCError


from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    ParseMode,
    Update,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)

# ---------------- ENV / CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID") or "0")
API_HASH = os.getenv("API_HASH") or ""
TELETHON_SESSION = os.getenv("TELETHON_SESSION") or ""
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@Royalofficial143")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "rocky_2ooo").lstrip("@")
DATABASE = os.getenv("DATABASE", "groupbot.db")

DEFAULT_CREDITS = int(os.getenv("DEFAULT_CREDITS", "10"))
COST_PER_SEARCH = int(os.getenv("COST_PER_SEARCH", "5"))
REFERRAL_REWARD = int(os.getenv("REFERRAL_REWARD", "10"))

# sanity checks
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is required")
if not API_ID or not API_HASH:
    raise RuntimeError("API_ID and API_HASH env vars are required")
if not TELETHON_SESSION:
    raise RuntimeError("TELETHON_SESSION env var is required (generate locally)")

# ---------------- logging ----------------
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- Telethon client ----------------
tele_client = TelegramClient(StringSession(TELETHON_SESSION), API_ID, API_HASH)

# ---------------- Database helpers ----------------
def init_db():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            credits INTEGER,
            created_at INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stats (
            key TEXT PRIMARY KEY,
            value INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_credits (
            username TEXT PRIMARY KEY,
            credits INTEGER DEFAULT 0
        )
        """
    )
    cur.execute("INSERT OR IGNORE INTO stats(key, value) VALUES ('total_searches', 0)")
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, first_name, credits, created_at FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"user_id": row[0], "username": row[1], "first_name": row[2], "credits": row[3], "created_at": row[4]}


def create_user_if_missing(user_id, username, first_name):
    u = get_user(user_id)
    if u:
        return u
    now = int(time.time())
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO users(user_id, username, first_name, credits, created_at) VALUES (?,?,?,?,?)",
        (user_id, username or "", first_name or "", DEFAULT_CREDITS, now),
    )
    conn.commit()
    conn.close()
    # apply pending credits if username present
    if username:
        apply_pending_credit_for_username(username, user_id)
    return get_user(user_id)


def apply_pending_credit_for_username(username, user_id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM pending_credits WHERE username=?", (username,))
    row = cur.fetchone()
    if row:
        credits = row[0]
        cur.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (credits, user_id))
        cur.execute("DELETE FROM pending_credits WHERE username=?", (username,))
        conn.commit()
    conn.close()


def add_credits_to_user_id(user_id, amount):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()


def add_pending_credits_for_username(username, amount):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO pending_credits(username, credits) VALUES (?,0)", (username,))
    cur.execute("UPDATE pending_credits SET credits = credits + ? WHERE username=?", (amount, username))
    conn.commit()
    conn.close()


def try_consume_credits(user_id, cost):
    user = get_user(user_id)
    if not user:
        return False, "User not found"
    if user["credits"] < cost:
        return False, f"Not enough credits. You have {user['credits']} credits."
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("UPDATE users SET credits = credits - ? WHERE user_id=?", (cost, user_id))
    conn.commit()
    conn.close()
    increment_stat("total_searches", 1)
    return True, None


def refund_credits(user_id, amount):
    add_credits_to_user_id(user_id, amount)


def increment_stat(key, amount=1):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO stats(key, value) VALUES (?, ?)", (key, 0))
    cur.execute("UPDATE stats SET value = value + ? WHERE key=?", (amount, key))
    conn.commit()
    conn.close()


def get_stat(key):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT value FROM stats WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def get_all_users():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, first_name, credits, created_at FROM users")
    rows = cur.fetchall()
    conn.close()
    return rows


# ---------------- Utility: normalize group input ----------------
import re

GROUP_LINK_RE = re.compile(r"(t\.me/|telegram\.me/)?@?([A-Za-z0-9_]+)")
INVITE_RE = re.compile(r"(https?://)?t\.me/joinchat/([A-Za-z0-9_-]+)")


def normalize_group_input(text):
    if not text:
        return None
    text = text.strip()
    try:
        if text.startswith("-100") or text.lstrip("-").isdigit():
            return int(text)
    except Exception:
        pass
    m = GROUP_LINK_RE.search(text)
    if m:
        return "@" + m.group(2)
    m2 = INVITE_RE.search(text)
    if m2:
        return text
    return text


# ---------------- Core: fetch group info via Telethon ----------------
def fetch_group_info(group_input):
    import asyncio

    # Ensure connection
    if not tele_client.is_connected():
        tele_client.connect()

    inp = normalize_group_input(group_input)

    # Run Telethon call safely in sync code
    try:
        entity = asyncio.get_event_loop().run_until_complete(
            tele_client.get_entity(inp)
        )
    except Exception as e:
        raise Exception(f"Could not resolve group: {e}")

    title = getattr(entity, "title", str(entity))
    gid = getattr(entity, "id", None)

    # Determine type
    if isinstance(entity, Channel):
        entity_type = "channel" if getattr(entity, "broadcast", False) else "supergroup"
    else:
        entity_type = "group"

    res = {
        "group": title,
        "id": gid,
        "type": entity_type,
        "member_count": None,
        "approx_date": None,
        "method": None,
        "owner": "Unknown",
        "admins": [],
        "note": None,
    }

    # Member count via GetFullChannel if possible
    try:
        from telethon.tl.functions.channels import GetFullChannelRequest

        if isinstance(entity, Channel):
            try:
                full = tele_client.loop.run_until_complete(tele_client(GetFullChannelRequest(channel=entity)))
                cnt = getattr(full.full_chat, "participants_count", None)
                res["member_count"] = cnt or getattr(entity, "participants_count", None)
            except Exception:
                res["member_count"] = getattr(entity, "participants_count", None)
        else:
            res["member_count"] = None
    except Exception:
        res["member_count"] = getattr(entity, "participants_count", None)

    # Oldest visible message
    try:
        msgs = asyncio.get_event_loop().run_until_complete(tele_client.iter_messages(entity, reverse=True, limit=1).__anext__())
        first = msgs
            res["approx_date"] = msgs.date.strftime("%Y-%m-%d %H:%M:%S")
            res["method"] = "Oldest Visible Message"
            res["note"] = "Based on first visible message (may not be original creation date)."
    except Exception:
        pass

    # Admins + Owner
    try:
        admins = []
        async def fetch_admins():
            async for admin in tele_client.iter_participants(entity, filter=ChannelParticipantsAdmins):
                name = " ".join(filter(None, [admin.first_name, admin.last_name])) or admin.username or f"id{admin.id}"
                admins.append(name)

        tele_client.loop.run_until_complete(fetch_admins())

        res["admins"] = admins
        if admins:
            res["owner"] = admins[0]
    except Exception:
        pass

    # Fallback: Estimate by group ID range
    if not res["approx_date"]:
        try:
            gid_abs = abs(int(res["id"])) if res["id"] else None
            if gid_abs:
                if gid_abs < 10**11:
                    est = "2015-2016"
                elif gid_abs < 10**12:
                    est = "2017-2018"
                elif gid_abs < 10**13:
                    est = "2019-2021"
                else:
                    est = "2022-2025"
                res["approx_date"] = f"~{est}"
                res["method"] = "Group ID Estimate"
                res["note"] = "Heuristic estimate (approx)."
            else:
                res["approx_date"] = "Unknown"
                res["method"] = "Unknown"
        except Exception:
            res["approx_date"] = "Unknown"
            res["method"] = "Unknown"

    return res


# ---------------- Bot helpers ----------------
def user_in_channel(bot, user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        status = getattr(member, "status", "")
        if str(status).lower() in ("member", "administrator", "creator"):
            return True
        return False
    except Exception as e:
        logger.info("get_chat_member failed: %s", e)
        return False


def format_info_text(info: dict):
    admins = ", ".join(info.get("admins") or []) or "None"
    text = (
        f"<b>Title:</b> {escape(info.get('group') or 'Unknown')}\n"
        f"<b>ID:</b> <code>{info.get('id')}</code>\n"
        f"<b>Type:</b> {escape(info.get('type') or 'Unknown')}\n"
        f"<b>Members:</b> {info.get('member_count') or 'Unknown'}\n"
        f"<b>Created (approx):</b> {escape(info.get('approx_date') or 'Unknown')} ({escape(info.get('method') or '')})\n"
        f"<b>Owner (best-effort):</b> {escape(info.get('owner') or 'Unknown')}\n"
        f"<b>Admins:</b> {escape(admins)}\n"
    )
    if info.get("note"):
        text += f"\n<i>{escape(info.get('note'))}</i>\n"
    return text


# ---------------- Handlers ----------------
def start_handler(update: Update, context: CallbackContext):
    user = update.effective_user
    args = context.args
    ref = None
    if args:
        first = args[0]
        if first.startswith("ref"):
            try:
                ref = int(first[3:])
            except Exception:
                ref = None

    create_user_if_missing(user.id, user.username or "", user.first_name or "")

    # apply referral reward if present (referrer must exist)
    if ref and ref != user.id:
        ref_rec = get_user(ref)
        if ref_rec:
            add_credits_to_user_id(ref, REFERRAL_REWARD)

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Join Channel ✅", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("Verify Join", callback_data="verify_join")],
        ]
    )
    update.message.reply_text(
        "👋 Hi! To use this bot you must join our channel first.\n\n"
        "After joining, press Verify. You get default credits when first starting.",
        reply_markup=kb,
    )


def verify_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    query.answer()
    if user_in_channel(context.bot, user.id):
        create_user_if_missing(user.id, user.username or "", user.first_name or "")
        query.message.reply_text("✅ Verified! You can now use inline queries or /check <group_link>.")
    else:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Retry Verify", callback_data="verify_join")]])
        query.message.reply_text(f"❌ Still not a member of {CHANNEL_USERNAME}. Please join and retry.", reply_markup=kb)


def check_handler(update: Update, context: CallbackContext):
    user = update.effective_user
    create_user_if_missing(user.id, user.username or "", user.first_name or "")

    if len(context.args) == 0:
        update.message.reply_text("Usage: /check <group_link_or_username_or_id>")
        return

    if not user_in_channel(context.bot, user.id):
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Verify Join", callback_data="verify_join")]])
        update.message.reply_text(f"❌ You must join {CHANNEL_USERNAME} first.", reply_markup=kb)
        return

    ok, err = try_consume_credits(user.id, COST_PER_SEARCH)
    if not ok:
        update.message.reply_text(err + f"\nContact admin to add credits → @{ADMIN_USERNAME}")
        return

    query_text = context.args[0]
    update.message.reply_text("🔍 Fetching group info... please wait a few seconds.")
    try:
        info = fetch_group_info(query_text)
        update.message.reply_text(format_info_text(info), parse_mode=ParseMode.HTML)
    except Exception as e:
        refund_credits(user.id, COST_PER_SEARCH)
        update.message.reply_text(f"⚠️ Error fetching info: {e}\nYour credit has been refunded.")


def inline_query_handler(update: Update, context: CallbackContext):
    inline_q = update.inline_query
    user = inline_q.from_user
    query_text = inline_q.query.strip()
    create_user_if_missing(user.id, user.username or "", user.first_name or "")

    if not query_text:
        hint = "Type a group link or username: @groupname or https://t.me/groupname"
        res = InlineQueryResultArticle(
            id="hint",
            title="Group Info Finder",
            input_message_content=InputTextMessageContent(hint),
            description=hint,
        )
        update.inline_query.answer([res], cache_time=10)
        return

    if not user_in_channel(context.bot, user.id):
        join_msg = f"You must join {CHANNEL_USERNAME} to use this bot. Open bot chat to verify."
        res = InlineQueryResultArticle(
            id="must_join",
            title="Join required",
            input_message_content=InputTextMessageContent(join_msg),
            description=f"Join {CHANNEL_USERNAME} and verify in bot chat.",
        )
        update.inline_query.answer([res], cache_time=5, switch_pm_text=f"Join {CHANNEL_USERNAME} to use", switch_pm_parameter="verify")
        return

    ok, err = try_consume_credits(user.id, COST_PER_SEARCH)
    if not ok:
        no_credits_text = err + f"\nContact admin to add credits → @{ADMIN_USERNAME}"
        res = InlineQueryResultArticle(
            id="no_credits",
            title="No credits",
            input_message_content=InputTextMessageContent(no_credits_text),
            description="You don't have enough credits.",
        )
        update.inline_query.answer([res], cache_time=5)
        return

    try:
        info = fetch_group_info(query_text)
        text = format_info_text(info)
        res = InlineQueryResultArticle(
            id="res_" + str(int(time.time())),
            title=f"{info.get('group')} — {info.get('approx_date')}",
            input_message_content=InputTextMessageContent(text, parse_mode="HTML"),
            description=f"Created: {info.get('approx_date')}",
        )
        update.inline_query.answer([res], cache_time=5)
    except Exception as e:
        refund_credits(user.id, COST_PER_SEARCH)
        err_text = f"Error fetching info: {str(e)} (credits refunded)"
        res = InlineQueryResultArticle(
            id="err",
            title="Error",
            input_message_content=InputTextMessageContent(err_text),
            description="Could not fetch group info.",
        )
        update.inline_query.answer([res], cache_time=5)


# Admin commands
def addcredit_command(update: Update, context: CallbackContext):
    user = update.effective_user
    if user.username != ADMIN_USERNAME:
        update.message.reply_text("Not authorized.")
        return
    if len(context.args) < 2:
        update.message.reply_text("Usage: /addcredit @username amount OR /addcredit user_id amount")
        return
    target = context.args[0]
    try:
        amount = int(context.args[1])
    except Exception:
        update.message.reply_text("Amount must be integer.")
        return

    if target.startswith("@"):
        uname = target[1:]
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE username=?", (uname,))
        row = cur.fetchone()
        conn.close()
        if row:
            tid = row[0]
            add_credits_to_user_id(tid, amount)
            update.message.reply_text(f"✅ Added {amount} credits to @{uname} (id {tid}).")
        else:
            add_pending_credits_for_username(uname, amount)
            update.message.reply_text(f"✅ @{uname} not in DB. Pending {amount} credits will be applied when they start bot.")
        return

    try:
        tid = int(target)
    except Exception:
        update.message.reply_text("Invalid target. Use @username or numeric id.")
        return
    rec = get_user(tid)
    if not rec:
        update.message.reply_text("User id not found in DB.")
        return
    add_credits_to_user_id(tid, amount)
    update.message.reply_text(f"✅ Added {amount} credits to id {tid}.")

def balance_command(update: Update, context: CallbackContext):
    """Show user’s current credits"""
    user = update.effective_user
    record = get_user(user.id)
    if not record:
        create_user_if_missing(user.id, user.username or "", user.first_name or "")
        record = get_user(user.id)
    update.message.reply_text(
        f"💰 You currently have <b>{record['credits']}</b> credits.",
        parse_mode=ParseMode.HTML,
    )

def usercredits_command(update: Update, context: CallbackContext):
    user = update.effective_user
    if user.username != ADMIN_USERNAME:
        update.message.reply_text("Not authorized.")
        return
    if len(context.args) == 0:
        update.message.reply_text("Usage: /usercredits @username_or_id")
        return
    target = context.args[0]
    if target.startswith("@"):
        uname = target[1:]
        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute("SELECT user_id, credits FROM users WHERE username=?", (uname,))
        row = cur.fetchone()
        conn.close()
        if not row:
            update.message.reply_text("User not found.")
            return
        update.message.reply_text(f"@{uname} (id {row[0]}) has {row[1]} credits.")
    else:
        try:
            tid = int(target)
            rec = get_user(tid)
            if not rec:
                update.message_reply_text("User not found.")
                return
            update.message.reply_text(f"id {tid} has {rec['credits']} credits.")
        except Exception:
            update.message_reply_text("Invalid id.")


def stats_command(update: Update, context: CallbackContext):
    user = update.effective_user
    if user.username != ADMIN_USERNAME:
        update.message_reply_text("Not authorized.")
        return
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    conn.close()
    total_searches = get_stat("total_searches")
    update.message.reply_text(f"Users: {total_users}\nTotal searches: {total_searches}")


def export_users_command(update: Update, context: CallbackContext):
    user = update.effective_user
    if user.username != ADMIN_USERNAME:
        update.message_reply_text("Not authorized.")
        return
    rows = get_all_users()
    fname = "users_export.csv"
    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "username", "first_name", "credits", "created_at"])
        for r in rows:
            writer.writerow(r)
    update.message_reply_text(f"✅ Exported {len(rows)} users to {fname}")


def error_handler(update: object, context: CallbackContext):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)


# ---------------- Main ----------------
def main():
    init_db()
    try:
        if not tele_client.is_connected():
            tele_client.connect()
    except Exception as e:
        logger.warning("Telethon connect warning: %s", e)

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_handler))
    dp.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify_join$"))
    dp.add_handler(CommandHandler("check", check_handler, pass_args=True))
    dp.add_handler(CommandHandler("balance", balance_command))  # ✅ added
    dp.add_handler(InlineQueryHandler(inline_query_handler))
    dp.add_handler(CommandHandler("addcredit", addcredit_command, pass_args=True))
    dp.add_handler(CommandHandler("usercredits", usercredits_command, pass_args=True))
    dp.add_handler(CommandHandler("stats", stats_command))
    dp.add_handler(CommandHandler("export_users", export_users_command))
    dp.add_error_handler(error_handler)

    logger.info("Bot starting (polling)...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()