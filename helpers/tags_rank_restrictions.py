# -*- coding: utf-8 -*-
"""تاك + تنزيل الكل + كشف القيود، كملف مستقل."""

import sqlite3
import threading
from pathlib import Path

from telegram import Update, ChatPermissions
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes, MessageHandler, filters

DB_PATH = Path(__file__).with_name("tags_rank_restrictions.db")
_DB_LOCK = threading.RLock()


def _db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            chat_id INTEGER PRIMARY KEY,
            tag_name TEXT NOT NULL,
            username TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def _save_tag(chat_id: int, name: str, username: str) -> None:
    with _DB_LOCK:
        conn = _db()
        conn.execute(
            "INSERT INTO tags(chat_id, tag_name, username) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET tag_name=excluded.tag_name, username=excluded.username",
            (chat_id, name, username),
        )
        conn.commit()
        conn.close()


def _get_tag(chat_id: int):
    with _DB_LOCK:
        conn = _db()
        row = conn.execute("SELECT tag_name, username FROM tags WHERE chat_id=?", (chat_id,)).fetchone()
        conn.close()
    return (row["tag_name"], row["username"]) if row else None


def _normalize_username(value: str) -> str:
    value = value.strip()
    if value.startswith("@"):
        value = value[1:]
    return value


async def _is_admin_or_rank_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            return True
    except Exception:
        pass
    try:
        import bot22
        return bot22.has_rank(chat.id, user.id, "ادمن")
    except Exception:
        return False


async def _tag_and_setup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user or chat.type not in ("group", "supergroup"):
        return

    text = (msg.text or "").strip()
    key = (chat.id, user.id)
    states = context.application.bot_data.setdefault("_custom_tag_states", {})
    state = states.get(key)

    # بدء إعداد التاك
    if text in ("تاك", "اضف تاك"):
        if not await _is_admin_or_rank_admin(update, context):
            await msg.reply_text("- هذا الامر يخص الادمن فما فوق .")
            return
        states[key] = "name"
        await msg.reply_text("- ارسل الاسم الان")
        return

    # استقبال الاسم
    if state == "name":
        if not text:
            return
        states[key] = {"step": "username", "name": text}
        await msg.reply_text("- تم حفظ الاسم\n- ارسل اليوزر الان")
        return

    # استقبال اليوزر
    if isinstance(state, dict) and state.get("step") == "username":
        username = _normalize_username(text)
        if not username or " " in username or username.startswith("-"):
            await msg.reply_text("- ارسل اليوزر بشكل صحيح مثل @username")
            return
        _save_tag(chat.id, state["name"], username)
        states.pop(key, None)
        await msg.reply_text("- تم حفظ اليوزر")
        return

    # تنفيذ التاك عند ظهور الاسم داخل رسالة عضو/مشرف/أي مستخدم.
    saved = _get_tag(chat.id)
    if saved and saved[0] and saved[0] in text:
        username = saved[1]
        await msg.reply_text(f"@{username}")


async def _resolve_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return None, None
    if msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        return u.id, u.full_name or u.first_name or str(u.id)

    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return None, None
    target = parts[1].strip()
    if target.startswith("@"):
        try:
            member = await context.bot.get_chat_member(msg.chat.id, target)
            return member.user.id, member.user.full_name or member.user.first_name or target
        except Exception:
            try:
                import bot22
                uid, name = await bot22.get_target_from_message(msg, target, context)
                if uid:
                    return uid, name
            except Exception:
                pass
            return None, None
    if target.lstrip("-").isdigit():
        uid = int(target)
        try:
            member = await context.bot.get_chat_member(msg.chat.id, uid)
            return member.user.id, member.user.full_name or member.user.first_name or str(uid)
        except Exception:
            return uid, str(uid)
    return None, None


async def _demote_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    chat = update.effective_chat
    actor = update.effective_user
    if not msg or not chat or not actor or chat.type not in ("group", "supergroup"):
        return
    if not await _is_admin_or_rank_admin(update, context):
        await msg.reply_text("- هذا الامر يخص الادمن فما فوق .")
        return

    target_id, target_name = await _resolve_target(update, context)
    if not target_id:
        await msg.reply_text("- رد على الشخص او اكتب يوزر/ايدي الشخص .")
        return

    try:
        import bot22
        actor_rank = bot22.get_actor_rank(chat.id, actor.id)
        target_rank = bot22.get_actor_rank(chat.id, target_id)
        if target_rank == "عضو":
            await msg.reply_text("- هذا شخص لا يمتلك رتبة")
            return
        if actor_rank != "مطور السورس" and bot22.rank_level(actor_rank) <= bot22.rank_level(target_rank):
            await msg.reply_text("- لا تستطيع تنزيل شخص برتبة مساوية لك أو أعلى .")
            return
        # هذا الأمر ينزل الرتبة الداخلية فقط، ولا يزيل صلاحيات أدمن تيليجرام الرسمية.
        bot22.db_remove_rank(chat.id, target_id)
        await msg.reply_text(f"- تم تنزيل {target_name} من جميع الرتب")
    except Exception:
        await msg.reply_text("- تعذر تنزيل رتبة الشخص حالياً .")


async def _check_restrictions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    chat = update.effective_chat
    if not msg or not chat or chat.type not in ("group", "supergroup"):
        return
    if not await _is_admin_or_rank_admin(update, context):
        await msg.reply_text("- هذا الامر يخص الادمن فما فوق .")
        return

    target_id, target_name = await _resolve_target(update, context)
    if not target_id:
        await msg.reply_text("- رد على الشخص او اكتب يوزر/ايدي الشخص .")
        return

    try:
        member = await context.bot.get_chat_member(chat.id, target_id)
    except Exception:
        await msg.reply_text("- ما لكيت الشخص")
        return

    status = member.status
    if status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        if status == ChatMemberStatus.BANNED:
            lines = ["- الطرد ↫ غير مطرود", "- الحظر ↫ تم حظرة", "- الكتم ↫ غير مكتوم", "- التقييد ↫ غير مقييد"]
        else:
            lines = ["- الطرد ↫ تم طردة", "- الحظر ↫ غير محظور", "- الكتم ↫ غير مكتوم", "- التقييد ↫ غير مقييد"]
    elif status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        lines = ["- الطرد ↫ غير مطرود", "- الحظر ↫ غير محظور", "- الكتم ↫ غير مكتوم", "- التقييد ↫ غير مقييد"]
    else:
        restricted = status == ChatMemberStatus.RESTRICTED
        permissions = getattr(member, "permissions", None)
        muted = restricted and permissions is not None and not getattr(permissions, "can_send_messages", True)
        restricted_only = restricted and not muted
        lines = [
            "- الطرد ↫ غير مطرود",
            "- الحظر ↫ غير محظور",
            f"- الكتم ↫ {'تم كتمة' if muted else 'غير مكتوم'}",
            f"- التقييد ↫ {'تم تقييدة' if restricted_only else 'غير مقييد'}",
        ]

    await msg.reply_text("\n".join(lines))


async def _router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.text:
        return
    text = msg.text.strip()
    if text == "تنزيل الكل" or text.startswith("تنزيل الكل "):
        await _demote_all(update, context)
        return
    if text == "كشف القيود" or text.startswith("كشف القيود "):
        await _check_restrictions(update, context)
        return
    await _tag_and_setup_handler(update, context)


def setup(app) -> None:
    # يعمل في مجموعات فقط، ويأتي قبل أغلب الهاندلرز النصية في bot22.
    app.add_handler(
        MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, _router),
        group=-3,
    )
