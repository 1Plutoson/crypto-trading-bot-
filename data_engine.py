import os
import asyncio
import logging
import json
import urllib.request
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
if isinstance(ENCRYPTION_KEY, str):
    if not ENCRYPTION_KEY.startswith("b'") and not isinstance(ENCRYPTION_KEY, bytes):
        pass
cipher_suite = Fernet(ENCRYPTION_KEY if isinstance(ENCRYPTION_KEY, bytes) else ENCRYPTION_KEY.encode())

ADMIN_ID = 6546954770
DB_FILE = "lens_pro_database.db"
WEB_APP_URL = "https://1plutoson.github.io/crypto-trading-bot-/"

crypto_prices = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0, "BNB": 0.0}

def run_query(query: str, params: tuple = (), fetch: str = None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        if fetch == "one": return cursor.fetchone()
        elif fetch == "all": return cursor.fetchall()
        else: conn.commit()
    finally:
        conn.close()

# --- UPGRADED DATABASE CORE ---
def init_db():
    # 1. Base User Table
    run_query("""
        CREATE TABLE IF NOT EXISTS user_states (
            user_id INTEGER PRIMARY KEY, account_mode TEXT, demo_balance REAL, real_balance REAL,
            is_strategy_active INTEGER, wallet_connected INTEGER, wallet_address TEXT, wallet_provider TEXT,
            encrypted_private_key TEXT, allocated_trade_capital REAL, risk_profile TEXT, demo_positions TEXT,
            real_positions TEXT, closed_history TEXT, last_seen_onchain_bal REAL
        )
    """)
    # 2. Advanced Tracking Columns (Safely added if they don't exist yet)
    try: run_query("ALTER TABLE user_states ADD COLUMN total_trades INTEGER DEFAULT 0")
    except: pass
    try: run_query("ALTER TABLE user_states ADD COLUMN ai_optimization INTEGER DEFAULT 0")
    except: pass

    # 3. Global System Settings Table
    run_query("CREATE TABLE IF NOT EXISTS system_config (key TEXT PRIMARY KEY, value TEXT)")
    run_query("INSERT OR IGNORE INTO system_config VALUES ('maintenance_mode', '0')")

def is_maintenance_active():
    res = run_query("SELECT value FROM system_config WHERE key = 'maintenance_mode'", fetch="one")
    return res and res[0] == '1'

def toggle_maintenance():
    current = is_maintenance_active()
    new_val = '0' if current else '1'
    run_query("UPDATE system_config SET value = ? WHERE key = 'maintenance_mode'", (new_val,))
    return new_val == '1'

def get_user_state(user_id: int) -> dict:
    row = run_query("SELECT * FROM user_states WHERE user_id = ?", (user_id,), fetch="one")
    if row:
        return {
            "account_mode": row[1], "demo_balance": float(row[2]) if row[2] is not None else 1000.00,
            "real_balance": float(row[3]) if row[3] is not None else 0.00,
            "is_strategy_active": bool(row[4]), "wallet_connected": bool(row[5]),
            "wallet_address": row[6] or "Not Connected", "wallet_provider": row[7],
            "encrypted_private_key": row[8].encode('utf-8') if row[8] else None,
            "allocated_trade_capital": float(row[9]) if row[9] is not None else 10.00,
            "risk_profile": row[10] or "MID",
            "demo_positions": json.loads(row[11]) if row[11] else {},
            "real_positions": json.loads(row[12]) if row[12] else {},
            "closed_history": json.loads(row[13]) if row[13] else [],
            "last_seen_onchain_bal": float(row[14]) if row[14] is not None else 0.00,
            "total_trades": int(row[15]) if len(row) > 15 and row[15] is not None else 0,
            "ai_optimization": bool(row[16]) if len(row) > 16 and row[16] is not None else False
        }
    else:
        run_query("INSERT INTO user_states (user_id, account_mode, demo_balance, real_balance, is_strategy_active, wallet_connected, wallet_address, allocated_trade_capital, risk_profile, demo_positions, real_positions, closed_history, last_seen_onchain_bal, total_trades, ai_optimization) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                  (user_id, "DEMO", 1000.00, 0.00, 0, 0, "Not Connected", 10.00, "MID", "{}", "{}", "[]", 0.00, 0, 0))
        return get_user_state(user_id)

def save_user_state(user_id: int, state: dict):
    enc_key_str = state["encrypted_private_key"].decode('utf-8') if state["encrypted_private_key"] else None
    run_query("""
        UPDATE user_states SET
            account_mode = ?, demo_balance = ?, real_balance = ?, is_strategy_active = ?, wallet_connected = ?,
            wallet_address = ?, wallet_provider = ?, encrypted_private_key = ?, allocated_trade_capital = ?,
            risk_profile = ?, demo_positions = ?, real_positions = ?, closed_history = ?, last_seen_onchain_bal = ?,
            total_trades = ?, ai_optimization = ?
        WHERE user_id = ?
    """, (
        state["account_mode"], state["demo_balance"], state["real_balance"], int(state["is_strategy_active"]),
        int(state["wallet_connected"]), state["wallet_address"], state["wallet_provider"], enc_key_str,
        state["allocated_trade_capital"], state["risk_profile"], json.dumps(state["demo_positions"]),
        json.dumps(state["real_positions"]), json.dumps(state["closed_history"]), state["last_seen_onchain_bal"],
        state["total_trades"], int(state["ai_optimization"]), user_id
    ))

async def fetch_resilient_prices():
    while True:
        for url in ["https://api.binance.com/api/v3/ticker/price"]:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                loop = asyncio.get_running_loop()
                def fetch_data():
                    with urllib.request.urlopen(req, timeout=5) as response:
                        if response.status == 200: return json.loads(response.read().decode())
                    return None
                data = await loop.run_in_executor(None, fetch_data)
                if data:
                    for item in data:
                        sym = item.get("symbol", "").replace("USDT", "")
                        if sym in crypto_prices: crypto_prices[sym] = float(item.get("price", 0.0))
            except Exception: pass
        await asyncio.sleep(5)

# --- SECURITY INTERCEPTOR ---
async def check_maintenance(update: Update) -> bool:
    if update.effective_user.id != ADMIN_ID and is_maintenance_active():
        await update.message.reply_text("⚠️ **SYSTEM MAINTENANCE ACTIVE**\n\nThe AI network is currently undergoing scheduled optimization and diagnostics. Functions are temporarily frozen. Please stand by.")
        return True
    return False

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_maintenance(update): return
    state = get_user_state(update.effective_user.id)
    reply_markup = ReplyKeyboardMarkup.from_button(KeyboardButton(text="🚀 Open LENS Terminal", web_app=WebAppInfo(url=WEB_APP_URL)), resize_keyboard=True)
    msg = (
        "🔥 **LENS INSTITUTIONAL PRO TERMINAL v13.0** 🔥\n"
        f"💳 **Server Mode:** `{state['account_mode']}` | 🧠 **AI Active:** `{'🟢 ON' if state['ai_optimization'] else '🔴 OFF'}`\n"
        f"🛡️ **Total Neural Trades Executed:** `{state['total_trades']}`\n"
        "---------------------------------------\n"
        "✨ /optimize - Toggle AI Auto-Optimization Suite\n"
        "💼 /wallet - Check Isolated Balances & Sync\n"
        "🤖 /autotrade [amount] - Deploy Pro Strategy\n"
        "📊 /positions - Isolated Portfolio View\n"
        "👑 /admin - (Admin Access Only)"
    )
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")

async def toggle_optimization(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_maintenance(update): return
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    state["ai_optimization"] = not state["ai_optimization"]
    save_user_state(user_id, state)
    status = "🟢 ACTIVATED" if state["ai_optimization"] else "🔴 DEACTIVATED"
    await update.message.reply_text(f"✨ **AI Optimization Suite {status}**\nYour account routing and structural risk curves will now be dynamically adjusted.")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    keyboard = [
        [InlineKeyboardButton("🔬 Run AI System Diagnostics", callback_data="admin_diag")],
        [InlineKeyboardButton(f"🛠 Toggle Maintenance Mode ({'ON' if is_maintenance_active() else 'OFF'})", callback_data="admin_maint")],
        [InlineKeyboardButton("🪱 Debug Global Ecosystem", callback_data="admin_debug")],
        [InlineKeyboardButton("⚡ Force Global Auto-Optimize", callback_data="admin_opt_all")]
    ]
    await update.message.reply_text("👑 **LENS ADVANCED ADMINISTRATION CORE**", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    await query.answer()
    data = query.data

    # --- NEW ADMIN ROUTES ---
    if data == "admin_diag" and user_id == ADMIN_ID:
        users = run_query("SELECT COUNT(*) FROM user_states", fetch="one")[0]
        total_trades = run_query("SELECT SUM(total_trades) FROM user_states", fetch="one")[0] or 0
        total_demo = run_query("SELECT SUM(demo_balance) FROM user_states", fetch="one")[0] or 0
        total_real = run_query("SELECT SUM(real_balance) FROM user_states", fetch="one")[0] or 0
        await query.edit_message_text(f"🔬 **AI Diagnostics Matrix**\n• Active Nodes: `{users}`\n• Total Trades Fired: `{total_trades}`\n• Demo Liquidity: `${total_demo:,.2f}`\n• Real Liquidity: `${total_real:,.2f}`\n• Matrix Status: 🟩 Optimal", parse_mode="Markdown")
        return

    if data == "admin_maint" and user_id == ADMIN_ID:
        is_on = toggle_maintenance()
        await query.edit_message_text(f"🛠 **Maintenance State Altered.**\nSystem is now: `{'LOCKED 🔴' if is_on else 'LIVE 🟢'}`", parse_mode="Markdown")
        return

    if data == "admin_opt_all" and user_id == ADMIN_ID:
        run_query("UPDATE user_states SET ai_optimization = 1")
        await query.edit_message_text("⚡ **Global Optimization Triggered.** All user environments activated.", parse_mode="Markdown")
        return

    # --- AUTO TRADE WITH ISOLATED TRACKING ---
    if data == "confirm_trade_on":
        state["is_strategy_active"] = True
        allocated_pool = state["allocated_trade_capital"]
        split_size = (allocated_pool / 2) / 3
        
        target_pool_key = "demo_positions" if state["account_mode"] == "DEMO" else "real_positions"
        assets_traded = 0
        
        for asset in ["ETH", "SOL", "BNB"]:
            entry_price = crypto_prices.get(asset, 0.0)
            if entry_price > 0:
                state[target_pool_key][asset] = {"allocated": split_size, "entry": entry_price}
                assets_traded += 1
                
        if state["account_mode"] == "DEMO": state["demo_balance"] -= (allocated_pool / 2)
        else: state["real_balance"] -= (allocated_pool / 2)
            
        state["total_trades"] += assets_traded # Isolates and updates exactly for this specific user
        save_user_state(user_id, state)
        await query.edit_message_text(f"🟩 **Pro AI Entry Strategy Fired.**\n• Isolated Blocks Executed: `{assets_traded}`\n• Total Lifetime Trades: `{state['total_trades']}`", parse_mode="Markdown")
        
async def post_init(application: Application) -> None:
    asyncio.create_task(fetch_resilient_prices())

def main():
    init_db()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("optimize", toggle_optimization))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.run_polling()

if __name__ == "__main__":
    main()
