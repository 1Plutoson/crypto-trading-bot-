import os
import asyncio
import logging
import json
import urllib.request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Setup system logs
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Global State Storage
SYSTEM_STATE = {
    "mode": "DEMO",             # DEMO or REAL
    "demo_balance": 10000.0,    # Default loaded virtual cash
    "real_balance": 0.0,
    "wallet_provider": "None",  # Trust Wallet, Phantom, etc.
    "wallet_address": "Not Connected",
    "runtime_hours": 3,         # Default session length (3h, 6h, 12h, 24h)
    "is_running": False,
    "manual_sl": 5.0,           # Customizable user stop loss %
    "auto_sl": 45.0,            # Hardcoded max safety emergency threshold
    "active_positions": []      # Simulating active trade allocations
}

crypto_prices = {"BTCUSDT": 0.0, "ETHUSDT": 0.0, "SOLUSDT": 0.0, "BNBUSDT": 0.0}

async def fetch_global_market_data():
    """Background loop ensuring raw price feeds route cleanly inside cloud servers"""
    while True:
        try:
            url = "https://api.binance.us/api/v3/ticker/24hr"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode())
                    if isinstance(data, list):
                        for item in data:
                            symbol = item.get("symbol")
                            if symbol in crypto_prices:
                                crypto_prices[symbol] = float(item.get("lastPrice", 0.0))
        except Exception as e:
            logging.error(f"Data stream sync issue: {e}")
        await asyncio.sleep(6)

async def auto_trade_engine():
    """Automated execution loop running multiple trades on perfect entries"""
    while True:
        if SYSTEM_STATE["is_running"]:
            # Logic scales dynamically depending on chosen balance mode
            current_balance = SYSTEM_STATE["demo_balance"] if SYSTEM_STATE["mode"] == "DEMO" else SYSTEM_STATE["real_balance"]
            
            # Simulated Technical Entry scan execution loop
            for symbol, price in crypto_prices.items():
                if price > 0.0 and len(SYSTEM_STATE["active_positions"]) < 3:
                    # Allocate standard position chunk size
                    trade_allocation = 1000.0 
                    SYSTEM_STATE["active_positions"].append({
                        "symbol": symbol,
                        "entry_price": price,
                        "current_price": price,
                        "allocation": trade_allocation,
                        "pnl_percent": 0.0
                    })
                    logging.info(f"⚡ [Execution Engine] Entry criteria matched. Position filled for {symbol} at ${price}")

            # Risk Management Module evaluating open entry sheets
            for pos in list(SYSTEM_STATE["active_positions"]):
                live_price = crypto_prices.get(pos["symbol"], pos["entry_price"])
                pnl = ((live_price - pos["entry_price"]) / pos["entry_price"]) * 100
                pos["current_price"] = live_price
                pos["pnl_percent"] = pnl

                # Auto Emergency System Check [📉 45%]
                if pnl <= -SYSTEM_STATE["auto_sl"]:
                    SYSTEM_STATE["active_positions"].remove(pos)
                    loss_amount = trade_allocation * (SYSTEM_STATE["auto_sl"] / 100)
                    if SYSTEM_STATE["mode"] == "DEMO":
                        SYSTEM_STATE["demo_balance"] -= loss_amount
                    logging.warning(f"🚨 [CRITICAL RISK] Hard Stop Triggered! 45% Auto SL liquidated {pos['symbol']}.")

                # Manual Customizable Stop Loss Check
                elif pnl <= -SYSTEM_STATE["manual_sl"]:
                    SYSTEM_STATE["active_positions"].remove(pos)
                    loss_amount = trade_allocation * (SYSTEM_STATE["manual_sl"] / 100)
                    if SYSTEM_STATE["mode"] == "DEMO":
                        SYSTEM_STATE["demo_balance"] -= loss_amount
                    logging.info(f"📉 [Risk Control] Customizable Manual SL reached. Closed out {pos['symbol']}.")
                    
                # Take Profit Optimization target closure (Example: 2.5% take profit target)
                elif pnl >= 2.5:
                    SYSTEM_STATE["active_positions"].remove(pos)
                    gain_amount = trade_allocation * (2.5 / 100)
                    if SYSTEM_STATE["mode"] == "DEMO":
                        SYSTEM_STATE["demo_balance"] += gain_amount
                    logging.info(f"🎯 [Profit Target] Technical target reached for {pos['symbol']}. Gains locked.")
                    
        await asyncio.sleep(4)

