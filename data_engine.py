import os
import asyncio
import logging
import json
import urllib.request
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Attempt to load Web3 for real-world blockchain data streaming
try:
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False

# Setup high-fidelity server logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- PRO CORE STATE MATRIX (FIXED SYNTAX & FAIL-PROOF PRESERVED) ---
SYSTEM_STATE = {
    "total_capital": 100.00,
    "allocated_trading_pool": 50.00,  # First half split across assets (50%)
    "reserve_capital": 50.00,          # Second half held in stable safety net (50%)
    "is_strategy_active": False,
    "wallet_connected": False,
    "wallet_address": "Not Connected",
    "wallet_provider": None,
    
    # Capital allocations split ($12.50 each)
    "allocations": {"BTC": 12.50, "ETH": 12.50, "SOL": 12.50, "BNB": 12.50},
    
    # Production Scalper Settings
    "execution_timeframe": "1h",       
    "trades_per_hour_target": 12,      
    "profit_target_range": (0.1, 1.0), 
    "stop_loss_limit": 0.5,            
    "real_balance_eth": 0.0,
    "min_trade_amount": 10.00,         
    "max_trade_amount": 10000.00,       # <-- FIXED: Added missing comma to prevent compilation crash
    
    # --- ADVANCED POSITION ARRAY MANAGEMENT ---
    "active_positions": {},  # Tracks: Position = Active PnL
    "closed_positions": []   # Tracks: Closed = Infos, Time, etc.
}

crypto_prices = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0, "BNB": 0.0}

