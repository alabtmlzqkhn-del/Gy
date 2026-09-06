# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes, MessageHandler, filters

DB_PATH = Path(os.getenv("LOCKS_DB_PATH", "locks_data.db"))

# الكلمات التي طلبها المستخدم لقفل الفشار.
POPCORN_WORDS = [
    "كسمك", "كسخالتك", "عير", "كس", "عير بيك", "ابن كحبة",
    "ابن العاهرة", "ابن عاهرة", "ابن بربوك", "كحبة", "ساقطة", "ام العيورة",
]

LOCK_NAMES = {
    "الفشار": "popcorn",
    "فشار": "popcorn",
    "الفيديو": "video",
    "فيديو": "video",
    "الصوت": "voice",
    "صوت": "voice",
    "الملفات": "files",
    "ملفات": "files",
    "الدردشة": "chat",
    "دردشة": "chat",
    "الفارسية": "persian",
    "فارسية": "persian",
    "الانكليزية": "english",
    "الإنكليزية": "english",
    "الانجليزي": "english",
    "الإنجليزي": "english",
    "السيلفي": "selfie",
    "سيلفي": "selfie",
}


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS locks (
            chat_id INTEGER PRIMARY KEY,
            data TEXT NOT NULL DEFAULT '{}'
        )"""
    )
    return conn


def _get_locks(chat_id: int) -> dict[str, bool]:
    conn = _db()
    row = conn.execute("SELECT data FROM locks WHERE chat_id=?", (chat_id,)).fetchone()
    conn.close()
    if not row:
        return {}
    try:
        data = json.loads(row[0])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _set_lock(chat_id: int, key: str, enabled: bool) -> None:
    data = _get_locks(chat_id)
    data[key] = enabled
    conn = _db()
    conn.execute(
        "INSERT INTO locks(chat_id,data) VALUES(?,?) "
        "ON CONFLICT(chat_id) DO UPDATE SET data=excluded.data",
        (chat_id, json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def _normalize(text: str) -> str:
    text = text.lower()
    # توحيد بعض أشكال الألف/الياء العربية لتقليل التحايل البسيط.
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي")
    return text


def _contains_popcorn(text: str) -> bool:
    text = _normalize(text)
    return any(_normalize(word) in text for word in POPCORN_WORDS)


def _contains_persian(text: str) -> bool:
    # حروف شائعة ومميزة في الفارسية.
    return bool(re.search(r"[پچژگک]", text))


def _contains_english(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", text))


def _is_allowed_rank(chat_id: int, user_id: int) -> bool:
    """المميز وجميع الرتب الأعلى منه مستثنون من أقفال المحتوى."""
    try:
        try:
            from . import bot22
        except ImportError:
            import bot22
        rank = bot22.get_actor_rank(chat_id, user_id)
        return bot22.rank_level(rank) >= bot22.rank_level("مميز")
    except Exception:
        return False


async def _can_manage_locks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """تغيير الأقفال: مشرف تيليجرام أو رتبة ادمن فما فوق."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not update.effective_chat:
        return False
    try:
        try:
            from . import bot22
        except ImportError:
            import bot22
        # نسمح للأدمن الرسمي في تيليجرام أو رتبة ادمن فما فوق في نظام البوت.
        member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
        if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            return True
        return bot22.rank_level(bot22.get_actor_rank(update.effective_chat.id, user.id)) >= bot22.rank_level("ادمن")
    except Exception:
        return False


async def _lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat or chat.type not in ("group", "supergroup"):
        return

    text = (msg.text or msg.caption or "").strip()
    m = re.fullmatch(r"(قفل|فتح)\s+(.+?)\s*", text)
    if not m:
        return

    action, raw_name = m.groups()
    key = LOCK_NAMES.get(raw_name.strip())
    if not key:
        return

    if not await _can_manage_locks(update):
        return

    enabled = action == "قفل"
    _set_lock(chat.id, key, enabled)
    state = "تم قفل" if enabled else "تم فتح"
    await msg.reply_text(f"᥀︙ {state} {raw_name.strip()} ✓")


async def _enforce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user or chat.type not in ("group", "supergroup"):
        return

    locks = _get_locks(chat.id)
    if not locks or _is_allowed_rank(chat.id, user.id):
        return

    delete = False

    if locks.get("chat"):
        # قفل الدردشة يمنع العضو العادي من أي رسالة.
        delete = True
    else:
        if locks.get("popcorn"):
            text = msg.text or msg.caption or ""
            if text and _contains_popcorn(text):
                delete = True

        if locks.get("video") and msg.video:
            delete = True

        if locks.get("voice") and (msg.voice or msg.audio):
            delete = True

        if locks.get("files") and msg.document:
            delete = True

        if locks.get("selfie") and msg.video_note:
            delete = True

        if locks.get("persian"):
            text = msg.text or msg.caption or ""
            if text and _contains_persian(text):
                delete = True

        if locks.get("english"):
            text = msg.text or msg.caption or ""
            if text and _contains_english(text):
                delete = True

    if delete:
        try:
            await msg.delete()
        except Exception:
            # يحتاج البوت صلاحية حذف الرسائل في المجموعة.
            pass


def setup(app) -> None:
    """ربط أوامر الأقفال مع تطبيق bot22."""
    # أوامر قفل/فتح أولاً حتى لا تُحذف عند تفعيل قفل الدردشة.
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.ChatType.GROUPS,
            _lock_command,
        ),
        group=-210,
    )
    # التنفيذ مبكر حتى تُحذف رسائل العضو قبل وصولها إلى بقية الهاندلرات.
    app.add_handler(
        MessageHandler(
            filters.ALL & filters.ChatType.GROUPS,
            _enforce,
        ),
        group=-200,
    )