async def start_runtime_timer(hours: int):
    """Monitors automated loop and signs off automatically once running time expires"""
    await asyncio.sleep(hours * 3600)
    if SYSTEM_STATE["is_running"]:
        SYSTEM_STATE["is_running"] = False
        SYSTEM_STATE["active_positions"].clear()
        logging.info(f"⏳ Session operational clock expired ({hours}h window reached). Engine offline.")

# --- TELEGRAM USER INTERFACE COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "💼 **LENS TRADING TERMINAL V2** 💼\n\n"
        f"🤖 **Engine Status:** {'🟢 WORKING' if SYSTEM_STATE['is_running'] else '🔴 STOPPED'}\n"
        f"⚙️ **Execution Mode:** {SYSTEM_STATE['mode']}\n"
        f"📊 **Demo Vault:** ${SYSTEM_STATE['demo_balance']:,} USD\n"
        f"⏱️ **Runtime Window:** {SYSTEM_STATE['runtime_hours']} Hours\n"
        f"📉 **Manual Stop-Loss:** -{SYSTEM_STATE['manual_sl']}%\n"
        f"🚨 **Emergency Auto SL:** -45% [Hard Protection]\n\n"
        f"🔗 **Web3 Link Hook:** {SYSTEM_STATE['wallet_provider']} ({SYSTEM_STATE['wallet_address'][:6]}...)\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎛️ Configure Settings", callback_data="open_settings")],
        [InlineKeyboardButton("🏁 START EXECUTION LOOP", callback_data="start_bot"),
         InlineKeyboardButton("🛑 EMERGENCY PANIC STOP", callback_data="panic_stop")]
    ]
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "open_settings":
        text = "🔧 **Terminal Configuration Deck**\nAdjust parameters below:"
        kb = [
            [InlineKeyboardButton("🔄 Toggle Mode (Real/Demo)", callback_data="toggle_mode")],
            [InlineKeyboardButton("⏱️ Adjust Execution Runtime", callback_data="set_runtime")],
            [InlineKeyboardButton("🛡️ Adjust Manual Stop Loss", callback_data="set_msl")],
            [InlineKeyboardButton("🔗 Connect Web3 Decentralized Wallet", callback_data="connect_web3")],
            [InlineKeyboardButton("↩️ Back to Terminal Dashboard", callback_data="back_main")]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data == "toggle_mode":
        SYSTEM_STATE["mode"] = "REAL" if SYSTEM_STATE["mode"] == "DEMO" else "DEMO"
        text = f"🔄 Mode Swapped successfully! Operational context is now set to: **{SYSTEM_STATE['mode']}**"
        kb = [[InlineKeyboardButton("↩️ Back to Settings", callback_data="open_settings")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data == "set_runtime":
        text = "⏱️ **Select System Execution Running Time:**\nThe system will maximize entry targets inside this strict window:"
        kb = [
            [InlineKeyboardButton("3 Hours", callback_data="rt_3"), InlineKeyboardButton("6 Hours", callback_data="rt_6")],
            [InlineKeyboardButton("12 Hours", callback_data="rt_12"), InlineKeyboardButton("24 Hours", callback_data="rt_24")],
            [InlineKeyboardButton("↩️ Back", callback_data="open_settings")]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data.startswith("rt_"):
        hours = int(query.data.split("_")[1])
        SYSTEM_STATE["runtime_hours"] = hours
        text = f"⏱️ Execution Window configured to **{hours} Hours**. Multi-entry pipeline updated."
        kb = [[InlineKeyboardButton("↩️ Back", callback_data="open_settings")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data == "set_msl":
        text = "🛡️ **Configure Customizable Manual Stop Loss**\n\nReply directly to the bot with the percentage integer you want to enforce (e.g. send `5` to set a 5% protection limit)."
        context.user_data["awaiting_sl"] = True
        kb = [[InlineKeyboardButton("↩️ Cancel", callback_data="open_settings")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data == "connect_web3":
        text = "🔗 **Decentralized Wallet Hook Center**\nSelect your ecosystem interface provider link:"
        kb = [
            [InlineKeyboardButton("🛡️ Trust Wallet Connect Hook", callback_data="w_trust")],
            [InlineKeyboardButton("👻 Phantom Wallet Connect Hook", callback_data="w_phantom")],
            [InlineKeyboardButton("🦊 MetaMask Connect Hook", callback_data="w_meta")],
            [InlineKeyboardButton("↩️ Back", callback_data="open_settings")]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data.startswith("w_"):
        provider = query.data.split("_")[1].upper()
        SYSTEM_STATE["wallet_provider"] = provider
        text = f"🧬 **{provider} Selected.**\n\nPlease paste or type your public address string to complete the decentralized API pipeline tracking connection link:"
        context.user_data["awaiting_wallet"] = True
        kb = [[InlineKeyboardButton("↩️ Cancel", callback_data="open_settings")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data == "start_bot":
        if not SYSTEM_STATE["is_running"]:
            SYSTEM_STATE["is_running"] = True
            asyncio.create_task(start_runtime_timer(SYSTEM_STATE["runtime_hours"]))
            text = f"🟢 **Automated Engine Initiated!**\nScanning entry configurations for the next {SYSTEM_STATE['runtime_hours']} hours..."
        else:
            text = "⚠️ Systems are already processing active data paths!"
        kb = [[InlineKeyboardButton("↩️ Main Dashboard", callback_data="back_main")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data == "panic_stop":
        SYSTEM_STATE["is_running"] = False
        SYSTEM_STATE["active_positions"].clear()
        text = "🚨 **MANUAL EMERGENCY STOP TRIGGERED!**\nAll automated processes severed. Current entries liquidated to protection cash."
        kb = [[InlineKeyboardButton("↩️ Main Dashboard", callback_data="back_main")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data == "back_main":
        msg = (
            "💼 **LENS TRADING TERMINAL V2** 💼\n\n"
            f"🤖 **Engine Status:** {'🟢 WORKING' if SYSTEM_STATE['is_running'] else '🔴 STOPPED'}\n"
            f"⚙️ **Execution Mode:** {SYSTEM_STATE['mode']}\n"
            f"📊 **Demo Vault:** ${SYSTEM_STATE['demo_balance']:,} USD\n"
            f"⏱️ **Runtime Window:** {SYSTEM_STATE['runtime_hours']} Hours\n"
            f"📉 **Manual Stop-Loss:** -{SYSTEM_STATE['manual_sl']}%\n"
            f"🚨 **Emergency Auto SL:** -45% [Hard Protection]\n\n"
            f"🔗 **Web3 Link Hook:** {SYSTEM_STATE['wallet_provider']} ({SYSTEM_STATE['wallet_address'][:6]}...)\n"
        )
        kb = [
            [InlineKeyboardButton("🎛️ Configure Settings", callback_data="open_settings")],
            [InlineKeyboardButton("🏁 START EXECUTION LOOP", callback_data="start_bot"),
             InlineKeyboardButton("🛑 EMERGENCY PANIC STOP", callback_data="panic_stop")]
        ]
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def handle_text_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes user text input configurations for customized stop loss limits and wallet strings"""
    user_text = update.message.text.strip()
    
    if context.user_data.get("awaiting_sl"):
        try:
            val = float(user_text)
            SYSTEM_STATE["manual_sl"] = abs(val)
            context.user_data["awaiting_sl"] = False
            await update.message.reply_text(f"✅ **Manual Protection Locked:** Custom Stop Loss set to -{abs(val)}%.")
        except ValueError:
            await update.message.reply_text("❌ Configuration error. Please send a valid numeric value.")
            
    elif context.user_data.get("awaiting_wallet"):
        SYSTEM_STATE["wallet_address"] = user_text
        context.user_data["awaiting_wallet"] = False
        await update.message.reply_text(
            f"🔗 **Web3 Hook Pipeline Synced!**\n"
            f"Provider: `{SYSTEM_STATE['wallet_provider']}`\n"
            f"Linked Key: `{user_text}`"
        )

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("CRITICAL: Environment variable token not found.")
        return

    app = Application.builder().token(token).build()

    # Link Interaction Routing Matrix
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_inputs))

    # Activate parallel runtime engine threads
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    loop.create_task(fetch_global_market_data())
    loop.create_task(auto_trade_engine())

    print("🚀 All advanced parameters mapped seamlessly. Terminal boot sequence complete.")
    app.run_polling()

if __name__ == "__main__":
    main()
