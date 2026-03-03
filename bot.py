"""
Telegram Bot — Join Request + Admin Approval + Video Content
=============================================================
Railway env vars:
  BOT_TOKEN, ADMIN_ID, CHANNEL_ID, CHANNEL_LINK,
  PAYMENT_LINK, VIDEO_1_ID, VIDEO_2_ID, EXTRA_VIDEO_IDS
"""
import asyncio
import logging
import os
from urllib.parse import quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── ENV VARS ──────────────────────────────────────────────────────────────────
BOT_TOKEN       = os.environ["BOT_TOKEN"]
ADMIN_ID        = int(os.environ["ADMIN_ID"])
CHANNEL_ID      = int(os.environ["CHANNEL_ID"])
CHANNEL_LINK    = os.environ.get("CHANNEL_LINK", "https://t.me/+Xb2fi4Gr00c3MTdl")
PAYMENT_LINK    = os.environ.get("PAYMENT_LINK", "https://t.me/your_payment_bot")
VIDEO_1_ID      = os.environ.get("VIDEO_1_ID", "")
VIDEO_2_ID      = os.environ.get("VIDEO_2_ID", "")
EXTRA_VIDEO_IDS = os.environ.get("EXTRA_VIDEO_IDS", "").split(",")

VIDEO_DELETE_DELAY = 30    # 30 seconds — videos auto delete
CHAT_DELETE_DELAY  = 86400  # 1 day (24 hours) — full chat wipe both sides

BOT_LINK = "https://t.me/Xetuu18bot?start=ref"

# ── STATE ─────────────────────────────────────────────────────────────────────
user_states: dict[int, dict] = {}

def get_state(uid: int) -> dict:
    if uid not in user_states:
        user_states[uid] = {"messages": [], "phase": "waiting", "more_shares": 0}
    return user_states[uid]

def share_url() -> str:
    return f"https://t.me/share/url?url={quote(CHANNEL_LINK)}&text={quote('join our exclusive group')}"

# ── HELPERS ───────────────────────────────────────────────────────────────────
async def schedule_delete(bot, chat_id: int, message_ids: list, delay: int):
    await asyncio.sleep(delay)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass

# ── PROMO MESSAGE (no buttons — waiting state) ────────────────────────────────
PROMO_TEXT = (
    "🚫 *CHANNEL IS PRIVATE*\n\n"
    "🍌💦 *SHARE = CONTENT*\n\n"
    "0 / 2 JOIN\n\n"
    "(SHARE) CHANNEL — 55,568 VIDEOS\n\n"
    "SHARE TO 2 GROUPS TO UNLOCK\n\n"
    "Verification is automatic ❤️\n\n"
    "━━━━━━━━━━━━━━━━\n"
    "⏳ *Waiting for admin approval...*"
)

# ── JOIN REQUEST HANDLER ──────────────────────────────────────────────────────
async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    join_req = update.chat_join_request
    user     = join_req.from_user

    if join_req.chat.id != CHANNEL_ID:
        return

    logger.info(f"Join request: {user.id} ({user.full_name})")

    state = get_state(user.id)
    state["messages"]    = []
    state["phase"]       = "waiting"
    state["more_shares"] = 0

    # DM the user — no buttons, just promo message
    try:
        msg = await context.bot.send_message(
            chat_id=user.id,
            text=PROMO_TEXT,
            parse_mode="Markdown",
        )
        state["messages"].append(msg.message_id)
        logger.info(f"DM sent to {user.id}")
    except Exception as e:
        logger.error(f"Cannot DM {user.id}: {e}")
        return

    # Notify admin
    uname = f"@{user.username}" if user.username else "_(no username)_"
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🔔 *New Join Request*\n\n"
            f"👤 Name: {user.full_name or 'Unknown'}\n"
            f"🆔 ID: `{user.id}`\n"
            f"📎 Username: {uname}\n\n"
            f"Approve to send them videos?"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅  APPROVE", callback_data=f"approve:{user.id}:{user.id}"),
            InlineKeyboardButton("❌  REJECT",  callback_data=f"reject:{user.id}:{user.id}"),
        ]])
    )

# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    state   = get_state(user.id)
    state["messages"]    = [update.message.message_id]
    state["phase"]       = "waiting"
    state["more_shares"] = 0

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=PROMO_TEXT,
        parse_mode="Markdown",
    )
    state["messages"].append(msg.message_id)

    uname = f"@{user.username}" if user.username else "_(no username)_"
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🔔 *New Access Request*\n\n"
            f"👤 Name: {user.full_name or 'Unknown'}\n"
            f"🆔 ID: `{user.id}`\n"
            f"📎 Username: {uname}\n\n"
            f"Approve this user?"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅  APPROVE", callback_data=f"approve:{user.id}:{chat_id}"),
            InlineKeyboardButton("❌  REJECT",  callback_data=f"reject:{user.id}:{chat_id}"),
        ]])
    )

# ── ADMIN: APPROVE ────────────────────────────────────────────────────────────
async def handle_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Approved!")

    if query.from_user.id != ADMIN_ID:
        return

    _, uid_str, chat_id_str = query.data.split(":")
    uid     = int(uid_str)
    chat_id = int(chat_id_str)
    state   = get_state(uid)
    state["phase"] = "content"

    # Approve the channel join request
    try:
        await context.bot.approve_chat_join_request(chat_id=CHANNEL_ID, user_id=uid)
    except Exception as e:
        logger.warning(f"approve_chat_join_request: {e}")

    await query.edit_message_text(
        query.message.text + "\n\n✅ *APPROVED — videos sent.*",
        parse_mode="Markdown",
    )

    # Tell user they're approved
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text="✅ *Approved! Sending your videos now...*",
        parse_mode="Markdown",
    )
    state["messages"].append(msg.message_id)

    # Send the videos
    await send_first_content(context.bot, chat_id, uid, state)

# ── ADMIN: REJECT ─────────────────────────────────────────────────────────────
async def handle_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("❌ Rejected.")

    if query.from_user.id != ADMIN_ID:
        return

    _, uid_str, chat_id_str = query.data.split(":")
    uid     = int(uid_str)
    chat_id = int(chat_id_str)

    try:
        await context.bot.decline_chat_join_request(chat_id=CHANNEL_ID, user_id=uid)
    except Exception as e:
        logger.warning(f"decline_chat_join_request: {e}")

    await query.edit_message_text(
        query.message.text + "\n\n❌ *REJECTED.*",
        parse_mode="Markdown",
    )

    state = get_state(uid)
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "❌ *Access Denied*\n\n"
            "You were not approved.\n\n"
            "💳 You can still get access by paying:"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💳  PAY FOR ACCESS — ₱1,499", url=PAYMENT_LINK),
        ]])
    )
    state["messages"].append(msg.message_id)

# ── SEND FIRST 2 VIDEOS ───────────────────────────────────────────────────────
async def send_first_content(bot, chat_id: int, uid: int, state: dict):
    video_msgs = []

    for label, vid_id in [("VIDEO_1_ID", VIDEO_1_ID), ("VIDEO_2_ID", VIDEO_2_ID)]:
        if not vid_id:
            logger.warning(f"{label} is empty")
            await bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ {label} not set in Railway Variables!")
            continue
        try:
            msg = await bot.send_video(
                chat_id=chat_id,
                video=vid_id,
                protect_content=True,
                supports_streaming=True,
            )
            video_msgs.append(msg.message_id)
            state["messages"].append(msg.message_id)
            logger.info(f"✅ Sent {label} to {chat_id}")
        except Exception as e:
            err = f"Video send error {label}: {e}"
            logger.error(err)
            await bot.send_message(chat_id=ADMIN_ID, text=f"❌ {err}")

    # Buttons sent SEPARATELY — SHARE FOR MORE + PAY only
    info_msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            "🔥 *Want MORE videos?*\n\n"
            "📤 Share to groups to unlock more\n\n"
            "─────────────────\n"
            "💳 Or pay for unlimited access"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤  SHARE FOR MORE", url=share_url())],
            [InlineKeyboardButton("💳  PAY FOR ACCESS — ₱1,499", url=PAYMENT_LINK)],
        ])
    )
    state["messages"].append(info_msg.message_id)

    # 🗑 Videos delete after 30s
    asyncio.create_task(schedule_delete(bot, chat_id, video_msgs, VIDEO_DELETE_DELAY))
    # 🗑 Full chat wipe after 30 min
    asyncio.create_task(schedule_delete(bot, chat_id, list(state["messages"]), CHAT_DELETE_DELAY))

