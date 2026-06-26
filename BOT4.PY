import json
import os
import asyncio
import logging
import random
from datetime import datetime
import aiohttp
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ChatMemberHandler
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN           = "8668087030:AAFPOsd-6JC5587zkYmZKBYykk7b3ErcccA"
PAYSTACK_SECRET_KEY = "sk_live_da548d75c92cf18e00e849974f3c22b6cf4f41e0"
ADMIN_ID            = 8162426062
BOT_USERNAME        = "MANAGEROFLEAKS_BOT"
BOT_PUBLIC_LINK     = "t.me/MANAGEROFLEAKS_BOT"

# sister bots
SINOBANED_LINK    = "t.me/SINOBANED_BOT"
CALCULUS_LINK     = "t.me/caculus_bot"
MOTHEROFBOTS_LINK = "t.me/MOTHEROFBOTSS_BOT"

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# ── In-memory message tracker: {chat_id: {user_id: [msg_id, ...]}} ─────────
message_tracker: dict[int, dict[int, list[int]]] = {}

def track_message(chat_id: int, user_id: int, msg_id: int):
    if chat_id not in message_tracker:
        message_tracker[chat_id] = {}
    if user_id not in message_tracker[chat_id]:
        message_tracker[chat_id][user_id] = []
    message_tracker[chat_id][user_id].append(msg_id)
    # Keep only last 200 message IDs per user to avoid memory bloat
    if len(message_tracker[chat_id][user_id]) > 200:
        message_tracker[chat_id][user_id] = message_tracker[chat_id][user_id][-200:]

def pop_user_messages(chat_id: int, user_id: int) -> list[int]:
    try:
        ids = message_tracker[chat_id].pop(user_id, [])
        return ids
    except KeyError:
        return []

# ── JSON helpers ────────────────────────────────────────────────────────────
def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def register_user(user):
    users = load_json("manager_users.json")
    uid = str(user.id)
    if uid not in users:
        users[uid] = {
            "id": user.id,
            "name": user.full_name,
            "username": user.username,
            "joined": datetime.now().isoformat()
        }
        save_json("manager_users.json", users)

def register_chat(chat):
    chats = load_json("manager_chats.json")
    cid = str(chat.id)
    if cid not in chats:
        chats[cid] = {
            "id": chat.id,
            "title": chat.title,
            "type": chat.type,
            "added": datetime.now().isoformat()
        }
        save_json("manager_chats.json", chats)
    return chats

# ── Permanent ban list helpers ───────────────────────────────────────────────
def load_banned():
    return load_json("manager_banned.json")

def save_banned(data):
    save_json("manager_banned.json", data)

def add_to_banlist(user_id: int, reason: str = "Manual ban by admin"):
    banned = load_banned()
    banned[str(user_id)] = {
        "user_id": user_id,
        "reason": reason,
        "banned_at": datetime.now().isoformat()
    }
    save_banned(banned)

def remove_from_banlist(user_id: int):
    banned = load_banned()
    banned.pop(str(user_id), None)
    save_banned(banned)

def is_permanently_banned(user_id: int) -> bool:
    banned = load_banned()
    return str(user_id) in banned

# ── Ad messages ─────────────────────────────────────────────────────────────
AD_MESSAGES = [
    (
        "yo fam 👀 you sleeping on these bots fr fr\n\n"
        f"🤖 @SINOBANED_BOT — VIP leaks, exclusive content, connects ur whole gang\n"
        f"🧮 @caculus_bot — build bots, fetch clients, make paper 💸\n"
        f"👑 @MOTHEROFBOTSS_BOT — the goat. signals, forex, crypto, members, CV builder, ALL OF IT\n\n"
        "tap in rn no cap 🔥"
    ),
    (
        "bestie why are you still broke 😭\n\n"
        f"✨ @caculus_bot drops you a Telegram bot for GHS 20\n"
        f"📈 @MOTHEROFBOTSS_BOT hooks you up with bet tips & crypto signals\n"
        f"🔒 @SINOBANED_BOT has the VIP group you need rn\n\n"
        "link in bio (jk just click the names) 💀"
    ),
    (
        "POV: you found the plug 🔌\n\n"
        f"💰 @MOTHEROFBOTSS_BOT — make money, forex, crypto, grow ur Telegram, ALL FREE INFO\n"
        f"🤖 @caculus_bot — build bots, fetch USA/Canada clients, flip GHS 10 to paper\n"
        f"🎯 @SINOBANED_BOT — VIP access, exclusive leaks, real ones only\n\n"
        "not checking these is actually a crime 🚔"
    ),
    (
        "ngl these bots go crazy hard 🔥🔥\n\n"
        f"👑 @SINOBANED_BOT — the OG. join the VIP, you won't regret it\n"
        f"🌍 @caculus_bot — services bot. bot builder + client fetcher + wallet + MORE\n"
        f"📊 @MOTHEROFBOTSS_BOT — signals, tips, investment, social media growth\n\n"
        "we built different no 🧢"
    ),
    (
        "this is your sign to level up ✨\n\n"
        f"💎 VIP content? → @SINOBANED_BOT\n"
        f"🛠 build your own bot? → @caculus_bot (GHS 20 only)\n"
        f"📈 forex/crypto/bet tips? → @MOTHEROFBOTSS_BOT\n\n"
        "the broke era is OVER 💀💀"
    ),
]

