"""
Telegram Bot — Admin Approval Version
======================================
Flow:
  User /start → Bot greets user → Admin gets notification card
  Admin taps ✅ APPROVE → Bot sends 2 protected videos to user
  Admin taps ❌ REJECT  → Bot sends rejection + pay button

Railway env vars needed:
  BOT_TOKEN, ADMIN_ID, CHANNEL_LINK, PAYMENT_LINK,
  VIDEO_1_ID, VIDEO_2_ID, EXTRA_VIDEO_IDS
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
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── ENV VARS — set all of these in Railway → Variables ────────────────────────
BOT_TOKEN       = os.environ["BOT_TOKEN"]
ADMIN_ID        = int(os.environ["ADMIN_ID"])           # Your Telegram numeric ID
CHANNEL_LINK    = os.environ.get("CHANNEL_LINK", "https://t.me/+Xb2fi4Gr00c3MTdl")
PAYMENT_LINK    = os.environ.get("PAYMENT_LINK", "https://t.me/your_payment_bot")
VIDEO_1_ID      = os.environ.get("VIDEO_1_ID", "")
VIDEO_2_ID      = os.environ.get("VIDEO_2_ID", "")
EXTRA_VIDEO_IDS = os.environ.get("EXTRA_VIDEO_IDS", "").split(",")

VIDEO_DELETE_DELAY = 30   # seconds before videos are deleted
CHAT_DELETE_DELAY  = 120  # seconds before entire chat is wiped

# ── IN-MEMORY STATE ───────────────────────────────────────────────────────────
user_states: dict[int, dict] = {}


def get_state(uid: int) -> dict:
    if uid not in user_states:
        user_states[uid] = {
            "messages":       [],   # all message ids in user chat
            "phase":          "waiting",
            "more_shares":    0,
        }
    return user_states[uid]


def share_url() -> str:
    text = "join our exclusive group"
    return f"https://t.me/share/url?url={quote(CHANNEL_LINK)}&text={quote(text)}"


# ── HELPERS ───────────────────────────────────────────────────────────────────
async def schedule_delete(bot, chat_id: int, message_ids: list[int], delay: int):
    """Delete a list of messages after `delay` seconds."""
    await asyncio.sleep(delay)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass


# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    state   = get_state(user.id)

    # Reset state
    state["messages"]    = [update.message.message_id]
    state["phase"]       = "waiting"
    state["more_shares"] = 0

    # 1️⃣  Greet the user — show the promo message
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🚫 *CHANNEL IS PRIVATE*\n\n"
            "🍌💦 *SHARE \\= CONTENT*\n\n"
            "0 / 2 JOIN\n\n"
            "\\(SHARE\\) CHANNEL \\— *55,568 VIDEOS*\n\n"
            "SHARE TO 2 GROUPS TO UNLOCK\n\n"
            "Verification is automatic ❤️\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⏳ *Waiting for admin approval\\.\\.\\.*"
        ),
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📤  SHARE LINK", url=share_url()),
        ]])
    )
    state["messages"].append(msg.message_id)

    # 2️⃣  Notify admin — show user info + Approve / Reject buttons
    username  = f"@{user.username}" if user.username else "_(no username)_"
    full_name = user.full_name or "Unknown"

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🔔 *New Access Request*\n\n"
            f"👤 Name: {full_name}\n"
            f"🆔 ID: `{user.id}`\n"
            f"📎 Username: {username}\n\n"
            f"Do you want to approve this user?"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅  APPROVE", callback_data=f"approve:{user.id}:{chat_id}"),
            InlineKeyboardButton("❌  REJECT",  callback_data=f"reject:{user.id}:{chat_id}"),
        ]])
    )
    logger.info(f"New request from {user.id} ({full_name}) — awaiting admin decision.")


# ── ADMIN: APPROVE ────────────────────────────────────────────────────────────
async def handle_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Approved!")

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return

    _, uid_str, chat_id_str = query.data.split(":")
    uid     = int(uid_str)
    chat_id = int(chat_id_str)
    state   = get_state(uid)
    state["phase"] = "content"

    # Update the admin's card
    await query.edit_message_text(
        query.message.text + "\n\n✅ *APPROVED — content sent.*",
        parse_mode="Markdown",
    )

    # Tell user they're in
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text="✅ *You have been approved\\!* Sending your content now\\.\\.\\.",
        parse_mode="MarkdownV2",
    )
    state["messages"].append(msg.message_id)

    await send_first_content(context.bot, chat_id, uid, state)


# ── ADMIN: REJECT ─────────────────────────────────────────────────────────────
async def handle_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("❌ Rejected.")

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return

    _, uid_str, chat_id_str = query.data.split(":")
    uid     = int(uid_str)
    chat_id = int(chat_id_str)

    await query.edit_message_text(
        query.message.text + "\n\n❌ *REJECTED.*",
        parse_mode="Markdown",
    )

    state = get_state(uid)
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "❌ *Access Denied*\n\n"
            "You were not approved at this time\\.\n\n"
            "💳 You can still get access by paying:"
        ),
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💳  PAY FOR ACCESS — ₱1,499", url=PAYMENT_LINK),
        ]])
    )
    state["messages"].append(msg.message_id)


# ── SEND FIRST 2 VIDEOS ───────────────────────────────────────────────────────
async def send_first_content(bot, chat_id: int, uid: int, state: dict):
    video_msgs = []

    for vid_id in [VIDEO_1_ID, VIDEO_2_ID]:
        if vid_id:
            try:
                msg = await bot.send_video(
                    chat_id=chat_id,
                    video=vid_id,
                    protect_content=True,    # 🔒 no forward / no save
                    supports_streaming=True,
                )
                video_msgs.append(msg.message_id)
                state["messages"].append(msg.message_id)
            except Exception as e:
                logger.error(f"Video send error: {e}")

    # Buttons sent SEPARATELY from the videos (as per original design)
    needed   = 3
    info_msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            "🔥 *Want MORE videos?*\n\n"
            f"📤 Share to *{needed} groups* to unlock more\n\n"
            "─────────────────\n"
            "💳 Or pay for *unlimited access*"
        ),
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤  SHARE FOR MORE", url=share_url())],
            [InlineKeyboardButton("💳  PAY FOR ACCESS — ₱1,499", url=PAYMENT_LINK)],
        ])
    )
    state["messages"].append(info_msg.message_id)

    # 🗑 Videos auto-delete after 30 s
    asyncio.create_task(schedule_delete(bot, chat_id, video_msgs, VIDEO_DELETE_DELAY))
    # 🗑 Entire chat wipe after 2 min
    asyncio.create_task(
        schedule_delete(bot, chat_id, list(state["messages"]), CHAT_DELETE_DELAY)
    )


# ── MORE CONTENT (share 3x) ───────────────────────────────────────────────────
async def more_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Share registered!")

    _, uid_str, chat_id_str = query.data.split(":")
    uid     = int(uid_str)
    chat_id = int(chat_id_str)
    state   = get_state(uid)

    # Only the correct user can tap their own button
    if query.from_user.id != uid:
        return

    state["more_shares"] += 1
    n      = state["more_shares"]
    needed = 3

    if n < needed:
        await query.edit_message_text(
            (
                "🔥 *Want MORE videos?*\n\n"
                f"📤 Share to *{needed} groups* to unlock more\n\n"
                "─────────────────\n"
                "💳 Or pay for *unlimited access*"
            ),
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤  SHARE FOR MORE", url=share_url())],
                [InlineKeyboardButton("💳  PAY FOR ACCESS — ₱1,499", url=PAYMENT_LINK)],
            ])
        )
    else:
        await query.edit_message_text("✅ *Unlocking more content\\!*", parse_mode="MarkdownV2")
        await send_more_content(context.bot, chat_id, uid, state)


# ── SEND EXTRA VIDEOS ─────────────────────────────────────────────────────────
async def send_more_content(bot, chat_id: int, uid: int, state: dict):
    state["more_shares"] = 0
    extra_msgs = []
    videos = [v.strip() for v in EXTRA_VIDEO_IDS if v.strip()]

    if not videos:
        msg = await bot.send_message(
            chat_id=chat_id,
            text="🔥 More videos coming soon\\! Stay tuned\\.",
            parse_mode="MarkdownV2",
        )
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

    needed   = 3
    info_msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            "🔥 *Enjoyed the content?*\n\n"
            f"📤 Share *{needed}x* more to keep unlocking\n\n"
            "─────────────────\n"
            "💳 Or go unlimited with *paid access*"
        ),
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤  SHARE FOR MORE", url=share_url())],
            [InlineKeyboardButton("💳  PAY FOR ACCESS — ₱1,499", url=PAYMENT_LINK)],
        ])
    )
    state["messages"].append(info_msg.message_id)

    asyncio.create_task(schedule_delete(bot, chat_id, extra_msgs, VIDEO_DELETE_DELAY))
    asyncio.create_task(
        schedule_delete(bot, chat_id, list(state["messages"]), CHAT_DELETE_DELAY)
    )


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_approve, pattern=r"^approve:"))
    app.add_handler(CallbackQueryHandler(handle_reject,  pattern=r"^reject:"))
    app.add_handler(CallbackQueryHandler(more_confirm,   pattern=r"^more:"))

    logger.info("Bot is running — admin approval mode.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
