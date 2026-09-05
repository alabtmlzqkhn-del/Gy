# -*- coding: utf-8 -*-
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, ContextTypes, MessageHandler, filters

SAVED_GROUPS_LINKS = {}


async def set_custom_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.message
    if not chat or not msg or not msg.text:
        return
    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("- هذا الأمر يعمل داخل المجموعات فقط.")
        return

    parts = msg.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        await msg.reply_text("- أرسل الأمر بهذا الشكل:\n\nضع رابط https://t.me/example")
        return

    url = parts[2].strip()
    if url.startswith("t.me/"):
        url = "https://" + url
    elif url.startswith("www.t.me/"):
        url = "https://" + url
    elif not (url.startswith("http://") or url.startswith("https://")):
        await msg.reply_text("- الرابط غير صحيح.")
        return

    SAVED_GROUPS_LINKS[chat.id] = url
    await msg.reply_text("✅ تم حفظ رابط المجموعة بنجاح.")


async def get_group_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.message
    if not chat or not msg:
        return
    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("- هذا الأمر يعمل داخل المجموعات فقط.")
        return

    saved_link = SAVED_GROUPS_LINKS.get(chat.id)
    if saved_link:
        await msg.reply_text(f"🔗 رابط المجموعة:\n{saved_link}", disable_web_page_preview=True)
        return

    try:
        if chat.username:
            link = f"https://t.me/{chat.username}"
        else:
            link = await context.bot.export_chat_invite_link(chat.id)
        await msg.reply_text(f"🔗 رابط المجموعة:\n{link}", disable_web_page_preview=True)
    except TelegramError:
        await msg.reply_text("- لم يتم العثور على رابط للمجموعة.\n\nاستخدم:\nضع رابط https://t.me/example")


async def create_interactive_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.message
    if not chat or not msg:
        return
    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("- هذا الأمر يعمل داخل المجموعات فقط.")
        return

    try:
        if chat.username:
            direct_link = f"https://t.me/{chat.username}"
        else:
            direct_link = await context.bot.export_chat_invite_link(chat.id)

        approval_invite = await context.bot.create_chat_invite_link(
            chat_id=chat.id,
            creates_join_request=True,
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("انضمام 🔗", url=direct_link),
                InlineKeyboardButton("خاص 🔒", url=approval_invite.invite_link),
            ]
        ])

        await msg.reply_text(
            "🔗 خيارات انضمام المجموعة:\n\n"
            "- انضمام: دخول مباشر.\n"
            "- خاص: يتطلب موافقة المشرفين.",
            reply_markup=keyboard,
        )
    except TelegramError:
        await msg.reply_text(
            "- فشل إنشاء الروابط.\n\n"
            "تأكد أن البوت مشرف ولديه صلاحية دعوة المستخدمين عبر رابط."
        )


def setup(app: Application):
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"^(ضع رابط|ضع الرابط)\s+.+$") & ~filters.COMMAND,
            set_custom_link,
        ),
        group=0,
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"^(الرابط|رابط)\s*$") & ~filters.COMMAND,
            get_group_link,
        ),
        group=0,
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"^(انشاء رابط|إنشاء رابط)\s*$") & ~filters.COMMAND,
            create_interactive_links,
        ),
        group=0,
    )