# ── Media Queue Helpers ────────────────────────────────────────────────────
def load_media():
    return load_json("manager_media.json")

def save_media(data):
    save_json("manager_media.json", data)

def get_media_state():
    data = load_media()
    if not data:
        return {"items": [], "current_index": 0, "waiting_for_media": False}
    return data

def add_media_item(file_id, file_type, caption=""):
    state = get_media_state()
    state["items"].append({
        "file_id": file_id,
        "type": file_type,
        "caption": caption,
        "added": datetime.now().isoformat()
    })
    state["waiting_for_media"] = False
    save_media(state)

# ── Paystack ────────────────────────────────────────────────────────────────
async def create_payment_link(amount_ghs: int, email: str, ref: str, description: str) -> str | None:
    url = "https://api.paystack.co/transaction/initialize"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}", "Content-Type": "application/json"}
    payload = {
        "email": email,
        "amount": amount_ghs * 100,
        "currency": "GHS",
        "reference": ref,
        "metadata": {"description": description}
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, headers=headers) as r:
                data = await r.json()
                if data.get("status"):
                    return data["data"]["authorization_url"]
    except Exception as e:
        logger.error(f"Paystack error: {e}")
    return None

async def verify_payment(ref: str) -> bool:
    url = f"https://api.paystack.co/transaction/verify/{ref}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers) as r:
                data = await r.json()
                return data.get("data", {}).get("status") == "success"
    except Exception as e:
        logger.error(f"Verify error: {e}")
    return False

# ── Keyboards ───────────────────────────────────────────────────────────────
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Join VIP Groups", callback_data="vip_groups")],
        [InlineKeyboardButton("🤖 Build a Bot Like Me", callback_data="build_bot")],
        [InlineKeyboardButton("➕ Add Me to Your Group/Channel", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")],
        [InlineKeyboardButton("👥 Our Sister Bots", callback_data="sister_bots")],
        [InlineKeyboardButton("📬 Contact Support", callback_data="contact_support")],
        [InlineKeyboardButton("📊 Admin Panel", callback_data="admin_panel")],
    ])

def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]])

# ── /start ──────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    text = (
        f"👋 Welcome, {user.first_name}!\n\n"
        f"I'm *Manager of Leaks* — the bot that keeps your Telegram empire running 🔥\n\n"
        f"I protect your groups, auto-post ads, manage members, and more.\n"
        f"Tap a button to get started 👇"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

# ── /ban ─────────────────────────────────────────────────────────────────────
async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Usage: /ban <user_id> [reason]  — ADMIN ONLY. Permanently bans user from all groups."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return

    args = ctx.args
    if not args:
        await update.message.reply_text(
            "⚠️ *Usage:* `/ban <user_id> [reason]`\n\nExample: `/ban 123456789 spam`",
            parse_mode="Markdown"
        )
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")
        return

    reason = " ".join(args[1:]) if len(args) > 1 else "Banned by admin"

    # Add to permanent ban list
    add_to_banlist(target_id, reason)

    # Ban from every known group/supergroup
    chats = load_json("manager_chats.json")
    banned_in = 0
    msgs_deleted = 0

    for cid_str, chat_info in chats.items():
        if chat_info.get("type") not in ("group", "supergroup"):
            continue
        cid = int(cid_str)
        try:
            await ctx.bot.ban_chat_member(cid, target_id)
            banned_in += 1
        except Exception as e:
            logger.warning(f"Could not ban {target_id} in {cid}: {e}")

        # Delete all tracked messages from this user in this chat
        msg_ids = pop_user_messages(cid, target_id)
        for mid in msg_ids:
            try:
                await ctx.bot.delete_message(cid, mid)
                msgs_deleted += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass

    await update.message.reply_text(
        f"🔨 *Permanent Ban Applied*\n\n"
        f"User ID: `{target_id}`\n"
        f"Reason: {reason}\n"
        f"Banned from: {banned_in} group(s)\n"
        f"Messages deleted: {msgs_deleted}\n\n"
        f"Use `/unban {target_id}` to restore them.",
        parse_mode="Markdown"
    )

