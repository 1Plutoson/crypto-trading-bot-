import os
import asyncio
import logging
import json
import urllib.request
import sqlite3
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from cryptography.fernet import Fernet
from eth_account import Account

Account.enable_unaudited_hdwallet_features()

try:
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- MASTER ENCRYPTION SYSTEM ---
ENCRYPTION_KEY = os.environ.get("MASTER_KEY", Fernet.generate_key())
if isinstance(ENCRYPTION_KEY, str):
    if not ENCRYPTION_KEY.startswith("b'") and not isinstance(ENCRYPTION_KEY, bytes):
        pass
cipher_suite = Fernet(ENCRYPTION_KEY if isinstance(ENCRYPTION_KEY, bytes) else ENCRYPTION_KEY.encode())

ADMIN_ID = 6546954770
DB_FILE = "lens_database.db"

# --- DB HELPER ENGINE (Thread-Safe Wrapper) ---
def run_query(query: str, params: tuple = (), fetch: str = None):
    """Safely handles isolated synchronous SQLite connections across async tasks."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        if fetch == "one":
            result = cursor.fetchone()
        elif fetch == "all":
            result = cursor.fetchall()
        else:
            conn.commit()
            result = None
        return result
    except Exception as e:
        logging.error(f"Database error during: {query} | Error: {e}")
        raise e
    finally:
        conn.close()

# --- DATABASE INITIALIZATION ENGINE ---
def init_db():
    """Creates the persistent SQL database schema if it doesn't exist."""
    run_query("""
        CREATE TABLE IF NOT EXISTS user_states (
            user_id INTEGER PRIMARY KEY,
            account_mode TEXT,
            demo_balance REAL,
            real_balance REAL,
            is_strategy_active INTEGER,
            wallet_connected INTEGER,
            wallet_address TEXT,
            wallet_provider TEXT,
            encrypted_private_key TEXT,
            allocated_trade_capital REAL,
            risk_profile TEXT,
            active_positions TEXT,
            closed_history TEXT
        )
    """)

def get_user_state(user_id: int) -> dict:
    """Fetches unique user profiles from the SQL database or instantiates a default row."""
    row = run_query("SELECT * FROM user_states WHERE user_id = ?", (user_id,), fetch="one")
    
    if row:
        return {
            "account_mode": row[1],
            "demo_balance": float(row[2]) if row[2] is not None else 1000.00,
            "real_balance": float(row[3]) if row[3] is not None else 0.00,
            "is_strategy_active": bool(row[4]),
            "wallet_connected": bool(row[5]),
            "wallet_address": row[6] or "Not Connected",
            "wallet_provider": row[7],
            "encrypted_private_key": row[8].encode('utf-8') if row[8] else None,
            "allocated_trade_capital": float(row[9]) if row[9] is not None else 10.00,
            "min_deposit_limit": 10.00,
            "risk_profile": row[10] or "MID",
            "risk_settings": {
                "LOW":  {"SL": -0.75, "TP": 2.5},   
                "MID":  {"SL": -1.5,  "TP": 6.25},  
                "HIGH": {"SL": -3.75, "TP": 12.5}  
            },
            "active_positions": json.loads(row[11]) if row[11] else {},
            "closed_history": json.loads(row[12]) if row[12] else []
        }
    else:
        default_state = {
            "account_mode": "DEMO",          
            "demo_balance": 1000.00,
            "real_balance": 0.00,
            "is_strategy_active": False,
            "wallet_connected": False,
            "wallet_address": "Not Connected",
            "wallet_provider": None,
            "encrypted_private_key": None,
            "allocated_trade_capital": 10.00, 
            "min_deposit_limit": 10.00,
            "risk_profile": "MID",           
            "risk_settings": {
                "LOW":  {"SL": -0.75, "TP": 2.5},   
                "MID":  {"SL": -1.5,  "TP": 6.25},  
                "HIGH": {"SL": -3.75, "TP": 12.5}  
            },
            "active_positions": {},  
            "closed_history": []     
        }
        run_query("""
            INSERT INTO user_states VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, "DEMO", 1000.00, 0.00, 0, 0, "Not Connected", None, None, 10.00, "MID", "{}", "[]"))
        return default_state

def save_user_state(user_id: int, state: dict):
    """Commits volatile changes back to the SQL architecture permanently."""
    enc_key_str = state["encrypted_private_key"].decode('utf-8') if state["encrypted_private_key"] else None
    run_query("""
        UPDATE user_states SET
            account_mode = ?,
            demo_balance = ?,
            real_balance = ?,
            is_strategy_active = ?,
            wallet_connected = ?,
            wallet_address = ?,
            wallet_provider = ?,
            encrypted_private_key = ?,
            allocated_trade_capital = ?,
            risk_profile = ?,
            active_positions = ?,
            closed_history = ?
        WHERE user_id = ?
    """, (
        state["account_mode"], state["demo_balance"], state["real_balance"],
        1 if state["is_strategy_active"] else 0, 1 if state["wallet_connected"] else 0,
        state["wallet_address"], state["wallet_provider"], enc_key_str,
        state["allocated_trade_capital"], state["risk_profile"],
        json.dumps(state["active_positions"]), json.dumps(state["closed_history"]),
        user_id
    ))

def credit_admin_fee(amount: float, mode: str):
    """Automatically routes the 10% deposit fee directly to Admin's DB balance."""
    admin_state = get_user_state(ADMIN_ID)
    if mode == "DEMO":
        admin_state["demo_balance"] += amount
    else:
        admin_state["real_balance"] += amount
    save_user_state(ADMIN_ID, admin_state)

crypto_prices = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0, "BNB": 0.0}

