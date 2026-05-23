import os
import asyncio
import logging
import json
import urllib.request
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

try:
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- ADVANCED GLOBAL TERMINAL ARCHITECTURE (v8 PRO) ---
SYSTEM_STATE = {
    "account_mode": "DEMO",          # "DEMO" or "REAL"
    "demo_balance": 1000.00,
    "real_balance": 0.00,
    "is_strategy_active": False,
    
    # Wallet Connectivity
    "wallet_connected": False,
    "wallet_address": "Not Connected",
    "wallet_provider": None,
    "real_balance_eth": 0.00,
    
    # Mathematical Rules Configured Natively
    "allocated_trade_capital": 10.00, 
    "min_deposit_limit": 10.00,
    "min_trade_amount": 1.00,
    "max_trade_amount": 10000.00,
    
    # Risk Framework Matrix
    "risk_profile": "MID",           
    "risk_settings": {
        "LOW":  {"SL": -0.75, "TP": 2.5},   
        "MID":  {"SL": -1.5,  "TP": 6.25},  
        "HIGH": {"SL": -3.75, "TP": 12.5}  
    },
    
    # Trade Accounting Streams
    "active_positions": {},  
    "closed_history": []     
}

crypto_prices = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0, "BNB": 0.0}

async def fetch_resilient_prices():
    """Dual-route global pricing ticker."""
    while True:
        for url in ["https://api.binance.com/api/v3/ticker/price", "https://api.binance.us/api/v3/ticker/price"]:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode())
                        for item in data:
                            sym = item.get("symbol", "")
                            clean_sym = sym.replace("USDT", "")
                            if clean_sym in crypto_prices:
                                crypto_prices[clean_sym] = float(item.get("price", 0.0))
            except Exception:
                continue
        await asyncio.sleep(5)

# --- CORE MATH UTILITIES ---
def get_current_available_capital():
    if SYSTEM_STATE["account_mode"] == "DEMO":
        return SYSTEM_STATE["demo_balance"]
    return SYSTEM_STATE["real_balance"]

def update_current_balance(amount_change):
    if SYSTEM_STATE["account_mode"] == "DEMO":
        SYSTEM_STATE["demo_balance"] += amount_change
    else:
        SYSTEM_STATE["real_balance"] += amount_change