# ── /unban ────────────────────────────────────────────────────────────────────
async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Usage: /unban <user_id>  — ADMIN ONLY. Removes permanent ban."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return

    args = ctx.args
    if not args:
        await update.message.reply_text(
            "⚠️ *Usage:* `/unban <user_id>`\n\nExample: `/unban 123456789`",
            parse_mode="Markdown"
        )
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")
        return

    if not is_permanently_banned(target_id):
        await update.message.reply_text(f"ℹ️ User `{target_id}` is not in the permanent ban list.", parse_mode="Markdown")
        return

    remove_from_banlist(target_id)

    # Unban from every known group/supergroup
    chats = load_json("manager_chats.json")
    unbanned_in = 0
    for cid_str, chat_info in chats.items():
        if chat_info.get("type") not in ("group", "supergroup"):
            continue
        cid = int(cid_str)
        try:
            await ctx.bot.unban_chat_member(cid, target_id, only_if_banned=True)
            unbanned_in += 1
        except Exception as e:
            logger.warning(f"Could not unban {target_id} in {cid}: {e}")

    await update.message.reply_text(
        f"✅ *Ban Removed*\n\n"
        f"User ID: `{target_id}`\n"
        f"Unbanned from: {unbanned_in} group(s)\n\n"
        f"They can now rejoin your groups.",
        parse_mode="Markdown"
    )

