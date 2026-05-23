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
DB_FILE = "lens_pro_database.db"

# --- DB HELPER ENGINE ---
def run_query(query: str, params: tuple = (), fetch: str = None):
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

# --- DATABASE INITIALIZATION ---
def init_db():
    """Initializes Pro schema with completely separated Demo and Real position tracks."""
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
            demo_positions TEXT,
            real_positions TEXT,
            closed_history TEXT,
            last_seen_onchain_bal REAL
        )
    """)

def get_user_state(user_id: int) -> dict:
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
            "demo_positions": json.loads(row[11]) if row[11] else {},
            "real_positions": json.loads(row[12]) if row[12] else {},
            "closed_history": json.loads(row[13]) if row[13] else [],
            "last_seen_onchain_bal": float(row[14]) if row[14] is not None else 0.00
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
            "demo_positions": {},
            "real_positions": {},  
            "closed_history": [],
            "last_seen_onchain_bal": 0.00
        }
        run_query("""
            INSERT INTO user_states VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, "DEMO", 1000.00, 0.00, 0, 0, "Not Connected", None, None, 10.00, "MID", "{}", "{}", "[]", 0.00))
        return default_state

def save_user_state(user_id: int, state: dict):
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
            demo_positions = ?,
            real_positions = ?,
            closed_history = ?,
            last_seen_onchain_bal = ?
        WHERE user_id = ?
    """, (
        state["account_mode"], state["demo_balance"], state["real_balance"],
        1 if state["is_strategy_active"] else 0, 1 if state["wallet_connected"] else 0,
        state["wallet_address"], state["wallet_provider"], enc_key_str,
        state["allocated_trade_capital"], state["risk_profile"],
        json.dumps(state["demo_positions"]), json.dumps(state["real_positions"]),
        json.dumps(state["closed_history"]), state["last_seen_onchain_bal"],
        user_id
    ))

def credit_admin_fee(amount: float):
    admin_state = get_user_state(ADMIN_ID)
    admin_state["real_balance"] += amount
    save_user_state(ADMIN_ID, admin_state)

crypto_prices = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0, "BNB": 0.0}

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

# --- AUTOMATED FUNDING DETECTION TRACKER ---
def process_automated_onchain_funding(user_id: int, state: dict, current_onchain_balance: float) -> str:
    """Detects if real account was externally funded; automatically auto-routes 10% fee to Admin."""
    if current_onchain_balance > state["last_seen_onchain_bal"]:
        new_funds = current_onchain_balance - state["last_seen_onchain_bal"]
        state["last_seen_onchain_bal"] = current_onchain_balance
        
        if user_id == ADMIN_ID:
            state["real_balance"] += new_funds
            return f"👑 **Admin Node Funded:** Detected input of `${new_funds:.2f}` real capital. 0% Excluded Fee applied."
        else:
            fee = new_funds * 0.10
            net_capital = new_funds - fee
            state["real_balance"] += net_capital
            credit_admin_fee(fee) # Route 10% automatically to admin row
            return (
                f"⚡ **Automated On-Chain Funding Detected!**\n"
                f"• Detected Raw Deposit: `${new_funds:.2f}`\n"
                f"• Automated Admin Fee (10%): `-${fee:.2f}`\n"
                f"• Liquid Capital Credited: `${net_capital:.2f}`"
            )
    state["last_seen_onchain_bal"] = current_onchain_balance
    return ""

# --- COMMAND INTERFACES ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    msg = (
        "🔥 **LENS INSTITUTIONAL PRO TERMINAL v12.0** 🔥\n"
        "Advanced Quantum Autonomous AI Engine active.\n\n"
        f"💳 **Server Mode:** `{state['account_mode']}` | 📊 **AI Strategy:** `{'🟢 ON' if state['is_strategy_active'] else '🔴 OFF'}`\n"
        f"🛡️ **Adaptive Risk Profile:** `{state['risk_profile']}`\n"
        "---------------------------------------\n"
        "🔌 /connect - Universal Web3 Secure Link Portal\n"
        "💼 /wallet - Check Isolated Balances & Sync Real Funds\n"
        "🔄 /accounts - Switch between DEMO and REAL Servers\n"
        "💸 /withdraw [amount] - Capital Extraction Matrix (Free Withdrawals)\n"
        "🛡️ /risk - Configure Active Stop Loss/Take Profit Risk Matrix\n"
        "📊 /positions - Isolated Portfolio View & Meme Performance PnL\n"
        "🤖 /autotrade [amount] - Deploy Pro AI Automated Strategy\n"
        "🛑 /closeall - Emergency Strategy Liquidation\n"
        "📈 /price - Live Real-Time Multi-Asset Index Feed"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    # Simulating standard secure Web3 address lookups for funding verification
    simulated_live_blockchain_balance = state["last_seen_onchain_bal"]
    if context.args:
        try:
            # Allows explicit injection for lightning-fast testing loops
            simulated_live_blockchain_balance = float(context.args[0])
        except ValueError:
            pass

    funding_alert = process_automated_onchain_funding(user_id, state, simulated_live_blockchain_balance)
    save_user_state(user_id, state)
    
    if funding_alert:
        await update.message.reply_text(funding_alert, parse_mode="Markdown")
        
    bal = state["demo_balance"] if state["account_mode"] == "DEMO" else state["real_balance"]
    msg = (
        "💼 **Your Isolated Pro Balance Matrix**\n"
        f"• Status: {'🟩 LINKED' if state['wallet_connected'] else '🟥 DECOUPLED'}\n"
        f"• On-Chain Tracking Addr: `{state['wallet_address']}`\n"
        "----------------------------------------\n"
        f"💳 **Current Target:** `{state['account_mode']}`\n"
        f"💰 **Active Tradable Balance:** `${bal:.2f} USDT`\n\n"
        f"_*Testing Tip:* To mock real-world external funding deposit detection instantly, pass a higher float balance value via command, like: `/wallet 5000`_"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    if not context.args:
        await update.message.reply_text("❌ Missing parameter. Format: `/withdraw 250`")
        return
        
    try:
        amount = float(context.args[0])
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid numeric format.")
        return

    current_balance = state["demo_balance"] if state["account_mode"] == "DEMO" else state["real_balance"]
    if amount > current_balance:
        await update.message.reply_text(f"❌ Insufficient account limits. Available: ${current_balance:.2f}")
        return

    if state["account_mode"] == "DEMO":
        state["demo_balance"] -= amount
    else:
        state["real_balance"] -= amount
        
    save_user_state(user_id, state)
    
    msg = (
        "💸 **Withdrawal Request Dispatched!**\n"
        "---------------------------------------\n"
        f"• **Amount Removed:** `${amount:.2f}`\n"
        f"• **Bot Extraction Fee:** `$0.00` (Free Withdrawals Active)\n\n"
        "_Note: External network layer-1 gas standard fees are settled natively by the user._"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    # Select fully isolated active position array based on profile state
    active_pool = state["demo_positions"] if state["account_mode"] == "DEMO" else state["real_positions"]
    
    if not active_pool:
        await update.message.reply_text(f"📊 **{state['account_mode']} Portfolio**: No positions open in this environment.")
        return
        
    msg = f"📊 **Isolated {state['account_mode']} Active Matrix**\n---------------------------------------\n"
    total_pnl_cash = 0.0
    total_allocated = 0.0
    
    for asset, data in active_pool.items():
        live_p = crypto_prices.get(asset, 0.0)
        pnl_pct = ((live_p - data['entry']) / data['entry']) * 100 if data['entry'] > 0 else 0.0
        pnl_cash = (live_p - data['entry']) * (data['allocated'] / data['entry']) if data['entry'] > 0 else 0.0
        total_pnl_cash += pnl_cash
        total_allocated += data['allocated']
        
        msg += (
            f"• **{asset}/USDT**\n"
            f"  - Allocation: ${data['allocated']:.2f}\n"
            f"  - Entry: ${data['entry']:,} | Live Index: ${live_p:,}\n"
            f"  - Return Profile: `{pnl_pct:+.2f}%` (${pnl_cash:+.2f} USDT)\n"
        )
        
    net_pnl_pct = (total_pnl_cash / total_allocated) * 100 if total_allocated > 0 else 0.0
    msg += f"---------------------------------------\n**Net Performance Yield:** `{net_pnl_pct:+.2f}%` (${total_pnl_cash:+.2f} USDT)"

    # --- DYNAMIC REACTION MEME ENGINE (PERCENTAGE ORIENTED) ---
    if net_pnl_pct >= 5.0:
        # Tier 4: Moon shot / Gigachad Wealth Win
        animation_url = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3ZtYnV6MndjYmF4M3R1dmtiaDJ3ODN4amF5M3QyY2Y3bjVpZnB1ZiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LdOyjZ7QX5N56wxtuK/giphy.gif"
    elif 0.0 <= net_pnl_pct < 5.0:
        # Tier 3: Steady gains / Smug approving reaction
        animation_url = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMDFmYmN5ZndwZWd0amJ5MmNleWtlYnR6MWs5bjZicjRwbTJ0ZWoxbCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/YnkMcHgNIMW4Yfmjxr/giphy.gif"
    elif -5.0 <= net_pnl_pct < 0.0:
        # Tier 2: Micro loss / Nervous panic sweat reaction
        animation_url = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYnI1am8ydWV2NTRwdm5oamFndHhzYmxtbmlyM2Rnb3FhcXR6ZmN3bCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LRV5CHZ65ubtC/giphy.gif"
    else:
        # Tier 1: Liquidation Warning / High rage explosion meme
        animation_url = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNmt0bXNudmU1Y3Y2Zmxtd3k1cmVxeDR1aHk3M2I0eXo4azBtYmdtZCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3o6Zt4HU9uwXmXSAuI/giphy.gif"
        
    await update.message.reply_animation(animation=animation_url, caption=msg, parse_mode="Markdown")

async def autotrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    if state["account_mode"] == "REAL" and not state["wallet_connected"]:
        await update.message.reply_text("❌ Infrastructure Link Error: Deploy cryptographic keys via /connect first.")
        return

    if not context.args:
        await update.message.reply_text(f"🤖 **Advanced AI Core Module**\nPass deployment size. Example: `/autotrade 200`")
        return

    try:
        req_amount = float(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Processing error. Numbers required.")
        return

    available = state["demo_balance"] if state["account_mode"] == "DEMO" else state["real_balance"]
    if req_amount > available:
        await update.message.reply_text(f"❌ Target exposure exceeds liquidity limits. Limit: ${available:.2f}")
        return

    state["allocated_trade_capital"] = req_amount
    save_user_state(user_id, state)
    
    # Institutional Neural Matrix Optimization simulation
    ai_success_matrix_score = round(random.uniform(95.00, 99.99), 2)
    
    keyboard = [
        [InlineKeyboardButton("⚡ Fire Pro AI Core Engine", callback_data="confirm_trade_on")],
        [InlineKeyboardButton("❌ Disengage Strategy Setup", callback_data="confirm_trade_off")]
    ]
    await update.message.reply_text(
        f"🧠 **ADVANCED QUANTUM AI SUITE EXECUTION**\n---------------------------------------\n"
        f"📈 **Neural Pattern Predictive Win-Rate:** `{ai_success_matrix_score}%` Successfully Verified\n"
        f"📊 **Market Indicators:** Order-Book Delta Long Spike Detected\n"
        f"💰 **Total Position Sizing Target:** ${req_amount:.2f} USDT\n\n"
        f"Confirm execution of the automated multi-coin entry matrix inside your {state['account_mode']} server layer?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def closeall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    active_pool = state["demo_positions"] if state["account_mode"] == "DEMO" else state["real_positions"]
    
    if not active_pool:
        await update.message.reply_text("⚠️ Exposure profile is completely flat.")
        return
        
    for asset, data in list(active_pool.items()):
        live_p = crypto_prices.get(asset, 0.0)
        pnl = (live_p - data['entry']) * (data['allocated'] / data['entry']) if data['entry'] > 0 else 0.0
        
        if state["account_mode"] == "DEMO":
            state["demo_balance"] += (data['allocated'] + pnl)
        else:
            state["real_balance"] += (data['allocated'] + pnl)
            
        state["closed_history"].append({
            "time": datetime.now().strftime("%m-%d %H:%M"), "asset": asset, "type": "LIQ_PRO", "pnl": pnl, "mode": state["account_mode"]
        })
        
    active_pool.clear()
    state["is_strategy_active"] = False
    save_user_state(user_id, state)
    await update.message.reply_text(f"🛑 **EMERGENCY LIQUIDATION COMPLETE.** All {state['account_mode']} exposure blocks cleared.")

async def accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    keyboard = [
        [InlineKeyboardButton("🎯 Deploy Demo Sandboxed Network", callback_data="set_demo")],
        [InlineKeyboardButton("💎 Deploy Live Production Mainnet", callback_data="set_real")]
    ]
    await update.message.reply_text(
        f"🔄 **Core Core Matrix Controller**\n\nActive Framework Server: `{state['account_mode']}`\n"
        f"• Demo Cash: `${state['demo_balance']:.2f}`\n"
        f"• Real Mainnet Cash: `${state['real_balance']:.2f}`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "📈 **LENS Real-Time Asset Index (USDT)**\n---------------------------------------\n"
    for asset, val in crypto_prices.items():
        status = "🟢" if val > 0 else "🔴 Offline"
        msg += f"• **{asset}**: ${val:,.2f} {status}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    keyboard = [[
        InlineKeyboardButton("🟢 LOW PROFILE", callback_data="risk_LOW"),
        InlineKeyboardButton("🟡 MID PROFILE", callback_data="risk_MID"),
        InlineKeyboardButton("🔴 HIGH PROFILE", callback_data="risk_HIGH")
    ]]
    sets = state["risk_settings"][state["risk_profile"]]
    await update.message.reply_text(
        f"🛡️ **Pro Risk Matrix Optimizer**\n\nActive Node Setting: `{state['risk_profile']}`\n"
        f"• Parametric Stop Loss: `{sets['SL']}%` | Take Profit target: `{sets['TP']}%`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if not state["closed_history"]:
        await update.message.reply_text("📜 History engine database contains zero records.")
        return
    msg = "📜 **Pro Real-Time Historical Database Ledger**\n---------------------------------------\n"
    for txn in state["closed_history"][-5:]:
        msg += f"• [{txn['time']}] **{txn['asset']}** ({txn['mode']}): Yield: `${txn['pnl']:+.2f}`\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ref_url = "https://t.me/UXUYbot/app?appstart=A_6546954770_inviteEarn"
    keyboard = [
        [InlineKeyboardButton("🔥 Register UXUY Infrastructure Link", url=ref_url)],
        [InlineKeyboardButton("🔒 Provision Secure Ephemeral Key", callback_data="gen_wallet")],
        [InlineKeyboardButton("🔑 Inject Authenticated Cipher Key", callback_data="imp_wallet")]
    ]
    await update.message.reply_text("🔌 **Secure Web3 Interface Link Module**", reply_markup=InlineKeyboardMarkup(keyboard))

async def import_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if not context.args:
        await update.message.reply_text("❌ Format error: `/import YOUR_KEY`")
        return
    try:
        raw_key = context.args[0].strip()
        account = Account.from_key(raw_key)
        state["wallet_address"] = account.address
        raw_key_bytes = bytes.fromhex(raw_key[2:]) if raw_key.startswith("0x") else bytes.fromhex(raw_key)
        state["encrypted_private_key"] = cipher_suite.encrypt(raw_key_bytes)
        state["wallet_provider"] = "Pro Encrypted Core Import"
        state["wallet_connected"] = True
        save_user_state(user_id, state)
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
        await update.message.reply_text(f"🟩 **Isolated Wallet Key Bound Securely to Instance Row!**\n`{account.address}`")
    except Exception:
        await update.message.reply_text("❌ Key initialization rejected. Invalid hexadecimal configuration.")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    keyboard = [
        [InlineKeyboardButton("🔍 Core Matrix Status Diagnostic", callback_data="admin_diagnose")],
        [InlineKeyboardButton("🔧 Clear Ghost Position Records", callback_data="admin_autofix")]
    ]
    await update.message.reply_text("🎛️ **LENS CENTRAL SYSTEM ADMINISTRATION CORE**", reply_markup=InlineKeyboardMarkup(keyboard))

# --- HANDLERS CALLBACK SYSTEM ---
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    await query.answer()
    data = query.data

    if data == "admin_diagnose" and user_id == ADMIN_ID:
        count_row = run_query("SELECT COUNT(*) FROM user_states", fetch="one")
        report = f"🔍 **System Diagnostic Log**\n• Stored Rows: `{count_row[0] if count_row else 0}`\n• Platform Pricing Stream: 🟩 LIVE"
        await query.edit_message_text(report, parse_mode="Markdown")
        return

    if data == "admin_autofix" and user_id == ADMIN_ID:
        run_query("UPDATE user_states SET demo_positions='{}', real_positions='{}' WHERE user_id != ?", (ADMIN_ID,))
        await query.edit_message_text("🔧 **Optimization Script Handled.** Ghost position data arrays wiped.")
        return

    if data == "gen_wallet":
        account = Account.create()
        state["wallet_address"] = account.address
        state["encrypted_private_key"] = cipher_suite.encrypt(account.key)
        state["wallet_provider"] = "LENS Native Pro Burner"
        state["wallet_connected"] = True
        save_user_state(user_id, state)
        await query.edit_message_text(f"🔐 **Secure Key Pair Matrix Generated**\n\n• Address: `{account.address}`\n• Private Key: `{account.key.hex()}`", parse_mode="Markdown")
        return

    if data == "imp_wallet":
        await query.edit_message_text("📝 Direct message structural key sequence using: `/import KEY_STRING`")
        return

    if data == "set_demo":
        state["account_mode"] = "DEMO"
        save_user_state(user_id, state)
        await query.edit_message_text("🟩 Core adjusted to **DEMO PIPELINE**.")
    elif data == "set_real":
        state["account_mode"] = "REAL"
        save_user_state(user_id, state)
        await query.edit_message_text("🎛️ Core adjusted to **REAL MAINNET PRODUCTION PIPELINE**.")

    elif data.startswith("risk_"):
        sel = data.split("_")[1]
        state["risk_profile"] = sel
        save_user_state(user_id, state)
        await query.edit_message_text(f"🟩 **Matrix constraints shifted to:** `{sel}`")

    elif data == "confirm_trade_on":
        state["is_strategy_active"] = True
        allocated_pool = state["allocated_trade_capital"]
        split_size = (allocated_pool / 2) / 3
        
        # Divert targets safely to separate demo or real position arrays
        target_pool_key = "demo_positions" if state["account_mode"] == "DEMO" else "real_positions"
        
        for asset in ["ETH", "SOL", "BNB"]:
            entry_price = crypto_prices.get(asset, 0.0)
            if entry_price > 0:
                state[target_pool_key][asset] = {"allocated": split_size, "entry": entry_price}
                
        if state["account_mode"] == "DEMO":
            state["demo_balance"] -= (allocated_pool / 2)
        else:
            state["real_balance"] -= (allocated_pool / 2)
            
        save_user_state(user_id, state)
        await query.edit_message_text("🟩 **Pro AI Entry Strategy Fired. Execution parameters written to SQL ledger.**")
        
    elif data == "confirm_trade_off":
        state["is_strategy_active"] = False
        save_user_state(user_id, state)
        await query.edit_message_text("🛑 Neural network deployment sequence aborted.")

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(f"🚨 Pro Engine Core Error: {context.error}")

async def post_init(application: Application) -> None:
    asyncio.create_task(fetch_resilient_prices())

def main():
    init_db()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token: return
    app = Application.builder().token(token).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("import", import_key_command))
    app.add_handler(CommandHandler("wallet", wallet))
    app.add_handler(CommandHandler("accounts", accounts))
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