# ── MORE CONTENT ──────────────────────────────────────────────────────────────
async def more_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Share registered!")

    _, uid_str, chat_id_str = query.data.split(":")
    uid     = int(uid_str)
    chat_id = int(chat_id_str)
    state   = get_state(uid)

    if query.from_user.id != uid:
        return

    state["more_shares"] += 1
    n      = state["more_shares"]
    needed = 3

    if n < needed:
        await query.edit_message_text(
            (
                "🔥 *Want MORE videos?*\n\n"
                f"📤 Share to groups to unlock more ({n}/{needed})\n\n"
                "─────────────────\n"
                "💳 Or pay for unlimited access"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤  SHARE FOR MORE", url=share_url())],
                [InlineKeyboardButton("💳  PAY FOR ACCESS — ₱1,499", url=PAYMENT_LINK)],
            ])
        )
    else:
        await query.edit_message_text("✅ *Unlocking more content!*", parse_mode="Markdown")
        await send_more_content(context.bot, chat_id, uid, state)

# ── SEND EXTRA VIDEOS ─────────────────────────────────────────────────────────
async def send_more_content(bot, chat_id: int, uid: int, state: dict):
    state["more_shares"] = 0
    extra_msgs = []
    videos = [v.strip() for v in EXTRA_VIDEO_IDS if v.strip()]

    if not videos:
        msg = await bot.send_message(chat_id=chat_id, text="🔥 More videos coming soon! Stay tuned.")
        extra_msgs.append(msg.message_id)
        state["messages"].append(msg.message_id)
    else:
        for vid_id in videos:
            try:
                msg = await bot.send_video(
                    chat_id=chat_id,
                    video=vid_id,
                    protect_content=True,
                    supports_streaming=True,
                )
                extra_msgs.append(msg.message_id)
                state["messages"].append(msg.message_id)
            except Exception as e:
                logger.error(f"Extra video error: {e}")

    info_msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            "🔥 *Enjoyed the content?*\n\n"
            "📤 Share more to keep unlocking\n\n"
            "─────────────────\n"
            "💳 Or go unlimited with paid access"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤  SHARE FOR MORE", url=share_url())],
            [InlineKeyboardButton("💳  PAY FOR ACCESS — ₱1,499", url=PAYMENT_LINK)],
        ])
    )
    state["messages"].append(info_msg.message_id)

    asyncio.create_task(schedule_delete(bot, chat_id, extra_msgs, VIDEO_DELETE_DELAY))
    asyncio.create_task(schedule_delete(bot, chat_id, list(state["messages"]), CHAT_DELETE_DELAY))

# ── AUTO REPLY "SHARE!" ───────────────────────────────────────────────────────
async def auto_reply_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.effective_user.id == ADMIN_ID:
        return
    state = get_state(update.effective_user.id)
    msg = await update.message.reply_text("SHARE!")
    state["messages"].append(update.message.message_id)
    state["messages"].append(msg.message_id)

# ── /testvideo (admin only) ───────────────────────────────────────────────────
async def test_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text("🧪 Testing videos...")

    for label, vid_id in [("VIDEO_1_ID", VIDEO_1_ID), ("VIDEO_2_ID", VIDEO_2_ID)]:
        if not vid_id:
            await update.message.reply_text(f"❌ {label} is EMPTY in Railway Variables!")
            continue
        try:
            await context.bot.send_video(
                chat_id=chat_id,
                video=vid_id,
                protect_content=True,
                supports_streaming=True,
            )
            await update.message.reply_text(f"✅ {label} — OK!")
        except Exception as e:
            await update.message.reply_text(f"❌ {label} FAILED:\n{e}")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testvideo", test_video))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(CallbackQueryHandler(handle_approve, pattern=r"^approve:"))
    app.add_handler(CallbackQueryHandler(handle_reject,  pattern=r"^reject:"))
    app.add_handler(CallbackQueryHandler(more_confirm,   pattern=r"^more:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_reply_share))

    logger.info("Bot running.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