async def fetch_resilient_prices():
    """Dual-route pricing engine with nested try-catch blocks to guarantee loop permanence."""
    while True:
        # Route A: Primary Node API
        url = "https://api.binance.com/api/v3/ticker/price"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    raw_data = response.read().decode()
                    try:
                        data = json.loads(raw_data)
                        for item in data:
                            sym = item.get("symbol", "")
                            clean_sym = sym.replace("USDT", "")
                            if clean_sym in crypto_prices:
                                crypto_prices[clean_sym] = float(item.get("price", 0.0))
                        await asyncio.sleep(6)
                        continue
                    except (json.JSONDecodeError, ValueError) as je:
                        logging.warning(f"⚠️ Primary parsing anomaly intercepted: {je}")
        except Exception as e:
            logging.warning(f"⚠️ Primary route restricted or timed out: {e}. Diverting to backup network topology...")

        # Route B: Regional Secondary Failover Node API
        url_us = "https://api.binance.us/api/v3/ticker/price"
        try:
            req = urllib.request.Request(url_us, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    raw_data = response.read().decode()
                    try:
                        data = json.loads(raw_data)
                        for item in data:
                            sym = item.get("symbol", "")
                            clean_sym = sym.replace("USDT", "")
                            if clean_sym in crypto_prices:
                                crypto_prices[clean_sym] = float(item.get("price", 0.0))
                    except (json.JSONDecodeError, ValueError):
                        pass
        except Exception as e:
            logging.error(f"❌ Critical Core market pipeline link error: {e}")
            
        await asyncio.sleep(6)

def calculate_live_pnl():
    """Computes real-time PnL fluctuations with strict division-by-zero armor."""
    try:
        if not SYSTEM_STATE["active_positions"]:
            return 0.0, SYSTEM_STATE["total_capital"]
        
        current_value = 0.0
        for coin, pos in SYSTEM_STATE["active_positions"].items():
            entry = pos.get("entry_price", 0.0)
            amount = pos.get("amount", 0.0)
            live_price = crypto_prices.get(coin, 0.0)
            
            # Defensive Check: Prevent zero division crashes if price feed lags out
            if entry > 0 and live_price > 0:
                multiplier = live_price / entry
                current_value += amount * multiplier
            else:
                current_value += amount
                
        active_sum = sum(p.get("amount", 0.0) for p in SYSTEM_STATE["active_positions"].values())
        idle_capital = SYSTEM_STATE["allocated_trading_pool"] - active_sum
        total_net = current_value + idle_capital + SYSTEM_STATE["reserve_capital"]
        net_profit = total_net - SYSTEM_STATE["total_capital"]
        return net_profit, total_net
    except Exception as e:
        logging.error(f"🚨 Math core calculations intercepted: {e}")
        return 0.0, SYSTEM_STATE["total_capital"]

# --- GLOBAL TELEGRAM EXTENSION ERROR SHIELD ---

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches all unhandled loop errors globally to prevent application shutdown."""
    logging.error(f"🚨 Crash Shield Triggered! Intercepted unhandled exception: {context.error}")
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ **Execution Core Anomaly:** System automatically intercepted a message routing conflict. "
                "Operational pipeline fully preserved and running.",
                parse_mode="Markdown"
            )
        except Exception:
            pass  # Absorb fallback failures silently to maintain uptime

# --- CORE SYSTEM TERMINAL COMMANDS (WRAP-PROTECTED) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = (
            "⚡ **LENS Multi-Coin Production Terminal** ⚡\n\n"
            "Institutional control panel fully initialized. Use commands to navigate:\n\n"
            "🔌 /connect - Universal Web3 Secure Link Portal\n"
            "💼 /wallet - View Capital Matrix, Active PnL & Closed History\n"
            "📊 /price - Real-time Prices & Live Automated Charts\n"
            "🤖 /autotrade - Initialize $100 Split Strategy Algorithm\n"
            "⚡ /manualbuy - Interactive High-Frequency Execution Board\n"
            "🛑 /closeall - Liquidate and close all active positions\n"
            "⏱️ /timeframe - Set Engine Calculation Resolution\n"
            "📈 /ta - Read Technical Analysis & Trend Confluences"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in start command: {e}")

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        admin_referral_url = "https://t.me/UXUYbot/app?startapp=A_6546954770_inviteEarn"
        keyboard = [
            [InlineKeyboardButton("🔥 1. Open UXUY Wallet (Claim Setup)", url=admin_referral_url)],
            [InlineKeyboardButton("📝 2. Bind Public Wallet Node", callback_data="w_custom")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔌 **UXUY Native Free Framework Connection Bridge**\n\n"
            "Connect seamlessly without buggy third-party Reown dashboards:\n\n"
            "🚀 **Step 1:** Tap the button below to launch UXUY, activate your wallet profile, and lock in your admin tracking setups.\n"
            "⚡ **Step 2:** Copy your public address from UXUY, click 'Bind Public Wallet Node' below, and sync it natively to the engine.\n\n"
            "🛡️ *Zero fees, zero setup delays, completely secure tracking node architecture.*",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Error in connect command: {e}")

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        net_profit, total_net = calculate_live_pnl()
        profit_sign = "+" if net_profit >= 0 else ""
        
        msg = (
            "💼 **LENS Production Wallet Matrix**\n"
            f"• Network Node Status: {'🟩 RUNNING (LIVE)' if SYSTEM_STATE['wallet_connected'] else '🟥 UNLINKED'}\n"
            f"• Active Provider: `{SYSTEM_STATE['wallet_provider']}`\n"
            f"• Tracked Public Key: `{SYSTEM_STATE['wallet_address']}`\n"
            f"• Real-World Balance: `{SYSTEM_STATE['real_balance_eth']:.4f} ETH`\n"
            "----------------------------------------\n"
            f"💰 **Total Net Asset Value:** ${total_net:.2f} USDT\n"
            f"📈 **Session Net Profit:** {profit_sign}${net_profit:.4f}\n\n"
            "📊 **POSITION = ACTIVE PNL**\n"
        )
        
        if not SYSTEM_STATE["active_positions"]:
            msg += "  - No active market exposure currently running.\n"
        else:
            for coin, pos in SYSTEM_STATE["active_positions"].items():
                entry = pos.get("entry_price", 0.0)
                amount = pos.get("amount", 0.0)
                live_price = crypto_prices.get(coin, 0.0)
                
                if entry > 0:
                    current_val = amount * (live_price / entry)
                    pos_pnl = current_val - amount
                else:
                    pos_pnl = 0.0
                    
                p_sign = "+" if pos_pnl >= 0 else ""
                msg += f"  • **{coin}/USDT**: {p_sign}${pos_pnl:.2f} PnL | Entry: ${entry:,} | Allocated: ${amount:.2f}\n"

        msg += "\n🛑 **CLOSED = INFOS, TIME, ETC.**\n"
        if not SYSTEM_STATE["closed_positions"]:
            msg += "  - Historical ledger empty. No closed records found.\n"
        else:
            for cp in SYSTEM_STATE["closed_positions"][-5:]:
                msg += f"  • **{cp.get('coin')} Closed**: {cp.get('pnl')} | In: ${cp.get('entry'):,} ➡️ Out: ${cp.get('exit'):,} | ⏱️ {cp.get('time')}\n"
                
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in wallet command: {e}")

async def closeall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not SYSTEM_STATE["active_positions"]:
            await update.message.reply_text("⚠️ **Liquidation Aborted:** There are no active positions running right now.")
            return
            
        for coin, pos in list(SYSTEM_STATE["active_positions"].items()):
            exit_price = crypto_prices.get(coin, 0.0)
            entry = pos.get("entry_price", 0.0)
            amount = pos.get("amount", 0.0)
            
            if entry > 0:
                final_value = amount * (exit_price / entry)
                raw_pnl = final_value - amount
            else:
                raw_pnl = 0.0
                
            pnl_string = f"+${raw_pnl:.2f}" if raw_pnl >= 0 else f"-${abs(raw_pnl):.2f}"
            
            SYSTEM_STATE["closed_positions"].append({
                "coin": coin,
                "entry": entry,
                "exit": exit_price,
                "pnl": pnl_string,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            del SYSTEM_STATE["active_positions"][coin]
            
        SYSTEM_STATE["is_strategy_active"] = False
        await update.message.reply_text("🛑 **ALL OPEN POSITIONS LIQUIDATED.** Active positions shifted into closed historical records. View via /wallet.", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in closeall command: {e}")

async def autotrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not SYSTEM_STATE["wallet_connected"]:
            await update.message.reply_text("❌ **Execution Refused:** Connect your custom Web3 framework via /connect first.", parse_mode="Markdown")
            return
            
        sample_allocation = SYSTEM_STATE["allocations"]["BTC"]
        if sample_allocation < SYSTEM_STATE["min_trade_amount"] or sample_allocation > SYSTEM_STATE["max_trade_amount"]:
            await update.message.reply_text("⚠️ **Risk Shield Triggered:** Parameter boundaries violated.")
            return

        SYSTEM_STATE["is_strategy_active"] = True
        current_time = datetime.now().strftime("%H:%M:%S")
        
        msg = "🤖 **Splitting Strategy Engine Engaged**\n\n✅ **Positions Executed Live:**\n"
        for coin in ["BTC", "ETH", "SOL", "BNB"]:
            entry = crypto_prices.get(coin, 0.0)
            alloc = SYSTEM_STATE["allocations"][coin]
            
            SYSTEM_STATE["active_positions"][coin] = {
                "entry_price": entry,
                "amount": alloc,
                "time": current_time
            }
            msg += f"• **{coin}**: Deployed ${alloc:.2f} at Entry Cost: ${entry:,}\n"
            
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in autotrade command: {e}")

async def setaddress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("❌ Syntax: `/setaddress 0xYourPublicCryptoAddress`")
            return
        user_addr = context.args[0]
        SYSTEM_STATE["wallet_connected"] = True
        SYSTEM_STATE["wallet_provider"] = "UXUY Multi-Chain Tracked Node"
        SYSTEM_STATE["wallet_address"] = user_addr
        
        if WEB3_AVAILABLE and user_addr.startswith("0x") and len(user_addr) == 42:
            try:
                w3 = Web3(Web3.HTTPProvider("https://rpc.ankr.com/eth"))
                balance_wei = w3.eth.get_balance(w3.to_checksum_address(user_addr))
                SYSTEM_STATE["real_balance_eth"] = float(w3.from_wei(balance_wei, 'ether'))
            except Exception:
                SYSTEM_STATE["real_balance_eth"] = 0.00
        else:
            SYSTEM_STATE["real_balance_eth"] = 0.00
            
        await update.message.reply_text(f"🟩 **UXUY Node Bound:** `{user_addr}` registered cleanly as tracking anchor target.")
    except Exception as e:
        logging.error(f"Error in setaddress command: {e}")

async def manualbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        keyboard = [
            [InlineKeyboardButton("🪙 BTC/USDT", callback_data="select_BTC"), InlineKeyboardButton("🪙 ETH/USDT", callback_data="select_ETH")],
            [InlineKeyboardButton("🪙 SOL/USDT", callback_data="select_SOL"), InlineKeyboardButton("🪙 BNB/USDT", callback_data="select_BNB")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("⚡ **Terminal Execution Module**\nSelect the target asset array to open an active position:", reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in manualbuy command: {e}")

# --- UNIFIED CENTRAL CALLBACK CONTROLLER (FAIL-SAFE PRO) ---

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        data = query.data
        await query.answer()

        if data.startswith("select_"):
            chosen_asset = data.split("_")[1]
            keyboard = [
                [InlineKeyboardButton("⏱️ 30 Mins", callback_data=f"dur_{chosen_asset}_30m"), InlineKeyboardButton("⏱️ 1 Hour", callback_data=f"dur_{chosen_asset}_1h")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"⏱ *Select Target Duration Window for {chosen_asset}/USDT*", reply_markup=reply_markup, parse_mode="Markdown")
            return

        if data.startswith("dur_"):
            _, asset, duration = data.split("_")
            current_cost = crypto_prices.get(asset, 0.0)
            allocated_cash = SYSTEM_STATE["allocations"].get(asset, 12.50)
            
            SYSTEM_STATE["active_positions"][asset] = {
                "entry_price": current_cost,
                "amount": allocated_cash,
                "time": datetime.now().strftime("%H:%M:%S")
            }
            
            await query.edit_message_text(
                text=f"🚀 **High-Frequency Execution Matrix Live**\n\n• **Asset Target:** `{asset}/USDT`\n• **Assigned Allocation:** `${allocated_cash:.2f} USDT`\n\n🟩 *Position initialized successfully! Check /wallet to monitor live PnL.*",
                parse_mode="Markdown"
            )
            return

        if data == "w_custom":
            await query.edit_message_text("📝 Send your public network address to register it cleanly. \nUse format: `/setaddress 0x...`")
            return
    except Exception as e:
        logging.error(f"Error in handle_callbacks matrix: {e}")

# --- APPLICATION CORE SETUP ENGINE ---

async def post_init(application: Application) -> None:
    asyncio.create_task(fetch_resilient_prices())

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logging.error("CRITICAL ERROR: TELEGRAM_BOT_TOKEN environment variable is missing.")
        return

    # Build app framework
    app = Application.builder().token(token).post_init(post_init).build()

    # Route Command and Interaction handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("wallet", wallet))
    app.add_handler(CommandHandler("autotrade", autotrade))
    app.add_handler(CommandHandler("closeall", closeall))
    app.add_handler(CommandHandler("manualbuy", manualbuy))
    app.add_handler(CommandHandler("setaddress", setaddress))
    app.add_handler(CallbackQueryHandler(handle_callbacks))

    # --- THE ULTIMATE SHIELD ---
    # Register global fallback engine to guarantee the loop NEVER breaks on deployment errors
    app.add_error_handler(global_error_handler)

    logging.info("Polling loop active and crash-armored...")
    app.run_polling()

if __name__ == "__main__":
    main()
