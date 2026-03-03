import asyncio
import logging
import os
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ChatJoinRequestHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN        = os.environ["BOT_TOKEN"]
ADMIN_ID         = int(os.environ["ADMIN_ID"])
CHANNEL_ID       = int(os.environ["CHANNEL_ID"])
CHANNEL_LINK     = os.environ.get("CHANNEL_LINK", "https://t.me/+Xb2fi4Gr00c3MTdl")
PAYMENT_LINK     = os.environ.get("PAYMENT_LINK", "")
VIDEO_1_ID       = os.environ.get("VIDEO_1_ID", "")
VIDEO_2_ID       = os.environ.get("VIDEO_2_ID", "")
REMINDER_VIDEO_1 = os.environ.get("REMINDER_VIDEO_1_ID", "")
REMINDER_VIDEO_2 = os.environ.get("REMINDER_VIDEO_2_ID", "")

VIDEO_DELETE_DELAY = 60
REMINDER_DELAY     = 90
CHAT_DELETE_DELAY  = 1200

# Only channel join users are stored here
channel_users: dict[int, dict] = {}

def new_user(uid: int) -> dict:
    channel_users[uid] = {"messages": [], "more_shares": 0}
    return channel_users[uid]

def get_user(uid: int):
    return channel_users.get(uid)

def share_url() -> str:
    return f"https://t.me/share/url?url={quote(CHANNEL_LINK)}&text={quote('join our exclusive group')}"

async def schedule_delete(bot, chat_id: int, message_ids: list, delay: int):
    await asyncio.sleep(delay)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass

def make_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤  SHARE FOR MORE", url=share_url())],
        [InlineKeyboardButton("💳  PAY FOR ACCESS — ₱1,499", url=PAYMENT_LINK)],
    ])

CONTENT_TEXT = (
    "🚫 *CHANNEL IS PRIVATE*\n\n"
    "🍌💦 *SHARE = CONTENT*\n\n"
    "0 / 2 JOIN\n\n"
    "(SHARE) CHANNEL — 55,568 VIDEOS\n\n"
    "SHARE TO 2 GROUPS TO UNLOCK more free videos\n\n"
    "Verification is automatic ❤️"
)

async def send_videos(bot, chat_id: int, state: dict, vid1: str, vid2: str):
    video_msgs = []
    for label, vid_id in [("VIDEO_1", vid1), ("VIDEO_2", vid2)]:
        if not vid_id:
            await bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ {label} not set in Railway!")
            continue
        try:
            msg = await bot.send_video(chat_id=chat_id, video=vid_id, protect_content=True, supports_streaming=True)
            video_msgs.append(msg.message_id)
            state["messages"].append(msg.message_id)
        except Exception as e:
            logger.error(f"{label} error: {e}")
            await bot.send_message(chat_id=ADMIN_ID, text=f"❌ {label} error: {e}")

    info = await bot.send_message(chat_id=chat_id, text=CONTENT_TEXT, parse_mode="Markdown", reply_markup=make_buttons())
    state["messages"].append(info.message_id)
    asyncio.create_task(schedule_delete(bot, chat_id, video_msgs, VIDEO_DELETE_DELAY))

async def send_reminder(bot, chat_id: int, uid: int):
    await asyncio.sleep(REMINDER_DELAY)
    state = get_user(uid)
    if state is None:
        return
    reminder_msgs = []
    for label, vid_id in [("REM1", REMINDER_VIDEO_1), ("REM2", REMINDER_VIDEO_2)]:
        if not vid_id:
            continue
        try:
            msg = await bot.send_video(chat_id=chat_id, video=vid_id, protect_content=True, supports_streaming=True)
            reminder_msgs.append(msg.message_id)
            state["messages"].append(msg.message_id)
        except Exception as e:
            logger.error(f"Reminder {label} error: {e}")

    info = await bot.send_message(
        chat_id=chat_id,
        text="🔥 *Want more videos?*\n\n📤 Share our channel to unlock more content!\n\n─────────────────\n💳 Or pay for unlimited access",
        parse_mode="Markdown",
        reply_markup=make_buttons()
    )
    reminder_msgs.append(info.message_id)
    state["messages"].append(info.message_id)
    asyncio.create_task(schedule_delete(bot, chat_id, reminder_msgs, VIDEO_DELETE_DELAY))
    asyncio.create_task(schedule_delete(bot, chat_id, list(state["messages"]), CHAT_DELETE_DELAY))

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    join_req = update.chat_join_request
    user = join_req.from_user
    if join_req.chat.id != CHANNEL_ID:
        return
    logger.info(f"Join request: {user.id} ({user.full_name})")
    state = new_user(user.id)
    await send_videos(context.bot, user.id, state, VIDEO_1_ID, VIDEO_2_ID)
    asyncio.create_task(send_reminder(context.bot, user.id, user.id))

async def auto_reply_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    uid = update.effective_user.id
    if uid == ADMIN_ID:
        return
    # Strictly ignore anyone not from channel join
    if get_user(uid) is None:
        return
    state = get_user(uid)
    msg = await update.message.reply_text("SHARE!")
    state["messages"].append(update.message.message_id)
    state["messages"].append(msg.message_id)

async def test_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("🧪 Testing videos...")
    for label, vid_id in [("VIDEO_1_ID", VIDEO_1_ID), ("VIDEO_2_ID", VIDEO_2_ID)]:
        if not vid_id:
            await update.message.reply_text(f"❌ {label} is EMPTY!")
            continue
        try:
            await context.bot.send_video(chat_id=update.effective_chat.id, video=vid_id, protect_content=True, supports_streaming=True)
            await update.message.reply_text(f"✅ {label} — OK!")
        except Exception as e:
            await update.message.reply_text(f"❌ {label} FAILED: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("testvideo", test_video))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(MessageHandler(filters.ALL, auto_reply_share))
    logger.info("Bot running — channel join users only.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