# ── /banlist ──────────────────────────────────────────────────────────────────
async def cmd_banlist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Shows all permanently banned users. ADMIN ONLY."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return

    banned = load_banned()
    if not banned:
        await update.message.reply_text("✅ No permanently banned users.")
        return

    lines = ["🔨 *Permanent Ban List*\n"]
    for uid, info in banned.items():
        lines.append(
            f"• `{uid}` — {info.get('reason', 'No reason')} "
            f"(banned {info.get('banned_at', '?')[:10]})"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ── /listmedia ──────────────────────────────────────────────────────────────
async def cmd_listmedia(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return
    state = get_media_state()
    items = state.get("items", [])
    idx = state.get("current_index", 0)
    if not items:
        await update.message.reply_text("📭 No media stored. Send me a photo or video in this chat to add to the queue.")
        return
    lines = [f"📋 *Media Queue* ({len(items)} items, next: #{idx + 1})\n"]
    for i, item in enumerate(items):
        marker = "▶️" if i == idx else f"{i+1}."
        cap = f' — "{item["caption"][:30]}..."' if item.get("caption") else ""
        lines.append(f"{marker} {item['type'].upper()}{cap}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ── /clearmedia ─────────────────────────────────────────────────────────────
async def cmd_clearmedia(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return
    save_media({"items": [], "current_index": 0, "waiting_for_media": False})
    await update.message.reply_text("🗑 Media queue cleared!")

# ── /addmedia ───────────────────────────────────────────────────────────────
async def cmd_addmedia(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return
    await update.message.reply_text(
        "📸 *Add Media*\n\nJust send me a photo or video directly in this chat — no command needed.\n"
        "Add a caption if you want it to appear in the group posts 👇",
        parse_mode="Markdown"
    )

# ── Callback router ─────────────────────────────────────────────────────────
async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    if data == "main_menu":
        await query.edit_message_text(
            f"👋 Welcome back, {user.first_name}! Choose an option 👇",
            parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )

    elif data == "vip_groups":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 VIP Group — GHS 10", callback_data="pay_vip")],
            [InlineKeyboardButton("👑 VVIP Group — GHS 30", callback_data="pay_vvip")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
        ])
        await query.edit_message_text(
            "💎 *VIP Membership*\n\nJoin our exclusive VIP/VVIP groups for premium content and leaks 🔥\n\nChoose your tier 👇",
            parse_mode="Markdown", reply_markup=kb
        )

    elif data in ("pay_vip", "pay_vvip"):
        amount = 10 if data == "pay_vip" else 30
        tier = "VIP" if data == "pay_vip" else "VVIP"
        ref = f"manager_{tier.lower()}_{user.id}_{int(datetime.now().timestamp())}"
        email = f"user{user.id}@managerofleaks.bot"
        link = await create_payment_link(amount, email, ref, f"{tier} Membership")
        if link:
            save_pending(ref, {"user_id": user.id, "type": tier, "amount": amount})
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"💳 Pay GHS {amount}", url=link)],
                [InlineKeyboardButton(f"✅ I've Paid — Verify", callback_data=f"verify_{ref}")],
                [InlineKeyboardButton("🔙 Back", callback_data="vip_groups")],
            ])
            await query.edit_message_text(
                f"👑 *{tier} Membership — GHS {amount}*\n\nTap the button below to complete your payment securely via Paystack 👇",
                parse_mode="Markdown", reply_markup=kb
            )
        else:
            await query.edit_message_text("❌ Payment link failed. Try again.", reply_markup=back_keyboard())

    elif data == "build_bot":
        await query.edit_message_text(
            "🤖 *Build a Bot Like Me!*\n\n"
            "I can build you a custom Telegram bot just like this one — group manager, auto-poster, payment system, EVERYTHING.\n\n"
            "💰 Price: *GHS 20*\n\n"
            "Tap below to pay and our team will contact you within 24hrs to get started 🔥",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Pay GHS 20 to Order", callback_data="pay_build_bot")],
                [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
            ])
        )

    elif data == "pay_build_bot":
        ref = f"manager_buildbot_{user.id}_{int(datetime.now().timestamp())}"
        email = f"user{user.id}@managerofleaks.bot"
        link = await create_payment_link(20, email, ref, "Build a Bot Like Me")
        if link:
            save_pending(ref, {"user_id": user.id, "type": "build_bot", "amount": 20})
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Pay GHS 20", url=link)],
                [InlineKeyboardButton("✅ I've Paid — Verify", callback_data=f"verify_{ref}")],
                [InlineKeyboardButton("🔙 Back", callback_data="build_bot")],
            ])
            await query.edit_message_text(
                "🤖 *Bot Order — GHS 20*\n\nComplete payment below and our dev team contacts you within 24hrs 🔥",
                parse_mode="Markdown", reply_markup=kb
            )
        else:
            await query.edit_message_text("❌ Payment link failed. Try again.", reply_markup=back_keyboard())

    elif data == "sister_bots":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔒 @SINOBANED_BOT — VIP Leaks", url=f"https://{SINOBANED_LINK}")],
            [InlineKeyboardButton("🧮 @caculus_bot — Services & Clients", url=f"https://{CALCULUS_LINK}")],
            [InlineKeyboardButton("👑 @MOTHEROFBOTSS_BOT — The GOAT Bot", url=f"https://{MOTHEROFBOTS_LINK}")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
        ])
        await query.edit_message_text(
            "👥 *Our Sister Bots*\n\nCheck out our full ecosystem 🔥",
            parse_mode="Markdown", reply_markup=kb
        )

    elif data == "contact_support":
        await query.edit_message_text(
            "📬 *Contact Support*\n\n"
            "Need help? Reach out directly 👇\n\n"
            "💬 Click the button below to open a DM with our support team.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Message Support", url="https://t.me/SINOBANED_BOT")],
                [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
            ])
        )

    elif data == "admin_panel":
        if user.id != ADMIN_ID:
            await query.answer("❌ Admins only!", show_alert=True)
            return
        users_data = load_json("manager_users.json")
        chats_data = load_json("manager_chats.json")
        pays       = load_json("manager_payments.json")
        banned     = load_banned()
        revenue    = sum(p.get("amount", 0) for p in pays.values() if p.get("paid"))
        media_state = get_media_state()
        media_count = len(media_state.get("items", []))
        media_idx   = media_state.get("current_index", 0)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
            [InlineKeyboardButton("📋 List Media", callback_data="admin_listmedia")],
            [InlineKeyboardButton("🗑 Clear Media", callback_data="admin_clearmedia")],
            [InlineKeyboardButton("🔨 Ban List", callback_data="admin_banlist")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
        ])
        await query.edit_message_text(
            f"🛠 *Admin Panel*\n\n"
            f"👤 Total Users: {len(users_data)}\n"
            f"💬 Groups/Channels: {len(chats_data)}\n"
            f"💰 Total Revenue: GHS {revenue}\n"
            f"✅ Payments: {sum(1 for p in pays.values() if p.get('paid'))}\n"
            f"📸 Media Queue: {media_count} items (next: #{media_idx + 1})\n"
            f"🔨 Permanently Banned: {len(banned)} users",
            parse_mode="Markdown", reply_markup=kb
        )

    elif data == "admin_broadcast":
        if user.id != ADMIN_ID:
            await query.answer("❌ Admins only!", show_alert=True)
            return
        ctx.user_data["awaiting_broadcast"] = True
        await query.edit_message_text(
            "📢 *Broadcast Mode*\n\nSend your message now (text, image, video, anything).\nI'll forward it to all groups and channels.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]])
        )

    elif data == "admin_listmedia":
        if user.id != ADMIN_ID:
            await query.answer("❌ Admins only!", show_alert=True)
            return
        state = get_media_state()
        items = state.get("items", [])
        idx = state.get("current_index", 0)
        if not items:
            await query.edit_message_text(
                "📭 *No Media Stored*\n\nSend me a photo or video in this private chat to add to the queue.",
                parse_mode="Markdown", reply_markup=back_keyboard()
            )
            return
        lines = [f"📋 *Media Queue* ({len(items)} items, next: #{idx + 1})\n"]
        for i, item in enumerate(items):
            marker = "▶️" if i == idx else f"{i+1}."
            cap = f' — "{item["caption"][:30]}..."' if item.get("caption") else ""
            lines.append(f"{marker} {item['type'].upper()}{cap}")
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=back_keyboard())

    elif data == "admin_clearmedia":
        if user.id != ADMIN_ID:
            await query.answer("❌ Admins only!", show_alert=True)
            return
        save_media({"items": [], "current_index": 0, "waiting_for_media": False})
        await query.edit_message_text("🗑 *Media queue cleared!*", parse_mode="Markdown", reply_markup=back_keyboard())

    elif data == "admin_banlist":
        if user.id != ADMIN_ID:
            await query.answer("❌ Admins only!", show_alert=True)
            return
        banned = load_banned()
        if not banned:
            await query.edit_message_text("✅ *No permanently banned users.*", parse_mode="Markdown", reply_markup=back_keyboard())
            return
        lines = ["🔨 *Permanent Ban List*\n"]
        for uid, info in banned.items():
            lines.append(
                f"• `{uid}` — {info.get('reason', 'No reason')} "
                f"({info.get('banned_at', '?')[:10]})"
            )
        lines.append(f"\n_Use /unban <user_id> to restore someone._")
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=back_keyboard())

    elif data.startswith("verify_"):
        ref = data[7:]
        paid = await verify_payment(ref)
        pending = load_json("manager_pending.json")
        info = pending.get(ref, {})
        if paid:
            payments = load_json("manager_payments.json")
            payments[ref] = {**info, "paid": True, "time": datetime.now().isoformat()}
            save_json("manager_payments.json", payments)
            if ref in pending:
                del pending[ref]
                save_json("manager_pending.json", pending)
            ptype = info.get("type", "")
            if ptype == "VIP":
                msg = "💎 *VIP Access Granted!*\n\nWelcome to the VIP family! Our team will add you to the VIP group within 1 hour. Contact @SINOBANED_BOT for your invite link 🔥"
            elif ptype == "VVIP":
                msg = "👑 *VVIP Access Granted!*\n\nElite status unlocked! Our team will add you to the VVIP group within 1 hour. Contact @SINOBANED_BOT for your invite link 🔥"
            elif ptype == "build_bot":
                msg = "🤖 *Bot Order Confirmed!*\n\nPayment received! Our dev team will contact you within 24 hours to start building your bot 🔥"
            else:
                msg = "✅ *Payment Confirmed!*\n\nThank you! Our team will be in touch shortly 🔥"
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_keyboard())
            try:
                await ctx.bot.send_message(
                    ADMIN_ID,
                    f"💰 *New Payment!*\n\nUser: {user.full_name} (@{user.username})\nID: {user.id}\nType: {ptype}\nAmount: GHS {info.get('amount', '?')}\nRef: {ref}",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            await query.edit_message_text(
                "❌ *Payment Not Found*\n\nPlease complete the payment first, then tap verify again.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data=data)],
                    [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
                ])
            )