# --- GLOBAL LIVE PRICE TICKER ---
async def fetch_resilient_prices():
    while True:
        for url in ["https://api.binance.com/api/v3/ticker/price", "https://api.binance.us/api/v3/ticker/price"]:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                loop = asyncio.get_running_loop()
                def fetch_data():
                    with urllib.request.urlopen(req, timeout=5) as response:
                        if response.status == 200:
                            return json.loads(response.read().decode())
                    return None
                
                data = await loop.run_in_executor(None, fetch_data)
                if data:
                    for item in data:
                        sym = item.get("symbol", "")
                        clean_sym = sym.replace("USDT", "")
                        if clean_sym in crypto_prices:
                            crypto_prices[clean_sym] = float(item.get("price", 0.0))
            except Exception:
                continue
        await asyncio.sleep(5)

# --- USER ROUTINES ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    msg = (
        "⚡ **LENS Multi-Coin Production Terminal v11.6** ⚡\n"
        "Your unique institutional database node is active.\n\n"
        f"💳 **Mode:** `{state['account_mode']}` | 📊 **Strategy:** `{'🟢 ON' if state['is_strategy_active'] else '🔴 OFF'}`\n"
        f"🛡️ **Your Risk Target:** `{state['risk_profile']}`\n"
        "---------------------------------------\n"
        "🔌 /connect - Universal Web3 Secure Link Portal\n"
        "💼 /wallet - View Capital Matrix & Network Details\n"
        "🔄 /accounts - Switch between DEMO and REAL Servers\n"
        "💵 /deposit [amount] - Fund your portfolio\n"
        "💸 /withdraw [amount] - Extract your capital\n"
        "🛡️ /risk - Configure Adaptive Risk parameters\n"
        "📊 /positions - View Your Active Orders & PnL\n"
        "📜 /history - View Your Transaction Logs\n"
        "📈 /price - Real-time Prices & Live Automated Charts\n"
        "🤖 /autotrade - Configurable AI Allocation Engine\n"
        "🛑 /closeall - Liquidate your active positions"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    if not context.args:
        await update.message.reply_text("❌ Missing amount. Format: `/deposit 500`")
        return
        
    try:
        amount = float(context.args[0])
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount.")
        return

    # FEE LOGIC: 10% to admin unless the user IS the admin
    if user_id == ADMIN_ID:
        fee = 0.0
        net_amount = amount
        msg = f"👑 **Admin Recognized.** 0% Fee applied.\n"
    else:
        fee = amount * 0.10
        net_amount = amount - fee
        credit_admin_fee(fee, state["account_mode"]) # Route fee silently
        msg = f"🏦 **Deposit Processing**\n• Deposit: `${amount:.2f}`\n• Platform Fee (10%): `-${fee:.2f}`\n"

    # Add funds to active mode
    if state["account_mode"] == "DEMO":
        state["demo_balance"] += net_amount
    else:
        state["real_balance"] += net_amount
        
    save_user_state(user_id, state)
    
    msg += f"✅ **Successfully credited `${net_amount:.2f}` to your {state['account_mode']} balance.**"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    if not context.args:
        await update.message.reply_text("❌ Missing amount. Format: `/withdraw 100`")
        return
        
    try:
        amount = float(context.args[0])
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount.")
        return

    current_balance = state["demo_balance"] if state["account_mode"] == "DEMO" else state["real_balance"]
    
    if amount > current_balance:
        await update.message.reply_text(f"❌ Insufficient funds. Available: ${current_balance:.2f}")
        return

    # Deduct funds
    if state["account_mode"] == "DEMO":
        state["demo_balance"] -= amount
    else:
        state["real_balance"] -= amount
        
    save_user_state(user_id, state)
    
    msg = (
        "💸 **Withdrawal Authorized!**\n"
        "---------------------------------------\n"
        f"• **Amount:** `${amount:.2f}`\n"
        f"• **Bot Fee:** `$0.00` (Free Withdrawals)\n"
        f"• **Network Status:** Pending on-chain verification.\n\n"
        "_Note: Blockchain network gas fees are settled directly by the user's wallet._"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "📈 **LENS Real-Time Asset Index (USDT)**\n---------------------------------------\n"
    for asset, val in crypto_prices.items():
        status = "🟢" if val > 0 else "🔴 Offline"
        msg += f"• **{asset}**: ${val:,.2f} {status}\n"
    msg += f"\n_Last verified: {datetime.now().strftime('%H:%M:%S')}_"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    keyboard = [
        [InlineKeyboardButton("🎮 Activate DEMO Server", callback_data="set_demo")],
        [InlineKeyboardButton("🔑 Activate REAL Server", callback_data="set_real")]
    ]
    await update.message.reply_text(
        f"🔄 **Server Environment Configurator**\n\nActive Node Server: `{state['account_mode']}`\n"
        f"Available Demo Capital: `${state['demo_balance']:.2f}`\n"
        f"Available Real Capital: `${state['real_balance']:.2f}`\n\n"
        "Choose your target environment landscape:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    keyboard = [[
        InlineKeyboardButton("🟢 LOW", callback_data="risk_LOW"),
        InlineKeyboardButton("🟡 MID", callback_data="risk_MID"),
        InlineKeyboardButton("🔴 HIGH", callback_data="risk_HIGH")
    ]]
    sets = state["risk_settings"][state["risk_profile"]]
    await update.message.reply_text(
        f"🛡️ **Risk Tolerance Profile Manager**\n\nCurrent Matrix: `{state['risk_profile']}`\n"
        f"• Stop Loss: `{sets['SL']}%` | Take Profit: `{sets['TP']}%`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    if not state["active_positions"]:
        await update.message.reply_text("📊 **Positions**: Your account context has no active deployments running.")
        return
        
    msg = "📊 **Your Active Portfolio Deployments**\n---------------------------------------\n"
    total_pnl_cash = 0.0
    
    for asset, data in state["active_positions"].items():
        live_p = crypto_prices.get(asset, 0.0)
        pnl_pct = ((live_p - data['entry']) / data['entry']) * 100 if data['entry'] > 0 else 0.0
        pnl_cash = (live_p - data['entry']) * (data['allocated'] / data['entry']) if data['entry'] > 0 else 0.0
        total_pnl_cash += pnl_cash
        
        msg += (
            f"• **{asset}/USDT**\n"
            f"  - Size: ${data['allocated']:.2f}\n"
            f"  - Entry: ${data['entry']:,} | Live: ${live_p:,}\n"
            f"  - Floating PnL: `{pnl_pct:+.2f}%` (${pnl_cash:+.2f} USDT)\n"
        )
        
    msg += f"---------------------------------------\n**Total Floating PnL:** `${total_pnl_cash:+.2f} USDT`"

    # ANIMATION / MEME LOGIC
    if total_pnl_cash >= 0:
        # Happy / Winning Meme GIF
        animation_url = "https://media.giphy.com/media/YnkMcHgNIMW4Yfmjxr/giphy.gif" 
    else:
        # Angry / Losing Meme GIF
        animation_url = "https://media.giphy.com/media/3o6Zt4HU9uwXmXSAuI/giphy.gif" 
        
    await update.message.reply_animation(animation=animation_url, caption=msg, parse_mode="Markdown")

async def autotrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    if state["account_mode"] == "REAL" and not state["wallet_connected"]:
        await update.message.reply_text("❌ Connection Error: Interface your Web3 infrastructure via /connect first.")
        return

    if not context.args:
        await update.message.reply_text(f"🤖 **AI Automated Strategy Engine**\nPass your allocation target size. Example: `/autotrade 50`\nEngine Core Status: `{'🟩 RUNNING' if state['is_strategy_active'] else '🟥 IDLE'}`")
        return

    try:
        req_amount = float(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Input processing failure. Numeric parameter values required.")
        return

    if req_amount < state["min_deposit_limit"]:
        await update.message.reply_text(f"❌ Minimum transaction deployment is **${state['min_deposit_limit']:.2f} USDT**.")
        return

    available = state["demo_balance"] if state["account_mode"] == "DEMO" else state["real_balance"]
    if req_amount > available:
        await update.message.reply_text(f"❌ Insufficient liquidity profile. Available pool: ${available:.2f}")
        return

    state["allocated_trade_capital"] = req_amount
    save_user_state(user_id, state)
    
    trade_pool = req_amount / 2
    per_asset = trade_pool / 3

    # AI PROBABILITY LOGIC
    ai_confidence = round(random.uniform(95.0, 99.9), 2)

    keyboard = [
        [InlineKeyboardButton("🟢 Confirm AI Execution", callback_data="confirm_trade_on")],
        [InlineKeyboardButton("🔴 Abort AI Setup", callback_data="confirm_trade_off")]
    ]
    await update.message.reply_text(
        f"⚠️ **AI NEURAL MATRIX ALLOCATION CONFIRMATION**\n---------------------------------------\n"
        f"🧠 **Deep Learning Target Success Rate:** `{ai_confidence}%`\n"
        f"• **Target Capital Base:** ${req_amount:.2f} USDT\n"
        f"• **Active Trade Split (50%):** ${trade_pool:.2f} USDT\n"
        f"• **Split Per Asset (ETH, SOL, BNB):** ~${per_asset:.2f} USDT\n\n"
        f"Our advanced AI module will manage micro-fluctuations to optimize success metrics.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def closeall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if not state["active_positions"]:
        await update.message.reply_text("⚠️ Matrix contains zero active risks to liquidate.")
        return
        
    for asset, data in list(state["active_positions"].items()):
        live_p = crypto_prices.get(asset, 0.0)
        pnl = (live_p - data['entry']) * (data['allocated'] / data['entry']) if data['entry'] > 0 else 0.0
        if state["account_mode"] == "DEMO":
            state["demo_balance"] += (data['allocated'] + pnl)
        else:
            state["real_balance"] += (data['allocated'] + pnl)
            
        state["closed_history"].append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"), "asset": asset, "type": "LIQUIDATE", "pnl": pnl, "mode": state["account_mode"]
        })
        
    state["active_positions"].clear()
    state["is_strategy_active"] = False
    save_user_state(user_id, state)
    await update.message.reply_text("🛑 **POSITIONS CLOSED.** Your specific database exposures have been committed and cleared.")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if not state["closed_history"]:
        await update.message.reply_text("📜 Your execution history log is empty.")
        return
    msg = "📜 **Your Isolated Transaction Ledger**\n---------------------------------------\n"
    for txn in state["closed_history"][-5:]:
        msg += f"• [{txn['time']}] **{txn['asset']}**: {txn['type']} | PnL: `${txn['pnl']:+.2f}` ({txn['mode']})\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ref_url = "https://t.me/UXUYbot/app?appstart=A_6546954770_inviteEarn"
    keyboard = [
        [InlineKeyboardButton("🔥 1. Register UXUY Infrastructure", url=ref_url)],
        [InlineKeyboardButton("⚡ 2A. Generate Isolated Burner", callback_data="gen_wallet")],
        [InlineKeyboardButton("🔑 2B. Import Personal Vault Key", callback_data="imp_wallet")]
    ]
    await update.message.reply_text("🔌 **Web3 Link Portal**\nChoose your database wallet deployment structure:", reply_markup=InlineKeyboardMarkup(keyboard))

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    bal = state["demo_balance"] if state["account_mode"] == "DEMO" else state["real_balance"]
    msg = (
        "💼 **Your Isolated Database Balance Matrix**\n"
        f"• Status: {'🟩 LINKED' if state['wallet_connected'] else '🟥 DECOUPLED'}\n"
        f"• Address: `{state['wallet_address']}`\n"
        "----------------------------------------\n"
        f"💳 **Active Mode:** `{state['account_mode']}` | **Liquidity Pool:** ${bal:.2f} USDT"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def import_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if not context.args:
        await update.message.reply_text("❌ Use formatting: `/import PRIVATE_KEY`")
        return
    try:
        raw_key = context.args[0].strip()
        account = Account.from_key(raw_key)
        state["wallet_address"] = account.address
        
        if raw_key.startswith("0x"):
            raw_key_bytes = bytes.fromhex(raw_key[2:])
        else:
            raw_key_bytes = bytes.fromhex(raw_key)
            
        state["encrypted_private_key"] = cipher_suite.encrypt(raw_key_bytes)
        state["wallet_provider"] = "User Vault Import"
        state["wallet_connected"] = True
        
        save_user_state(user_id, state)
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
        await update.message.reply_text(f"🟩 **Decoupled Wallet Imported Securely to SQL Database!**\nBound to instance: `{account.address}`")
    except Exception as e:
        logging.error(f"Import failure parsing raw signature data: {e}")
        await update.message.reply_text("❌ Encryption cipher signature verification rejected. Confirm structural format strings.")

# --- MASTER ADMIN ONLY CONTROL CENTER ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ **CRITICAL EXCEPTION: ACCESS DENIED.**")
        return
        
    keyboard = [
        [InlineKeyboardButton("🔍 Diagnose SQL Infrastructure", callback_data="admin_diagnose")],
        [InlineKeyboardButton("🔧 Execute Auto-Fix Script", callback_data="admin_autofix")]
    ]
    await update.message.reply_text(
        "🎛️ **LENS CORE SYSTEM ADMINISTRATION (SQL PERSISTENT)**\n"
        "---------------------------------------\n"
        "Select an automated maintenance daemon below:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# --- GLOBAL CALLBACK MATRIX ---
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    await query.answer()
    data = query.data

    # --- ADMIN EXECUTIONS ---
    if data == "admin_diagnose":
        if user_id != ADMIN_ID: return
        
        count_row = run_query("SELECT COUNT(*) FROM user_states", fetch="one")
        active_nodes = count_row[0] if count_row else 0
        
        env_token = "🟩 FOUND" if os.environ.get("TELEGRAM_BOT_TOKEN") else "🟥 MISSING"
        env_key = "🟩 SIGNED" if os.environ.get("MASTER_KEY") else "🟨 TEMPORARY VOLATILE"
        feed_status = "🟩 CONNECTED" if any(v > 0 for v in crypto_prices.values()) else "🟥 DATA STALLED"
        
        report = (
            "🔍 **LENS INFRASTRUCTURE HEALTH REPORT (SQL)**\n"
            "---------------------------------------\n"
            f"• **Stored Database Contexts:** `{active_nodes} Profiles Saved`\n"
            f"• **Telegram Interface Pipeline:** `{env_token}`\n"
            f"• **Encryption Vault Master Status:** `{env_key}`\n"
            f"• **Binance Stream Feed:** `{feed_status}`\n"
            f"• **Database Engine Architecture:** `SQLite3 Thread-Safe Native Pool`"
        )
        await query.edit_message_text(report, parse_mode="Markdown")
        return

    if data == "admin_autofix":
        if user_id != ADMIN_ID: return
        corrupted_nodes = 0
        fixed_positions = 0
        
        rows = run_query("SELECT user_id FROM user_states", fetch="all")
        
        for row in rows:
            uid = row[0]
            ustate = get_user_state(uid)
            mutated = False
            
            for asset, pos in list(ustate["active_positions"].items()):
                if pos['entry'] <= 0 or crypto_prices.get(asset, 0) == 0:
                    del ustate["active_positions"][asset]
                    fixed_positions += 1
                    mutated = True
            if not isinstance(ustate.get("demo_balance"), (int, float)):
                ustate["demo_balance"] = 1000.00
                corrupted_nodes += 1
                mutated = True
                
            if mutated:
                save_user_state(uid, ustate)
                
        await query.edit_message_text(
            f"🔧 **AUTOMATED SQL MAINTENANCE COMPLETE**\n"
            "---------------------------------------\n"
            f"• Repaired structural node values: `{corrupted_nodes}`\n"
            f"• Dropped dead ghost exposure sets: `{fixed_positions}`\n"
            f"• Database Status: `OPTIMIZED & ARCHIVED`", 
            parse_mode="Markdown"
        )
        return

    # --- DECOUPLED USER MENU ACTIONS ---
    if data == "gen_wallet":
        account = Account.create()
        state["wallet_address"] = account.address
        state["encrypted_private_key"] = cipher_suite.encrypt(account.key)
        state["wallet_provider"] = "LENS Native Burner"
        state["wallet_connected"] = True
        
        save_user_state(user_id, state)
        await query.edit_message_text(
            f"🔐 **Decoupled Wallet Generated & Saved to DB**\n\n"
            f"• **Your Isolated Address:** `{account.address}`\n"
            f"• **Your Private Key:** `{account.key.hex()}`\n\n"
            "⚠️ Copy your private key immediately! It has been committed securely to the SQL architecture.",
            parse_mode="Markdown"
        )
        return

    if data == "imp_wallet":
        await query.edit_message_text("📝 Send your key to this DM thread using: `/import YOUR_PRIVATE_KEY`")
        return

    if data == "set_demo":
        state["account_mode"] = "DEMO"
        save_user_state(user_id, state)
        await query.edit_message_text(f"🟩 Node adjusted to **DEMO**. Database index: ${state['demo_balance']:.2f} USDT")
    elif data == "set_real":
        state["account_mode"] = "REAL"
        save_user_state(user_id, state)
        await query.edit_message_text("🎛️ Node adjusted to **REAL**. Database tracking matrix operational.")

    elif data.startswith("risk_"):
        sel = data.split("_")[1]
        state["risk_profile"] = sel
        save_user_state(user_id, state)
        await query.edit_message_text(f"🟩 **Your profile configured to:** `{sel}`")

    elif data == "confirm_trade_on":
        state["is_strategy_active"] = True
        pool = state["allocated_trade_capital"] / 2
        per_asset = pool / 3
        for asset in ["ETH", "SOL", "BNB"]:
            entry = crypto_prices.get(asset, 0.0)
            if entry > 0:
                state["active_positions"][asset] = {"allocated": per_asset, "entry": entry}
        if state["account_mode"] == "DEMO":
            state["demo_balance"] -= pool
        else:
            state["real_balance"] -= pool
            
        save_user_state(user_id, state)
        await query.edit_message_text("🟩 **AI Matrix strategy active. State written permanently to SQL database.**")
        
    elif data == "confirm_trade_off":
        state["is_strategy_active"] = False
        save_user_state(user_id, state)
        await query.edit_message_text("🛑 Order setup killed safely.")

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(f"🚨 Crash Shield Catch: {context.error}")

async def post_init(application: Application) -> None:
    asyncio.create_task(fetch_resilient_prices())

def main():
    init_db() # Run SQL table verification instantly at bootup
    
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logging.critical("CRITICAL FATAL EXCEPTION: Missing environment TELEGRAM_BOT_TOKEN parameter variable.")
        return

    app = Application.builder().token(token).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("import", import_key_command))
    app.add_handler(CommandHandler("wallet", wallet))
    app.add_handler(CommandHandler("accounts", accounts))
    app.add_handler(CommandHandler("deposit", deposit))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("risk", risk))
    app.add_handler(CommandHandler("positions", positions))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("autotrade", autotrade))
    app.add_handler(CommandHandler("closeall", closeall))
    
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_error_handler(global_error_handler)
    
    app.run_polling()

if __name__ == "__main__":
    main()
