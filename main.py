import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# تنظیمات Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# خواندن متغیرهای محیطی
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip().lstrip("@").lower()

DB_PATH = "bot_database.db"

# راه‌اندازی و ساخت جداول دیتابیس SQLite
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # جدول کاربران
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            language_code TEXT,
            first_seen TEXT,
            last_seen TEXT,
            message_count INTEGER DEFAULT 0,
            last_interaction TEXT
        )
    """)
    
    # جدول پیام‌ها / تعاملات
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            interaction_type TEXT,
            message_text TEXT,
            timestamp TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

def is_admin(username: str) -> bool:
    if not ADMIN_USERNAME or not username:
        return False
    return username.strip().lstrip("@").lower() == ADMIN_USERNAME

def log_user_interaction(user, interaction_type: str, text: str = None):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # بررسی وجود کاربر
    cursor.execute("SELECT user_id, message_count FROM users WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    
    uname = user.username.lower() if user.username else None
    fname = user.first_name if user.first_name else ""
    lname = user.last_name if user.last_name else ""
    lang = user.language_code if user.language_code else ""
    
    if row:
        new_count = row[1] + 1
        cursor.execute("""
            UPDATE users SET 
                username = ?, 
                first_name = ?, 
                last_name = ?, 
                language_code = ?, 
                last_seen = ?, 
                message_count = ?, 
                last_interaction = ?
            WHERE user_id = ?
        """, (uname, fname, lname, lang, now, new_count, interaction_type, user.id))
    else:
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, language_code, first_seen, last_seen, message_count, last_interaction)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (user.id, uname, fname, lname, lang, now, now, interaction_type))
        
    # ثبت متن تعامل در صورت وجود
    if text:
        cursor.execute("""
            INSERT INTO messages (user_id, interaction_type, message_text, timestamp)
            VALUES (?, ?, ?, ?)
        """, (user.id, interaction_type, text[:1000], now))
        
    conn.commit()
    conn.close()

# هندلر دستور /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_user_interaction(user, "command_start", "/start")
    
    user_name = user.username.lower() if user.username else ""
    is_user_admin = is_admin(user_name)
    
    if is_user_admin:
        keyboard = [
            [InlineKeyboardButton("👤 دریافت مشخصات خود", callback_data="self_info")],
            [InlineKeyboardButton("👥 دریافت مشخصات بقیه کاربران", callback_data="admin_users_1")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("👤 دریافت مشخصات خود", callback_data="self_info")]
        ]
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"سلام {user.first_name} عزیز!\nبه ربات مدیریت و اطلاعات خوش آمدید.",
        reply_markup=reply_markup
    )

# هندلر عمومی پیام‌ها برای ثبت فعالیت
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    
    user = update.effective_user
    msg = update.message
    
    # تشخیص نوع تعامل
    if msg.text:
        inter_type = "text"
        content = msg.text
    elif msg.photo:
        inter_type = "photo"
        content = msg.caption or "[عکس]"
    elif msg.video:
        inter_type = "video"
        content = msg.caption or "[ویدیو]"
    elif msg.document:
        inter_type = "document"
        content = msg.caption or "[فایل]"
    elif msg.sticker:
        inter_type = "sticker"
        content = f"[استیکر: {msg.sticker.emoji}]" if msg.sticker.emoji else "[استیکر]"
    elif msg.voice:
        inter_type = "voice"
        content = "[پیام صوتی]"
    elif msg.location:
        inter_type = "location"
        content = f"Lat: {msg.location.latitude}, Lon: {msg.location.longitude}"
    elif msg.contact:
        inter_type = "contact"
        content = f"Contact: {msg.contact.first_name} ({msg.contact.phone_number})"
    else:
        inter_type = "other"
        content = "[سایر تعاملات]"
        
    log_user_interaction(user, inter_type, content)
    
    # پاسخ ساده به کاربر برای اینکه بداند ربات فعال است
    await msg.reply_text("پیام شما دریافت و ثبت شد. برای دسترسی به منو از /start استفاده کنید.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_name = user.username.lower() if user.username else ""
    data = query.data
    
    log_user_interaction(user, f"callback_{data}")
    
    # اطلاعات خود کاربر
    if data == "self_info":
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT first_name, last_name, username, user_id, language_code, first_seen, last_seen, message_count, last_interaction FROM users WHERE user_id = ?", (user.id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            text = (
                f"👤 **مشخصات شما:**\n\n"
                f"👤 First Name: {row[0]}\n"
                f"📝 Last Name: {row[1] or 'ندارد'}\n"
                f"🔹 Username: @{row[2] if row[2] else 'ندارد'}\n"
                f"🆔 Numeric ID: `{row[3]}`\n"
                f"🌐 Language: {row[4] or 'نامشخص'}\n"
                f"📅 First Seen: {row[5]}\n"
                f"🕐 Last Seen: {row[6]}\n"
                f"💬 Message Count: {row[7]}\n"
                f"📨 Last Interaction: {row[8]}"
            )
        else:
            text = "اطلاعاتی از شما یافت نشد. لطفا /start را بزنید."
            
        keyboard = [[InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    # بازگشت به منوی اصلی
    if data == "back_to_menu":
        is_adm = is_admin(user_name)
        if is_adm:
            keyboard = [
                [InlineKeyboardButton("👤 دریافت مشخصات خود", callback_data="self_info")],
                [InlineKeyboardButton("👥 دریافت مشخصات بقیه کاربران", callback_data="admin_users_1")]
            ]
        else:
            keyboard = [[InlineKeyboardButton("👤 دریافت مشخصات خود", callback_data="self_info")]]
            
        await query.edit_message_text("منوی اصلی ربات:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # بخش مدیریت کاربران (نیاز به احراز هویت دقیق مدیر)
    if data.startswith("admin_users_") or data.startswith("admin_user_detail_") or data.startswith("admin_user_msgs_"):
        if not is_admin(user_name):
            await query.answer("خطا: شما اجازه دسترسی به این بخش را ندارید!", show_alert=True)
            await query.edit_message_text("⛔ دسترسی غیرمجاز (Access Denied)")
            return

        # لیست کاربران با Pagination (صفحه بندی ۵تایی)
        if data.startswith("admin_users_"):
            page = int(data.split("_")[2])
            limit = 5
            offset = (page - 1) * limit
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT user_id, first_name, username FROM users ORDER BY last_seen DESC LIMIT ? OFFSET ?", (limit, offset))
            users = cursor.fetchall()
            conn.close()
            
            total_pages = max(1, (total_users + limit - 1) // limit)
            
            keyboard = []
            for u in users:
                display_name = f"👤 {u[1]}" + (f" (@{u[2]})" if u[2] else "")
                keyboard.append([InlineKeyboardButton(display_name, callback_data=f"admin_user_detail_{u[0]}_{page}")])
                
            # دکمه‌های صفحه‌بندی
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_users_{page - 1}"))
            
            nav_buttons.append(InlineKeyboardButton(f"صفحه {page}/{total_pages}", callback_data="noop"))
            
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"admin_users_{page + 1}"))
                
            if nav_buttons:
                keyboard.append(nav_buttons)
                
            keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل مدیر", callback_data="back_to_menu")])
            
            await query.edit_message_text(
                f"👥 **لیست کاربران ربات (کل: {total_users}):**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return

        # جزئیات کاربر خاص
        if data.startswith("admin_user_detail_"):
            parts = data.split("_")
            target_user_id = int(parts[3])
            return_page = parts[4] if len(parts) > 4 else "1"
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT first_name, last_name, username, user_id, language_code, first_seen, last_seen, message_count, last_interaction FROM users WHERE user_id = ?", (target_user_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                text = (
                    f"👤 **مشخصات کاربر:**\n\n"
                    f"👤 First Name: {row[0]}\n"
                    f"📝 Last Name: {row[1] or 'ندارد'}\n"
                    f"🔹 Username: @{row[2] if row[2] else 'ندارد'}\n"
                    f"🆔 Numeric ID: `{row[3]}`\n"
                    f"🌐 Language: {row[4] or 'نامشخص'}\n"
                    f"📅 First Seen: {row[5]}\n"
                    f"🕐 Last Seen: {row[6]}\n"
                    f"💬 Message Count: {row[7]}\n"
                    f"📨 Last Interaction: {row[8]}"
                )
                keyboard = [
                    [InlineKeyboardButton("💬 مشاهده پیام‌های ثبت‌شده", callback_data=f"admin_user_msgs_{target_user_id}_{return_page}")],
                    [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data=f"admin_users_{return_page}")]
                ]
            else:
                text = "کاربر مورد نظر یافت نشد."
                keyboard = [[InlineKeyboardButton("🔙 بازگشت به لیست", callback_data=f"admin_users_{return_page}")]]
                
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        # مشاهده پیام‌های ذخیره شده کاربر
        if data.startswith("admin_user_msgs_"):
            parts = data.split("_")
            target_user_id = int(parts[3])
            return_page = parts[4] if len(parts) > 4 else "1"
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT interaction_type, message_text, timestamp FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT 10", (target_user_id,))
            msgs = cursor.fetchall()
            conn.close()
            
            text = f"💬 **آخرین پیام‌ها/تعاملات کاربر (`{target_user_id}`):**\n\n"
            if msgs:
                for m in msgs:
                    text += f"▪️ [{m[0]}] ({m[2]}):\n{m[1]}\n-------------------\n"
            else:
                text += "هیچ پیامی ثبت نشده است."
                
            keyboard = [[InlineKeyboardButton("🔙 بازگشت به مشخصات کاربر", callback_data=f"admin_user_detail_{target_user_id}_{return_page}")]]
            
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

def main():
    if not BOT_TOKEN:
        logger.error("متغیر محیطی BOT_TOKEN تنظیم نشده است!")
        return

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    logger.info("ربات در حال اجراست...")
    application.run_polling()

if __name__ == "__main__":
    main()

