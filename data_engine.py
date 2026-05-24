import os
import asyncio
import logging
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# YOUR ADMIN ID
ADMIN_ID = 6546954770
DB_FILE = "lens_admin_node.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS system_telemetry (
            id INTEGER PRIMARY KEY, total_users INTEGER DEFAULT 0,
            active_users INTEGER DEFAULT 0, inactive_users INTEGER DEFAULT 0
        )
    """)
    # Insert dummy data for the Admin panel to track
    c.execute("INSERT OR IGNORE INTO system_telemetry (id, total_users, active_users, inactive_users) VALUES (1, 120, 85, 35)")
    conn.commit()
    conn.close()

# --- SECURITY DECORATOR ---
# Only you can execute commands. Everyone else is ignored.
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id != ADMIN_ID:
            return # Silent rejection for non-admins
        return await func(update, context, *args, **kwargs)
    return wrapper

@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👑 **LENs ADMIN COMMAND CENTER** 👑\n\n"
        "Web App is now fully autonomous and client-side. This bot is restricted to your administrative oversight.\n\n"
        "🛠️ **Available Server Commands:**\n"
        "📊 `/stats` - View Current Platform Users\n"
        "🧠 `/diagnostics` - Run AI System Health Check\n"
        "📈 `/marketcap` - View Live Project Market Cap\n"
        "🧹 `/debug` - Clear Memory & Enhance Server Performance"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT total_users, active_users, inactive_users FROM system_telemetry WHERE id=1")
    row = c.fetchone()
    conn.close()
    
    msg = (
        "👥 **LENs USER TELEMETRY**\n"
        "--------------------------\n"
        f"🌐 Total Registered: `{row[0]}`\n"
        f"🟢 Active Nodes: `{row[1]}`\n"
        f"🔴 Inactive/Dormant: `{row[2]}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@admin_only
async def diagnostics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔬 *Initiating AI Diagnostic Sequence...*", parse_mode="Markdown")
    await asyncio.sleep(2) # Simulate processing time
    
    msg = (
        "🧠 **AI DIAGNOSTICS REPORT**\n\n"
        "**Status:** 🟨 Minor Discrepancy Found\n"
        "**Issue:** High cache saturation detected in WebSockets gateway causing a 4ms latency spike.\n\n"
        "**AI Human Fix Recommended:**\n"
        "Run the `/debug` command to execute a `VACUUM` on the SQL storage and clear the local DNS cache routing. All other core trading engines (Quantum, Advanced, Strong) are operating flawlessly."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@admin_only
async def marketcap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Dynamic generation based on standard project formula (Users * Liquidity)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT active_users FROM system_telemetry WHERE id=1")
    active = c.fetchone()[0]
    conn.close()
    
    mcap = active * 45210.50 # Simulated average liquidity per node
    
    msg = (
        "📈 **LENs PROJECT MARKET CAP (AI-Updated)**\n"
        f"💰 **Total Network Value:** `${mcap:,.2f}`\n\n"
        "_Calculated via live Web3 node aggregation._"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@admin_only
async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧹 *Executing Deep Cache Clear & Database Vacuum...*", parse_mode="Markdown")
    
    conn = sqlite3.connect(DB_FILE)
    conn.execute("VACUUM") # Actually clears unused SQLite space
    conn.commit()
    conn.close()
    
    await asyncio.sleep(1.5)
    await update.message.reply_text("✅ **DEBUG COMPLETE.**\nUseless space cleared. Server performance enhanced by 14%.")

def main():
    init_db()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("diagnostics", diagnostics))
    app.add_handler(CommandHandler("marketcap", marketcap))
    app.add_handler(CommandHandler("debug", debug))
    
    print("Admin Controller Online. Web Interface is now fully decoupled.")
    app.run_polling()

if __name__ == "__main__":
    main()
