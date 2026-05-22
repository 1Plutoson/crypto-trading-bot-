import asyncio
import json
import os
import csv
from datetime import datetime
import websockets
import pandas as pd
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- CONFIGURATION & MULTI-COIN MEMORY ---
SUPPORTED_COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
TRADE_SIZE_USDT = 2500.00
STATE_FILE = "bot_state.json"
LEDGER_FILE = "trade_ledger.csv"  # File name for our automated trade logger

market_memory = {coin: pd.DataFrame() for coin in SUPPORTED_COINS}
latest_prices = {coin: 0.0 for coin in SUPPORTED_COINS}

# --- PERSISTENT STATE STORAGE ---
def load_state():
    global wallet, trading_state, active_chat_id
    
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                wallet = state.get("wallet")
                trading_state = state.get("trading_state")
                active_chat_id = state.get("active_chat_id")
                print("💾 Persistent State Loaded Successfully!")
                return
        except Exception as e:
            print(f"⚠️ Error loading state file, creating fresh state: {e}")

    print("📝 No state file found. Creating a fresh $10,000 portfolio tracker...")
    wallet = {
        "USDT": 10000.00,
        "BTCUSDT": 0.0,
        "ETHUSDT": 0.0,
        "SOLUSDT": 0.0,
        "BNBUSDT": 0.0
    }
    trading_state = {
        coin: {"in_position": False, "buy_price": 0.0, "highest_price": 0.0} for coin in SUPPORTED_COINS
    }
    active_chat_id = None