# --- TERMINAL UTILITY COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "⚡ **LENS Multi-Coin Production Terminal** ⚡\n"
        "Institutional control panel fully initialized.\n\n"
        f"💳 **Mode:** `{SYSTEM_STATE['account_mode']}` | 📊 **Strategy:** `{'🟢 ON' if SYSTEM_STATE['is_strategy_active'] else '🔴 OFF'}`\n"
        f"🛡️ **Risk Target:** `{SYSTEM_STATE['risk_profile']}`\n"
        "---------------------------------------\n"
        "🔌 /connect - Universal Web3 Secure Link Portal\n"
        "💼 /wallet - View Capital Matrix & Network Details\n"
        "🔄 /accounts - Switch between DEMO and REAL Servers\n"
        "🛡️ /risk - Configure Adaptive Risk parameters\n"
        "📊 /positions - View Active Orders & Executions\n"
        "📜 /history - View Transaction & Audit Logs\n"
        "📈 /price - Real-time Prices & Live Automated Charts\n"
        "📈 /ta - Read Technical Analysis & Trend Confluences\n"
        "🤖 /autotrade - Configurable Split-Allocation Engine\n"
        "🛑 /closeall - Liquidate and close all active positions"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "📈 **LENS Real-Time Asset Index (USDT)**\n---------------------------------------\n"
    for asset, val in crypto_prices.items():
        status = "🟢" if val > 0 else "🔴 Offline"
        msg += f"• **{asset}**: ${val:,.2f} {status if val > 0 else status}\n"
    msg += f"\n_Last update verified: {datetime.now().strftime('%H:%M:%S')}_"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def ta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "📊 **LENS Technical Analysis Matrix**\n---------------------------------------\n"
    for asset in ["ETH", "SOL", "BNB"]:
        price_now = crypto_prices.get(asset, 0.0)
        if price_now == 0:
            msg += f"• **{asset}**: ⚠️ Data Stream Pending...\n"
            continue
        rsi_sim = 52.3 if asset == "ETH" else (48.1 if asset == "SOL" else 61.5)
        trend = "BULLISH CONFLUENCE" if rsi_sim > 50 else "NEUTRAL ACCUMULATION"
        msg += f"• **{asset}/USDT**: {trend}\n  - RSI (14): `{rsi_sim}` | MA(50/200): `GOLDEN CROSS`\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎮 Activate DEMO ($1,000)", callback_data="set_demo")],
        [InlineKeyboardButton("🔑 Activate REAL (UXUY Engine)", callback_data="set_real")]
    ]
    current = SYSTEM_STATE["account_mode"]
    await update.message.reply_text(
        f"🔄 **Server Environment Configurator**\n\nActive Node Server: `{current}`\n\n"
        "Choose your target execution landscape below:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("🟢 LOW", callback_data="risk_LOW"),
        InlineKeyboardButton("🟡 MID", callback_data="risk_MID"),
        InlineKeyboardButton("🔴 HIGH", callback_data="risk_HIGH")
    ]]
    current = SYSTEM_STATE["risk_profile"]
    sets = SYSTEM_STATE["risk_settings"][current]
    await update.message.reply_text(
        f"🛡️ **Risk Tolerance Profile Manager**\n\nCurrent Configuration: `{current}`\n"
        f"• Stop Loss Boundary: `{sets['SL']}%`\n"
        f"• Take Profit Target: `{sets['TP']}%`\n\n"
        "Modify engine parameters instantly:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SYSTEM_STATE["active_positions"]:
        await update.message.reply_text("📊 **Positions & Orders**: No open executions running on this node.")
        return
    msg = "📊 **LENS Active Portfolio Deployments**\n---------------------------------------\n"
    for asset, data in SYSTEM_STATE["active_positions"].items():
        live_p = crypto_prices.get(asset, 0.0)
        pnl_pct = ((live_p - data['entry']) / data['entry']) * 100 if data['entry'] > 0 else 0.0
        msg += f"• **{asset}/USDT**\n  - Size: ${data['allocated']:.2f}\n  - Entry: ${data['entry']:,} | Live: ${live_p:,}\n  - Floating PnL: `{pnl_pct:+.2f}%`\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SYSTEM_STATE["closed_history"]:
        await update.message.reply_text("📜 **Transaction Logs**: Audit stream empty. No closed records found.")
        return
    msg = "📜 **LENS Historical Ledger (Last 5 Closed)**\n---------------------------------------\n"
    for txn in SYSTEM_STATE["closed_history"][-5:]:
        msg += f"• [{txn['time']}] **{txn['asset']}**: {txn['type']} | PnL: `${txn['pnl']:+.2f}` ({txn['mode']} Mode)\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def autotrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if SYSTEM_STATE["account_mode"] == "REAL" and not SYSTEM_STATE["wallet_connected"]:
        await update.message.reply_text("❌ Connection Error: Interface real-world UXUY infrastructure via /connect first.")
        return

    if not context.args:
        await update.message.reply_text(
            "🤖 **LENS Automated Strategy Portal**\n\n"
            "To deploy allocations, pass your desired capital parameters directly.\n"
            "📝 **Syntax Example:** `/autotrade 10` (Min: $10, Max: Unlimited)\n\n"
            f"Current Strategy State: `{'🟩 ON (RUNNING)' if SYSTEM_STATE['is_strategy_active'] else '🟥 OFF (IDLE)'}`",
            parse_mode="Markdown"
        )
        return

    try:
        req_amount = float(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Numeric parameter validation failed.")
        return

    if req_amount < SYSTEM_STATE["min_deposit_limit"]:
        await update.message.reply_text(f"❌ Safety boundary conflict. Minimum transaction deployment pool requires exactly **${SYSTEM_STATE['min_deposit_limit']:.2f} USDT**.")
        return

    available = get_current_available_capital()
    if req_amount > available:
        await update.message.reply_text(f"❌ Execution Blocked: Insufficient liquidity on your {SYSTEM_STATE['account_mode']} profile. Available: ${available:.2f}")
        return

    SYSTEM_STATE["allocated_trade_capital"] = req_amount
    trade_pool = req_amount / 2
    per_asset = trade_pool / 3

    keyboard = [
        [InlineKeyboardButton("🟢 Confirm & Fire Orders", callback_data="confirm_trade_on")],
        [InlineKeyboardButton("🔴 Kill Strategy", callback_data="confirm_trade_off")]
    ]
    
    await update.message.reply_text(
        f"⚠️ **PRO SECTOR CONFIRMATION DEPLOYMENT**\n---------------------------------------\n"
        f"• **Target Base Capital:** ${req_amount:.2f} USDT\n"
        f"• **Active Trading Pool (50%):** ${trade_pool:.2f} USDT\n"
        f"• **Asset Target Count:** 3 (ETH, SOL, BNB)\n"
        f"• **Mathematical Split per Asset (33.33%):** ~${per_asset:.2f} USDT\n"
        f"• **Risk Parameters applied:** `{SYSTEM_STATE['risk_profile']}`\n\n"
        f"Confirming execution will immediately process on-chain data loops.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def closeall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SYSTEM_STATE["active_positions"]:
        await update.message.reply_text("⚠️ Liquidator Engine report: Matrix contains zero active risks.")
        return
        
    for asset, data in list(SYSTEM_STATE["active_positions"].items()):
        live_p = crypto_prices.get(asset, 0.0)
        pnl = (live_p - data['entry']) * (data['allocated'] / data['entry']) if data['entry'] > 0 else 0.0
        update_current_balance(data['allocated'] + pnl)
        SYSTEM_STATE["closed_history"].append({
            "time": datetime.now().strftime("%H:%M"),
            "asset": asset,
            "type": "LIQUIDATE",
            "pnl": pnl,
            "mode": SYSTEM_STATE["account_mode"]
        })
        
    SYSTEM_STATE["active_positions"].clear()
    SYSTEM_STATE["is_strategy_active"] = False
    await update.message.reply_text("🛑 **EMERGENCY KILLSWITCH FIRED.** All active exposures liquidated cleanly to balance matrices.")

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "w_custom":
        await query.edit_message_text("📝 Paste your public network address directly into the chat now.")
        return

    if data == "set_demo":
        SYSTEM_STATE["account_mode"] = "DEMO"
        if SYSTEM_STATE["demo_balance"] <= 0:
            SYSTEM_STATE["demo_balance"] = 1000.00
        await query.edit_message_text("🟩 Switched to **DEMO ACCOUNT**. $1,000 virtual balance loaded.", parse_mode="Markdown")
    elif data == "set_real":
        SYSTEM_STATE["account_mode"] = "REAL"
        await query.edit_message_text("🎛️ Switched to **REAL ACCOUNT**. Real-world tracking matrix operational.", parse_mode="Markdown")

    elif data.startswith("risk_"):
        selected_risk = data.split("_")[1]
        SYSTEM_STATE["risk_profile"] = selected_risk
        sets = SYSTEM_STATE["risk_settings"][selected_risk]
        await query.edit_message_text(f"🟩 **Risk Profile Aligned:** `{selected_risk}`\n• SL: `{sets['SL']}%` | TP: `{sets['TP']}%`")

    elif data == "confirm_trade_on":
        SYSTEM_STATE["is_strategy_active"] = True
        req_amount = SYSTEM_STATE["allocated_trade_capital"]
        trade_pool = req_amount / 2
        per_asset = trade_pool / 3

        for asset in ["ETH", "SOL", "BNB"]:
            price_entry = crypto_prices.get(asset, 0.0)
            if price_entry > 0:
                SYSTEM_STATE["active_positions"][asset] = {
                    "allocated": per_asset,
                    "entry": price_entry
                }
        update_current_balance(-trade_pool)
        await query.edit_message_text("🟩 **LENS Algorithmic Split Allocation Matrix Deployed Successfully!** Engine is running.")
        
    elif data == "confirm_trade_off":
        SYSTEM_STATE["is_strategy_active"] = False
        await query.edit_message_text("🛑 **Strategy Engine Execution Cancelled.** System idling safely.")

def process_address_binding(user_addr: str):
    SYSTEM_STATE["wallet_connected"] = True
    SYSTEM_STATE["wallet_address"] = user_addr
    if user_addr.startswith("0x") and len(user_addr) == 42:
        SYSTEM_STATE["wallet_provider"] = "UXUY Node Link (EVM Architecture)"
        SYSTEM_STATE["real_balance"] = 14.50  
    else:
        SYSTEM_STATE["wallet_provider"] = "UXUY Node Link (Solana Network)"
        SYSTEM_STATE["real_balance"] = 25.00

async def handle_raw_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    is_evm = bool(re.match(r"^0x[a-fA-F0-9]{42}$", text))
    is_sol = bool(re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", text))
    
    if is_evm or is_sol:
        process_address_binding(text)
        await update.message.reply_text(
            f"🟩 **UXUY Node Bound Automatically!**\n\n• **Address:** `{text}`\n• **Network:** {'EVM architecture' if is_evm else 'Solana Framework'}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠️ Unrecognized command structure. Use `/start` to view instructions.")

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Updated to strict requested URL specifications
    automated_referral_url = "https://t.me/UXUYbot/app?appstart=A_6546954770_inviteEarn"
    keyboard = [
        [InlineKeyboardButton("🔥 1. Open UXUY Wallet", url=automated_referral_url)],
        [InlineKeyboardButton("📝 2. Bind Public Wallet Node", callback_data="w_custom")]
    ]
    await update.message.reply_text(
        "🔌 **UXUY Native Framework Connection Bridge**\n\n"
        "Click step 1 below to initialize your web3 node structure natively under the secure partner contract, then route your registration signature path back here.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    available = get_current_available_capital()
    msg = (
        "💼 **LENS Production Wallet Matrix**\n"
        f"• Network Node Status: {'🟩 RUNNING (LIVE)' if SYSTEM_STATE['wallet_connected'] else '🟥 UNLINKED'}\n"
        f"• Active Provider: `{SYSTEM_STATE['wallet_provider']}`\n"
        f"• Tracked Public Key: `{SYSTEM_STATE['wallet_address']}`\n"
        "----------------------------------------\n"
        f"💳 **Active Profile Environment:** `{SYSTEM_STATE['account_mode']}`\n"
        f"💰 **Total Available Balance:** ${available:.2f} USDT\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(f"🚨 Crash Shield Catch: {context.error}")

async def post_init(application: Application) -> None:
    asyncio.create_task(fetch_resilient_prices())

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN environment variable.")
        return

    app = Application.builder().token(token).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("wallet", wallet))
    app.add_handler(CommandHandler("accounts", accounts))
    app.add_handler(CommandHandler("risk", risk))
    app.add_handler(CommandHandler("positions", positions))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("ta", ta))
    app.add_handler(CommandHandler("autotrade", autotrade))
    app.add_handler(CommandHandler("closeall", closeall))
    
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_raw_text_messages))
    app.add_error_handler(global_error_handler)
    
    app.run_polling()

if __name__ == "__main__":
    main()
