# -*- coding: utf-8 -*-
"""
أوامر التسلية الاجتماعية للبوت.

الأوامر:
جمالي
زوجني
زوجي / زوجتي
طلاق / طلقني (مع الرد أو بدونه)
نسبة الحب
نسبة الكره
نسبة الرجولة
نسبة الانوثة
نسبة الجمال

أوامر النسب التي تحتاج اسماً تسأل المستخدم عن الاسم ثم تحسب النسبة.
النتائج ترفيهية وعشوائية وليست حكماً حقيقياً على الشخص.
"""

import html
import random
import sqlite3
import threading
import time
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

DB_PATH = "fun_data.db"
_DB_LOCK = threading.Lock()

# (chat_id, user_id) -> pending test name command
_PENDING: dict[tuple[int, int], str] = {}
_PENDING_LOCK = threading.Lock()


def _conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _init_db():
    with _DB_LOCK:
        conn = _conn()
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS marriages (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            partner_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY(chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS members (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(chat_id, user_id)
        );
        """)
        conn.commit()
        conn.close()


def _remember_member(chat_id: int, user_id: int, name: str, username: str = ""):
    with _DB_LOCK:
        conn = _conn()
        conn.execute(
            "INSERT OR REPLACE INTO members(chat_id,user_id,name,username) VALUES(?,?,?,?)",
            (chat_id, user_id, name or "مجهول", username or ""),
        )
        conn.commit()
        conn.close()


def _member_rows(chat_id: int):
    conn = _conn()
    rows = conn.execute(
        "SELECT user_id,name,username FROM members WHERE chat_id=?", (chat_id,)
    ).fetchall()
    conn.close()
    return rows


def _get_partner(chat_id: int, user_id: int) -> Optional[int]:
    conn = _conn()
    row = conn.execute(
        "SELECT partner_id FROM marriages WHERE chat_id=? AND user_id=?",
        (chat_id, user_id),
    ).fetchone()
    conn.close()
    return int(row["partner_id"]) if row else None


def _set_marriage(chat_id: int, a: int, b: int):
    with _DB_LOCK:
        conn = _conn()
        now = int(time.time())
        conn.execute(
            "INSERT OR REPLACE INTO marriages(chat_id,user_id,partner_id,created_at) VALUES(?,?,?,?)",
            (chat_id, a, b, now),
        )
        conn.execute(
            "INSERT OR REPLACE INTO marriages(chat_id,user_id,partner_id,created_at) VALUES(?,?,?,?)",
            (chat_id, b, a, now),
        )
        conn.commit()
        conn.close()


def _divorce(chat_id: int, a: int, b: Optional[int] = None) -> bool:
    with _DB_LOCK:
        conn = _conn()
        if b is None:
            row = conn.execute(
                "SELECT partner_id FROM marriages WHERE chat_id=? AND user_id=?",
                (chat_id, a),
            ).fetchone()
            if not row:
                conn.close()
                return False
            b = int(row["partner_id"])
        conn.execute("DELETE FROM marriages WHERE chat_id=? AND user_id IN (?,?)", (chat_id, a, b))
        conn.commit()
        conn.close()
        return True


def _display(user_id: int, name: str, username: str = "") -> str:
    if username:
        return f"@{html.escape(username.lstrip('@'))}"
    return f'<a href="tg://user?id={user_id}">{html.escape(name or "مجهول")}</a>'


def _score() -> int:
    return random.randint(1, 100)


def _target_from_reply(update: Update):
    msg = update.effective_message
    if msg and msg.reply_to_message and msg.reply_to_message.from_user:
        return msg.reply_to_message.from_user
    return update.effective_user


async def _member_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user or chat.type not in ("group", "supergroup"):
        return
    _remember_member(chat.id, user.id, user.full_name or user.first_name or "مجهول", user.username or "")
    msg = update.effective_message
    if msg and msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        _remember_member(chat.id, u.id, u.full_name or u.first_name or "مجهول", u.username or "")


# فلتر مخصص حتى لا يلتقط كل الرسائل؛ فقط من ينتظر اسماً.


def _pending_check(update: Update) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    if not chat or not user or not msg or not msg.text:
        return False
    with _PENDING_LOCK:
        return (chat.id, user.id) in _PENDING


class _PendingMessageHandler(MessageHandler):
    def check_update(self, update):
        if not _pending_check(update):
            return False
        return super().check_update(update)


async def _pending_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    if not chat or not user or not msg or not msg.text:
        return
    key = (chat.id, user.id)
    with _PENDING_LOCK:
        kind = _PENDING.pop(key, None)
    if not kind:
        return

    name = msg.text.strip().lstrip("@").strip()
    if not name:
        await msg.reply_text("- ارسل اسم مستخدم صحيح.")
        return

    labels = {
        "male": "الرجولة",
        "female": "الانوثة",
        "beauty": "الجمال",
    }
    score = _score()
    label = labels[kind]
    await msg.reply_text(
        f"- نسبة {label} لـ {html.escape(name)} هي : <b>{score}%</b> 😎",
        parse_mode="HTML",
    )


async def beauty_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = _target_from_reply(update)
    if not target:
        return
    score = _score()
    name = target.full_name or target.first_name or "مجهول"
    await update.effective_message.reply_text(
        f"✨ نسبة جمال {html.escape(name)} هي : <b>{score}%</b>",
        parse_mode="HTML",
    )


async def marry_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    if not chat or not user or not msg or chat.type not in ("group", "supergroup"):
        if msg:
            await msg.reply_text("- هذا الأمر يعمل داخل المجموعات فقط.")
        return

    current = _get_partner(chat.id, user.id)
    if current:
        await msg.reply_text("- انت متزوج بالفعل 😅 اكتب ( زوجي ) أو ( زوجتي ) لمعرفة الشريك.")
        return

    rows = [r for r in _member_rows(chat.id) if int(r["user_id"]) != user.id and not _get_partner(chat.id, int(r["user_id"]))]
    if not rows:
        await msg.reply_text("- ما عندي أعضاء كافين للاختيار 😅 خلي الأعضاء يرسلون رسائل أولاً وبعدين اكتب زوجني.")
        return

    partner = random.choice(rows)
    partner_id = int(partner["user_id"])
    _set_marriage(chat.id, user.id, partner_id)
    me = _display(user.id, user.full_name or user.first_name or "مجهول", user.username or "")
    them = _display(partner_id, partner["name"], partner["username"])
    await msg.reply_text(
        f"💍 مبروك الزواج!\n\n{me} ❤️ {them}\n\nتم تسجيل الزواج بنجاح 😂",
        parse_mode="HTML",
    )


async def spouse_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    if not chat or not user or not msg or chat.type not in ("group", "supergroup"):
        if msg:
            await msg.reply_text("- هذا الأمر يعمل داخل المجموعات فقط.")
        return
    partner_id = _get_partner(chat.id, user.id)
    if not partner_id:
        await msg.reply_text("- انت مو متزوج حالياً 😅 اكتب ( زوجني )")
        return
    rows = [r for r in _member_rows(chat.id) if int(r["user_id"]) == partner_id]
    if rows:
        r = rows[0]
        partner = _display(partner_id, r["name"], r["username"])
    else:
        partner = f'<a href="tg://user?id={partner_id}">الشخص</a>'
    await msg.reply_text(f"💍 زوجتك/زوجك هو : {partner}", parse_mode="HTML")


async def divorce_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    if not chat or not user or not msg or chat.type not in ("group", "supergroup"):
        if msg:
            await msg.reply_text("- هذا الأمر يعمل داخل المجموعات فقط.")
        return

    target = msg.reply_to_message.from_user if msg.reply_to_message and msg.reply_to_message.from_user else None
    if target and target.id != user.id:
        ok = _divorce(chat.id, user.id, target.id)
        if ok:
            await msg.reply_text("💔 تم الطلاق بين الطرفين.")
        else:
            await msg.reply_text("- ماكو زواج مسجل بينكم.")
        return

    ok = _divorce(chat.id, user.id)
    if ok:
        await msg.reply_text("💔 تم الطلاق بنجاح.")
    else:
        await msg.reply_text("- انت مو متزوج حالياً.")


def _ask_pending(kind: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        user = update.effective_user
        msg = update.effective_message
        if not chat or not user or not msg:
            return
        with _PENDING_LOCK:
            _PENDING[(chat.id, user.id)] = kind
        await msg.reply_text("- ارسل اسم مستخدم للشخص الآن .")
    return handler


def setup(app: Application):
    _init_db()

    # تسجيل أعضاء المجموعة قبل باقي الهاندلرات بدون استهلاك الرسالة.
    app.add_handler(TypeHandler(Update, _member_collector), group=-99)

    # إذا كان المستخدم في انتظار اسم، هذا الهاندلر يسبق باقي أوامر النص.
    app.add_handler(
        _PendingMessageHandler(filters.TEXT & ~filters.COMMAND, _pending_name_handler),
        group=0,
    )

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^جمالي$") & ~filters.COMMAND,
        beauty_handler,
    ), group=0)

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^زوجني$") & ~filters.COMMAND,
        marry_handler,
    ), group=0)

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^(زوجي|زوجتي)$") & ~filters.COMMAND,
        spouse_handler,
    ), group=0)

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^(طلاق|طلقني)$") & ~filters.COMMAND,
        divorce_handler,
    ), group=0)

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^(نسبة|نسبه) الحب$") & ~filters.COMMAND,
        lambda u, c: _simple_score(u, "الحب"),
    ), group=0)

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^(نسبة|نسبه) الكره$") & ~filters.COMMAND,
        lambda u, c: _simple_score(u, "الكره"),
    ), group=0)

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^(نسبة|نسبه) الرجولة$") & ~filters.COMMAND,
        _ask_pending("male"),
    ), group=0)

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^(نسبة|نسبه) الانوثة$") & ~filters.COMMAND,
        _ask_pending("female"),
    ), group=0)

    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^(نسبة|نسبه) الجمال$") & ~filters.COMMAND,
        _ask_pending("beauty"),
    ), group=0)


async def _simple_score(update: Update, label: str):
    msg = update.effective_message
    if not msg:
        return
    score = _score()
    name = (update.effective_user.full_name if update.effective_user else "") or "مجهول"
    await msg.reply_text(
        f"💘 نسبة {label} لـ {html.escape(name)} هي : <b>{score}%</b>",
        parse_mode="HTML",
    )