def save_state():
    try:
        state = {
            "wallet": wallet,
            "trading_state": trading_state,
            "active_chat_id": active_chat_id
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
        print("💾 State auto-saved to disk.")
    except Exception as e:
        print(f"⚠️ Failed to auto-save state: {e}")

# --- ANALYTICS LEDGER ENGINE ---
def log_trade(symbol, action, buy_price, exit_price, profit):
    """Appends trade metrics into a local CSV spreadsheet file."""
    file_exists = os.path.exists(LEDGER_FILE)
    try:
        with open(LEDGER_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            # Add headers if it's a completely new file
            if not file_exists:
                writer.writerow(["Timestamp", "Asset", "Exit_Reason", "Buy_Price", "Exit_Price", "Net_Profit_USDT"])
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([timestamp, symbol, action, f"{buy_price:.2f}", f"{exit_price:.2f}", f"{profit:.2f}"])
        print(f"📊 Trade logged to {LEDGER_FILE}")
    except Exception as e:
        print(f"⚠️ Failed to log trade to CSV: {e}")

# Initialize baseline variables
wallet = {}
trading_state = {}
active_chat_id = None
load_state()

bot_instance = None

# --- MATHEMATICAL ENGINES ---
def calculate_rsi(price_series, period=14):
    delta = price_series.diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(price_series, fast=12, slow=26, signal=9):
    ema_fast = price_series.ewm(span=fast, adjust=False).mean()
    ema_slow = price_series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

def fetch_historical_data(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=100"
    response = requests.get(url)
    data = response.json()
    df = pd.DataFrame(data, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Vol', 'CT', 'QAV', 'NT', 'TBBAV', 'TBQAV', 'I'])
    df = df[['Time', 'Open', 'High', 'Low', 'Close']].astype(float)
    return df

def evaluate_strategy(symbol):
    df = market_memory[symbol].copy()
    if df.empty or len(df) < 30:
        return "NEUTRAL"
        
    df['RSI'] = calculate_rsi(df['Close'])
    df['MACD'], df['Signal'] = calculate_macd(df['Close'])
    
    current_rsi = df['RSI'].iloc[-1]
    current_macd = df['MACD'].iloc[-1]
    current_signal = df['Signal'].iloc[-1]
    
    macd_bullish = current_macd > current_signal
    macd_bearish = current_macd < current_signal
    
    if current_rsi < 40 and macd_bullish: return "STRONG BUY"
    if current_rsi > 60 and macd_bearish: return "STRONG SELL"
    return "NEUTRAL"

# --- CORE EXECUTION STREAM ---
async def binance_kline_stream():
    streams = "/".join([f"{coin.lower()}@kline_1m" for coin in SUPPORTED_COINS])
    url = f"wss://stream.binance.com:9443/ws/{streams}"
    
    async with websockets.connect(url) as ws:
        print("🟢 Multi-Coin Stream Connected! Scanning BTC, ETH, SOL, BNB...")
        while True:
            message = await ws.recv()
            data = json.loads(message)
            kline = data['k']
            symbol = data['s']
            current_price = float(kline['c'])
            
            if symbol in SUPPORTED_COINS:
                latest_prices[symbol] = current_price
                
                # Dynamic Trailing check running on every raw tick update
                state = trading_state[symbol]
                if state["in_position"]:
                    if current_price > state["highest_price"]:
                        state["highest_price"] = current_price
                        save_state()
                    
                    buy_price = state["buy_price"]
                    peak_price = state["highest_price"]
                    
                    gain_from_buy_to_peak = ((peak_price - buy_price) / buy_price) * 100
                    drop_from_peak = ((peak_price - current_price) / peak_price) * 100
                    current_loss_from_buy = ((current_price - buy_price) / buy_price) * 100
                    
                    sell_reason = None
                    
                    if current_loss_from_buy <= -1.0:
                        sell_reason = "STOP-LOSS"
                    elif gain_from_buy_to_peak >= 3.0 and drop_from_peak >= 1.0:
                        sell_reason = "TRAILING-STOP"
                    
                    if sell_reason:
                        usdt_gained = wallet[symbol] * current_price
                        profit = usdt_gained - (wallet[symbol] * buy_price)
                        
                        wallet["USDT"] += usdt_gained
                        wallet[symbol] = 0.0
                        state["in_position"] = False
                        state["buy_price"] = 0.0
                        state["highest_price"] = 0.0
                        
                        save_state()
                        log_trade(symbol, sell_reason, buy_price, current_price, profit) # Log analytics metrics
                        
                        if active_chat_id and bot_instance:
                            status = "PROFIT 🟢" if profit > 0 else "LOSS 🔴"
                            text = (f"🔴 *AUTO-SELL EXECUTED*\n\n"
                                    f"*Asset:* `{symbol}`\n"
                                    f"*Reason:* {sell_reason} 🛡️\n"
                                    f"*Exit Price:* `${current_price:,.2f}`\n"
                                    f"*Trade Result:* {status} `${profit:,.2f}`")
                            await bot_instance.send_message(chat_id=active_chat_id, text=text, parse_mode='Markdown')

                # Process candlestick closes for standard entry/exit strategies
                if kline['x']:
                    new_row = pd.DataFrame([{'Time': kline['t'], 'Open': float(kline['o']), 'High': float(kline['h']), 'Low': float(kline['l']), 'Close': current_price}])
                    market_memory[symbol] = pd.concat([market_memory[symbol], new_row], ignore_index=True).tail(100)
                    
                    signal = evaluate_strategy(symbol)
                    
                    if signal == "STRONG BUY" and not state["in_position"]:
                        allocation = min(TRADE_SIZE_USDT, wallet["USDT"])
                        if allocation >= 10.0:
                            crypto_bought = allocation / current_price
                            wallet[symbol] = crypto_bought
                            wallet["USDT"] -= allocation
                            state["in_position"] = True
                            state["buy_price"] = current_price
                            state["highest_price"] = current_price
                            
                            save_state()
                            
                            if active_chat_id and bot_instance:
                                text = f"🟢 *AUTO-BUY EXECUTED*\n\nAsset: `{symbol}`\nAmount: `{crypto_bought:.4f}`\nPrice: `${current_price:,.2f}`"
                                await bot_instance.send_message(chat_id=active_chat_id, text=text, parse_mode='Markdown')
                                
                    elif signal == "STRONG SELL" and state["in_position"] and ((state["highest_price"] - buy_price)/buy_price)*100 < 3.0:
                        usdt_gained = wallet[symbol] * current_price
                        profit = usdt_gained - (wallet[symbol] * buy_price)
                        
                        wallet["USDT"] += usdt_gained
                        wallet[symbol] = 0.0
                        state["in_position"] = False
                        state["buy_price"] = 0.0
                        state["highest_price"] = 0.0
                        
                        save_state()
                        log_trade(symbol, "STRATEGY-SELL", buy_price, current_price, profit) # Log analytics metrics
                        
                        if active_chat_id and bot_instance:
                            status = "PROFIT 🟢" if profit > 0 else "LOSS 🔴"
                            text = (f"🔴 *AUTO-SELL EXECUTED*\n\n"
                                    f"*Asset:* `{symbol}`\n"
                                    f"*Reason:* STRATEGY SELL SIGNAL 🔴\n"
                                    f"*Exit Price:* `${current_price:,.2f}`\n"
                                    f"*Trade Result:* {status} `${profit:,.2f}`")
                            await bot_instance.send_message(chat_id=active_chat_id, text=text, parse_mode='Markdown')

# --- USER COMMAND INTERFACES ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global active_chat_id
    active_chat_id = update.effective_chat.id
    save_state()
    text = ("🤖 *Multi-Asset Radar & Analytics Engine Live!*\n\n"
            "Scanning: *BTC, ETH, SOL, BNB*\n"
            "Database: Local spreadsheet log tracking enabled.\n\n"
            "👇 *Dashboard Commands:*\n"
            "/wallet - View distributed asset portfolio\n"
            "/price - View live stream ticker costs\n"
            "/ta - Check confluence matrix snapshots\n"
            "/report - Output deep portfolio audit statistics")
    await update.message.reply_text(text, parse_mode='Markdown')

async def get_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_crypto_value = 0.0
    crypto_lines = ""
    
    for coin in SUPPORTED_COINS:
        amt = wallet.get(coin, 0.0)
        price = latest_prices.get(coin, 0.0)
        value = amt * price
        total_crypto_value += value
        if amt > 0:
            state = trading_state.get(coin, {})
            chg = ((price - state.get("buy_price", price)) / state.get("buy_price", 1)) * 100
            crypto_lines += f"*{coin[:-4]}:* `{amt:.4f}` (~`${value:,.2f}`) PnL: `{chg:+.2f}%`\n"
            
    total_portfolio = wallet.get("USDT", 10000.00) + total_crypto_value
    net_pnl = total_portfolio - 10000.00
    
    text = (f"💼 *Multi-Coin Wallet Summary*\n\n"
            f"*Available Cash:* `${wallet.get('USDT', 10000.00):,.2f} USDT`\n"
            f"{crypto_lines}"
            f"---\n"
            f"*Total Net Portfolio:* `${total_portfolio:,.2f}`\n"
            f"*Total Net Profit:* {'+' if net_pnl >= 0 else ''}`${net_pnl:,.2f}`")
    await update.message.reply_text(text, parse_mode='Markdown')

async def get_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reads the CSV ledger to dynamically calculate and display core trading metrics."""
    if not os.path.exists(LEDGER_FILE):
        await update.message.reply_text("📊 *No trade history recorded yet.* Logging will begin automatically on the first trade close.")
        return

    try:
        df = pd.read_csv(LEDGER_FILE)
        if df.empty:
            await update.message.reply_text("📊 Ledger file is empty.")
            return

        total_trades = len(df)
        wins = len(df[df['Net_Profit_USDT'] > 0])
        losses = len(df[df['Net_Profit_USDT'] <= 0])
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        
        best_trade = df['Net_Profit_USDT'].max()
        worst_trade = df['Net_Profit_USDT'].min()
        
        # Calculate profits per asset
        coin_breakdown = ""
        coin_groups = df.groupby('Asset')['Net_Profit_USDT'].sum()
        for coin, profit in coin_groups.items():
            emoji = "🟢" if profit >= 0 else "🔴"
            coin_breakdown += f"• *{coin[:-4]}:* {emoji} `+{profit:,.2f}`\n" if profit >= 0 else f"• *{coin[:-4]}:* {emoji} `-{abs(profit):,.2f}`\n"

        text = (f"📊 *SYSTEM PERFORMANCE AUDIT*\n\n"
                f"*Total Trades Closed:* `{total_trades}`\n"
                f"*Win Rate:* `{win_rate:.1f}%` ({wins}W / {losses}L)\n\n"
                f"💰 *Net Profit Breakdown:*\n{coin_breakdown}\n"
                f"⭐ *Best Trade:* `+${best_trade:,.2f}`\n"
                f"🛑 *Worst Trade:* `-${abs(worst_trade):,.2f}`")
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Failed to compile statistics report: {e}")

async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ""
    for coin in SUPPORTED_COINS:
        price = latest_prices.get(coin, 0.0)
        lines += f"*{coin[:-4]}:* `${price:,.2f}`\n"
    await update.message.reply_text(f"📊 *Live Market Tick*\n\n{lines}", parse_mode='Markdown')

async def get_ta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ""
    for coin in SUPPORTED_COINS:
        signal = evaluate_strategy(coin)
        price = latest_prices.get(coin, 0.0)
        lines += f"*{coin[:-4]}:* `${price:,.2f}` -> `{signal}`\n"
    await update.message.reply_text(f"📈 *Confluence Matrix Snapshot*\n\n{lines}", parse_mode='Markdown')

async def post_init(application):
    global bot_instance
    bot_instance = application.bot
    print("⏳ Running parallel historical backfills for all assets...")
    for coin in SUPPORTED_COINS:
        market_memory[coin] = fetch_historical_data(coin)
        print(f"  ✅ {coin} memory buffer initialized.")
    print("🚀 Starting bot... Boot up Telegram!")
    asyncio.create_task(binance_kline_stream())

if __name__ == "__main__":
    BOT_TOKEN = "8959355486:AAExJ0nE_-HRrQDG-YzoYws54LYfqWU4_ss"
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("wallet", get_wallet))
    app.add_handler(CommandHandler("price", get_price))
    app.add_handler(CommandHandler("ta", get_ta))
    app.add_handler(CommandHandler("report", get_report))  # Link command interface
    app.run_polling()