def save_pending(ref, data):
    pending = load_json("manager_pending.json")
    pending[ref] = data
    save_json("manager_pending.json", pending)

# ── New member joined group ─────────────────────────────────────────────────
async def member_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if result is None:
        return
    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status
    chat = result.chat

    if new_status in ("member", "restricted") and old_status in ("left", "kicked"):
        new_member = result.new_chat_member.user
        register_chat(chat)

        # Block permanently banned users from rejoining
        if is_permanently_banned(new_member.id):
            try:
                await ctx.bot.ban_chat_member(chat.id, new_member.id)
                logger.info(f"Re-banned permanently banned user {new_member.id} who tried to rejoin {chat.id}")
            except Exception as e:
                logger.error(f"Re-ban error: {e}")
            return

        if new_member.is_bot:
            try:
                await ctx.bot.ban_chat_member(chat.id, new_member.id)
                await ctx.bot.send_message(
                    chat.id,
                    f"🚫 Bot @{new_member.username} was automatically removed. Bots are not allowed here.",
                )
            except Exception:
                pass

async def join_request_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request

    # Block permanently banned users from join requests
    if is_permanently_banned(req.from_user.id):
        try:
            await ctx.bot.decline_chat_join_request(req.chat.id, req.from_user.id)
        except Exception as e:
            logger.error(f"Decline join request error: {e}")
        return

    try:
        await ctx.bot.approve_chat_join_request(req.chat.id, req.from_user.id)
        register_chat(req.chat)
        register_user(req.from_user)
    except Exception as e:
        logger.error(f"Join approve error: {e}")

