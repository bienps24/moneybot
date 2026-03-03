"""
Telegram Bot — Auto DM on Channel Join + Admin Approval
=========================================================
Flow:
  User joins channel → Bot auto-DMs them the promo message
  Admin sees notification → Taps ✅ APPROVE or ❌ REJECT
  If bot cannot DM (user never started bot) → Bot posts in channel
  tagging the user to start the bot first

Railway env vars needed:
  BOT_TOKEN, ADMIN_ID, CHANNEL_ID, CHANNEL_LINK,
  PAYMENT_LINK, VIDEO_1_ID, VIDEO_2_ID, EXTRA_VIDEO_IDS
"""
import asyncio
import logging
import os
from urllib.parse import quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMemberUpdated
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
)
from telegram.error import Forbidden, BadRequest

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── ENV VARS — set all of these in Railway → Variables ────────────────────────
BOT_TOKEN       = os.environ["BOT_TOKEN"]
ADMIN_ID        = int(os.environ["ADMIN_ID"])
CHANNEL_ID      = int(os.environ["CHANNEL_ID"])        # e.g. -1001234567890
CHANNEL_LINK    = os.environ.get("CHANNEL_LINK", "https://t.me/+Xb2fi4Gr00c3MTdl")
PAYMENT_LINK    = os.environ.get("PAYMENT_LINK", "https://t.me/your_payment_bot")
VIDEO_1_ID      = os.environ.get("VIDEO_1_ID", "")
VIDEO_2_ID      = os.environ.get("VIDEO_2_ID", "")
EXTRA_VIDEO_IDS = os.environ.get("EXTRA_VIDEO_IDS", "").split(",")

VIDEO_DELETE_DELAY = 30   # seconds before videos are deleted
CHAT_DELETE_DELAY  = 120  # seconds before entire chat is wiped

BOT_LINK = "https://t.me/Xetuu18bot?start=ref"

# ── IN-MEMORY STATE ───────────────────────────────────────────────────────────
user_states: dict[int, dict] = {}


def get_state(uid: int) -> dict:
    if uid not in user_states:
        user_states[uid] = {
            "messages":    [],
            "phase":       "waiting",
            "more_shares": 0,
        }
    return user_states[uid]


def share_url() -> str:
    text = "join our exclusive group"
    return f"https://t.me/share/url?url={quote(BOT_LINK)}&text={quote(text)}"


# ── HELPERS ───────────────────────────────────────────────────────────────────
async def schedule_delete(bot, chat_id: int, message_ids: list[int], delay: int):
    await asyncio.sleep(delay)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass


async def greet_user(bot, user, chat_id: int):
    """Send the promo message to the user and notify admin."""
    state = get_state(user.id)
    state["messages"]    = []
    state["phase"]       = "waiting"
    state["more_shares"] = 0

    msg = await bot.send_message(
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

    username  = f"@{user.username}" if user.username else "_(no username)_"
    full_name = user.full_name or "Unknown"

    await bot.send_message(
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
    logger.info(f"Greeted {user.id} ({full_name})")


# ── NEW CHANNEL MEMBER HANDLER ────────────────────────────────────────────────
async def new_channel_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when someone joins the channel."""
    result: ChatMemberUpdated = update.chat_member

    # Only care about our channel
    if result.chat.id != CHANNEL_ID:
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    # Detect join: was not member, now is member
    joined = (
        old_status in ("left", "kicked", "restricted")
        and new_status in ("member", "administrator", "creator")
    )
    if not joined:
        return

    user = result.new_chat_member.user
    if user.is_bot:
        return

    logger.info(f"User {user.id} ({user.full_name}) joined channel — sending DM.")

    try:
        # Try to DM the user directly
        await greet_user(context.bot, user, user.id)

    except (Forbidden, BadRequest):
        # User never started the bot — cannot DM them
        # Post in channel tagging them to start the bot
        logger.warning(f"Cannot DM {user.id} — posting in channel instead.")
        try:
            msg = await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=(
                    f"👋 Welcome [{user.full_name}](tg://user?id={user.id})\\!\n\n"
                    f"To receive your content, please start our bot first:\n"
                    f"👉 [Click here to start]({BOT_LINK})"
                ),
                parse_mode="MarkdownV2",
            )
            # Auto-delete the welcome message after 60 seconds
            asyncio.create_task(
                schedule_delete(context.bot, CHANNEL_ID, [msg.message_id], 60)
            )
        except Exception as e:
            logger.error(f"Channel post error: {e}")


# ── /start (also handles users who click the bot link) ───────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id

    await greet_user(context.bot, user, chat_id)


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

    await query.edit_message_text(
        query.message.text + "\n\n✅ *APPROVED — content sent.*",
        parse_mode="Markdown",
    )

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
                    protect_content=True,
                    supports_streaming=True,
                )
                video_msgs.append(msg.message_id)
                state["messages"].append(msg.message_id)
            except Exception as e:
                logger.error(f"Video send error: {e}")

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

    asyncio.create_task(schedule_delete(bot, chat_id, video_msgs, VIDEO_DELETE_DELAY))
    asyncio.create_task(
        schedule_delete(bot, chat_id, list(state["messages"]), CHAT_DELETE_DELAY)
    )


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
    app.add_handler(ChatMemberHandler(new_channel_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(handle_approve, pattern=r"^approve:"))
    app.add_handler(CallbackQueryHandler(handle_reject,  pattern=r"^reject:"))
    app.add_handler(CallbackQueryHandler(more_confirm,   pattern=r"^more:"))

    logger.info("Bot running — channel join detection active.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