# ── Message handler: guard + media store + broadcast ───────────────────────
async def message_guard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    user = msg.from_user
    if not user:
        return

    # ── ADMIN in private chat: store media or broadcast ────────────────
    if user.id == ADMIN_ID and msg.chat.type == "private":

        if msg.photo:
            file_id = msg.photo[-1].file_id
            caption = msg.caption or ""
            add_media_item(file_id, "photo", caption)
            state = get_media_state()
            await msg.reply_text(
                f"✅ *Photo stored!* Queue now has {len(state['items'])} item(s).\n"
                f"Use /listmedia to review or /clearmedia to reset.",
                parse_mode="Markdown"
            )
            return

        if msg.video:
            file_id = msg.video.file_id
            caption = msg.caption or ""
            add_media_item(file_id, "video", caption)
            state = get_media_state()
            await msg.reply_text(
                f"✅ *Video stored!* Queue now has {len(state['items'])} item(s).\n"
                f"Use /listmedia to review or /clearmedia to reset.",
                parse_mode="Markdown"
            )
            return

        if ctx.user_data.get("awaiting_broadcast"):
            ctx.user_data["awaiting_broadcast"] = False
            chats = load_json("manager_chats.json")
            sent = 0
            failed = 0
            for cid in chats:
                try:
                    await msg.forward(int(cid))
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception:
                    failed += 1
            await msg.reply_text(f"📢 Broadcast done!\n✅ Sent: {sent}\n❌ Failed: {failed}")
            return

    # ── Group message: track message IDs ──────────────────────────────
    if msg.chat.type in ("group", "supergroup") and msg.message_id:
        track_message(msg.chat.id, user.id, msg.message_id)

    # ── Admin is exempt from all group rules ──────────────────────────
    if user.id == ADMIN_ID:
        return

    text = msg.text or msg.caption or ""
    has_link = (
        "t.me/" in text or
        "http://" in text or
        "https://" in text or
        ("@" in text and any(e.type == "mention" for e in (msg.entities or [])))
    )

    if has_link and msg.chat.type in ("group", "supergroup"):
        try:
            # Delete the offending message immediately
            await msg.delete()

            # Also delete all tracked messages from this user in this chat
            msg_ids = pop_user_messages(msg.chat.id, user.id)
            for mid in msg_ids:
                try:
                    await ctx.bot.delete_message(msg.chat.id, mid)
                    await asyncio.sleep(0.05)
                except Exception:
                    pass

            # Ban for 45 minutes (2700 seconds)
            until = int(datetime.now().timestamp()) + 2700
            await ctx.bot.ban_chat_member(
                msg.chat.id,
                user.id,
                until_date=until
            )

            # Send warning in group
            warn = await ctx.bot.send_message(
                msg.chat.id,
                f"🚫 {user.full_name} has been banned for 45 minutes and all their messages removed. No links allowed here! 🔒"
            )

            # Auto-delete the warning after 30 seconds
            await asyncio.sleep(30)
            try:
                await warn.delete()
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Ban error: {e}")

# ── Auto-post: media queue or fallback to ad ──────────────────────────────
async def auto_post(ctx: ContextTypes.DEFAULT_TYPE):
    chats = load_json("manager_chats.json")
    if not chats:
        return

    state = get_media_state()
    items = state.get("items", [])
    idx   = state.get("current_index", 0)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 @MOTHEROFBOTSS_BOT", url=f"https://{MOTHEROFBOTS_LINK}")],
        [InlineKeyboardButton("🔒 @SINOBANED_BOT",     url=f"https://{SINOBANED_LINK}")],
        [InlineKeyboardButton("🧮 @caculus_bot",        url=f"https://{CALCULUS_LINK}")],
    ])

    if items:
        item = items[idx]
        caption = item.get("caption", "")
        footer  = "\n\n👇 Check out our bots 👇"
        full_caption = (caption + footer) if caption else footer.strip()

        for cid in chats:
            try:
                if item["type"] == "photo":
                    await ctx.bot.send_photo(int(cid), item["file_id"], caption=full_caption, reply_markup=kb)
                else:
                    await ctx.bot.send_video(int(cid), item["file_id"], caption=full_caption, reply_markup=kb)
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"Media post failed for {cid}: {e}")

        next_idx = idx + 1
        if next_idx >= len(items):
            save_media({"items": [], "current_index": 0, "waiting_for_media": True})
            try:
                await ctx.bot.send_message(
                    ADMIN_ID,
                    "✅ *Media cycle complete!*\n\nAll stored media has been posted.\n\n"
                    "📸 Send me a new photo or video to keep posting, or I'll stay quiet next cycle.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            state["current_index"] = next_idx
            save_media(state)

    else:
        waiting = state.get("waiting_for_media", False)
        if not waiting:
            state["waiting_for_media"] = True
            save_media(state)
            try:
                await ctx.bot.send_message(
                    ADMIN_ID,
                    "📭 *I need media to post!*\n\nNo photos or videos are stored in my queue.\n\n"
                    "Send me a photo or video here to start the next cycle 👇",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

# ── Bot added to group ──────────────────────────────────────────────────────
async def my_chat_member(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if result is None:
        return
    new_status = result.new_chat_member.status
    chat = result.chat
    if new_status in ("administrator", "member"):
        register_chat(chat)
        try:
            await ctx.bot.send_message(
                chat.id,
                f"👋 Hey fam! *Manager of Leaks* is now live in *{chat.title}* 🔥\n\n"
                f"I'll keep this group clean and auto-post updates regularly.\n\n"
                f"Check out our full ecosystem 👇",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 @MOTHEROFBOTSS_BOT", url=f"https://{MOTHEROFBOTS_LINK}")],
                    [InlineKeyboardButton("🔒 @SINOBANED_BOT",     url=f"https://{SINOBANED_LINK}")],
                    [InlineKeyboardButton("🧮 @caculus_bot",        url=f"https://{CALCULUS_LINK}")],
                ])
            )
        except Exception:
            pass

# ── Main ────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("ban",        cmd_ban))
    app.add_handler(CommandHandler("unban",      cmd_unban))
    app.add_handler(CommandHandler("banlist",    cmd_banlist))
    app.add_handler(CommandHandler("listmedia",  cmd_listmedia))
    app.add_handler(CommandHandler("clearmedia", cmd_clearmedia))
    app.add_handler(CommandHandler("addmedia",   cmd_addmedia))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(ChatMemberHandler(member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, message_guard))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_guard))

    # Auto-post every 17 minutes (1020 seconds)
    app.job_queue.run_repeating(auto_post, interval=1020, first=60)

    print("🔥 Manager of Leaks bot is running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()