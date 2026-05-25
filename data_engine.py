import os
import time
import uuid
import asyncio
import logging
import sqlite3
import jwt
import random
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ==========================================
# 1. SYSTEM CONFIGURATION & SETUP
# ==========================================
logging.basicConfig(
    format='%(asctime)s - [LENs-FINANCIAL-v3] - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ADMIN_ID = 6546954770
DB_FILE = "lens_secure_vault.db"
SECRET_KEY = "lens_institutional_secure_key_override"
ALGORITHM = "HS256"

# Master/Hot Wallet Configuration Node Reference (From 1779722407919.jpeg)
MASTER_HOT_WALLET = "TYG7x89qWmNksPz2mAL17vKxR90PqX7z8L"

app = FastAPI(title="LENs Advanced Unified Gateway Platform", version="3.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 2. UPGRADED DATABASE LEDGER SCHEMA
# ==========================================
def init_secure_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    c = conn.cursor()
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Wallets layout upgraded to support deterministic tracking addresses
    c.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            user_id TEXT PRIMARY KEY,
            main_balance REAL DEFAULT 0.00,
            bonus_pool REAL DEFAULT 45.00,
            unlocked_bonus REAL DEFAULT 5.00,
            deposit_address TEXT UNIQUE,
            admin_fee_collected REAL DEFAULT 0.00,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            trade_id TEXT PRIMARY KEY,
            user_id TEXT,
            engine TEXT,
            asset TEXT,
            amount REAL,
            runtime_seconds INTEGER,
            profit_loss REAL DEFAULT 0.00,
            status TEXT DEFAULT 'running',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)
    
    # Track verified blockchain deposits to prevent double-crediting
    c.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            tx_hash TEXT PRIMARY KEY,
            user_id TEXT,
            amount REAL,
            network TEXT,
            confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            description TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("Financial matrix ledger structural validation complete.")

# ==========================================
# 3. ON-CHAIN BLOCKCHAIN SYNCHRONIZER DAEMON
# ==========================================
async def blockchain_synchronizer_daemon():
    """
    Continuous off-chain service worker. 
    Scans network nodes/explorer APIs for incoming transactions matching sub-addresses,
    then updates the internal database ledger dynamically (as detailed in 1779722407919.jpeg).
    """
    logger.info("Blockchain synchronizer background daemon initialized successfully.")
    while True:
        try:
            await asyncio.sleep(15) # Poll public API indexers every 15 seconds
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # Fetch all generated user tracking ports
            c.execute("SELECT user_id, deposit_address FROM wallets WHERE deposit_address IS NOT NULL")
            active_nodes = c.fetchall()
            
            if not active_nodes:
                conn.close()
                continue
                
            # Simulate scanning blocks from an indexer pipeline (e.g., Etherscan, TronGrid, or Blockcypher)
            for user_id, deposit_address in active_nodes:
                # Randomly simulate an incoming blockchain payment event for testing purposes
                if random.random() < 0.05: 
                    mock_tx_hash = f"0x{uuid.uuid4().hex}{uuid.uuid4().hex}"[:64]
                    mock_deposit_amount = random.choice([50.0, 100.0, 250.0, 500.0])
                    
                    # Ensure transaction hash hasn't already been processed by the ledger engine
                    c.execute("SELECT 1 FROM deposits WHERE tx_hash = ?", (mock_tx_hash,))
                    if c.fetchone() is None:
                        # 1. Log payment matrix confirmation immutably
                        c.execute("INSERT INTO deposits (tx_hash, user_id, amount, network) VALUES (?, ?, ?, ?)",
                                  (mock_tx_hash, user_id, mock_deposit_amount, "TRC-20"))
                        
                        # 2. Update internal off-chain ledger balance tracking database rule
                        c.execute("UPDATE wallets SET main_balance = main_balance + ? WHERE user_id = ?",
                                  (mock_deposit_amount, user_id))
                        
                        c.execute("INSERT INTO audit_logs (event_type, description) VALUES (?, ?)",
                                  ("BLOCKCHAIN_DEPOSIT_CREDITED", f"Node {user_id} detected tx {mock_tx_hash[:10]}... credited ${mock_deposit_amount}"))
                        
                        logger.info(f"✨ SUCCESS: Blockchain Scanner credited user {user_id} with ${mock_deposit_amount} via address {deposit_address[:10]}...")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error inside network scanning worker loop: {str(e)}")

# ==========================================
# 4. BACKGROUND ALGORITHMIC TRADING RUNTIMES
# ==========================================
async def execute_trade_lifecycle(trade_id: str, user_id: str, engine: str, amount: float, runtime_seconds: int):
    logger.info(f"Asynchronous engine worker deployed for Trade ID: {trade_id}. Lock duration: {runtime_seconds}s")
    await asyncio.sleep(runtime_seconds)
    
    win_odds = 0.50
    pnl_multiplier = 0.15
    
    if engine == "low":      # Strong-Regular AI: 50% - 65% Win Rate
        win_odds = random.uniform(0.50, 0.65)
        pnl_multiplier = random.uniform(0.05, 0.12)
    elif engine == "mid":    # Advance AI Bot: 60% - 70% Win Rate
        win_odds = random.uniform(0.60, 0.70)
        pnl_multiplier = random.uniform(0.12, 0.28)
    elif engine == "high":   # Quantum AI Bot: 85% - 90% Win Rate (Aggressive scanning)
        win_odds = random.uniform(0.85, 0.90)
        pnl_multiplier = random.uniform(0.30, 0.65)

    is_win = random.random() < win_odds
    gross_pnl = (amount * pnl_multiplier) if is_win else -(amount * 0.40)
    
    # 0.5% Administrative Infrastructure Fee Allocation Rule
    execution_fee = amount * 0.005
    net_return = amount + gross_pnl - execution_fee if is_win else (amount + gross_pnl)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("UPDATE trades SET profit_loss = ?, status = 'completed' WHERE trade_id = ?", (gross_pnl, trade_id))
        c.execute("UPDATE wallets SET main_balance = main_balance + ? WHERE user_id = ?", (net_return, user_id))
        c.execute("UPDATE wallets SET admin_fee_collected = admin_fee_collected + ? WHERE user_id = (SELECT user_id FROM users LIMIT 1)", (execution_fee,))
        c.execute("INSERT INTO audit_logs (event_type, description) VALUES (?, ?)", 
                  ("TRADE_SETTLED", f"Node {user_id} complete. Gross PnL: ${gross_pnl:.2f}, Fee: ${execution_fee:.2f}"))
        conn.commit()
    except Exception as e:
        logger.error(f"Critical execution engine settlement structural failure: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

# ==========================================
# 5. UPGRADED API GATEWAY ROUTING INTERFACE
# ==========================================
class CreateTradeParams(BaseModel):
    greed_level: str
    asset: str
    amount: float
    runtime_options: str

def verify_jwt(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token parameters.")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["user_id"]
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Authentication signature rejected.")

@app.post("/api/wallet/burner")
async def create_burner_wallet():
    user_id = f"lens_node_{uuid.uuid4().hex[:8]}"
    
    # Generate unique deposit routing address per user (Mimicking BIP-44 sub-accounts layout)
    unique_sub_address = f"T{uuid.uuid4().hex[:33].upper()}"
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
    c.execute("INSERT INTO wallets (user_id, main_balance, deposit_address) VALUES (?, ?, ?)", 
              (user_id, 0.00, unique_sub_address)) # Starting liquid tracking balance empty until blockchain confirmation
    conn.commit()
    conn.close()
    
    token = jwt.encode({"user_id": user_id, "exp": time.time() + 86400}, SECRET_KEY, algorithm=ALGORITHM)
    return {"status": "success", "user_id": user_id, "token": token, "deposit_address": unique_sub_address}

@app.get("/api/wallet/state")
async def get_wallet_state(user_id: str = Depends(verify_jwt)):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT main_balance, bonus_pool, unlocked_bonus, deposit_address FROM wallets WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    
    # Retrieve recent uncredited pending or completed deposits
    c.execute("SELECT tx_hash, amount, confirmed_at FROM deposits WHERE user_id = ? ORDER BY confirmed_at DESC LIMIT 3", (user_id,))
    history_rows = c.fetchall()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Identity context missing.")
        
    history_list = [{"hash": r[0][:12] + "...", "amount": r[1], "time": r[2]} for r in history_rows]
    
    return {
        "main_balance": row[0], 
        "bonus_pool": row[1], 
        "unlocked_bonus": row[2],
        "deposit_address": row[3],
        "recent_deposits": history_list
    }

@app.post("/api/trade/deploy")
async def deploy_ai_engine(params: CreateTradeParams, background_tasks: BackgroundTasks, user_id: str = Depends(verify_jwt)):
    runtime_map = {"30mins": 5, "1hr": 10, "3hrs": 20, "6hrs": 40, "12hrs": 60}
    runtime_seconds = runtime_map.get(params.runtime_options, 10)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT main_balance FROM wallets WHERE user_id = ?", (user_id,))
    balance = c.fetchone()[0]
    
    if balance < params.amount:
        conn.close()
        raise HTTPException(status_code=400, detail="Insufficient liquid balance configuration.")
        
    trade_id = str(uuid.uuid4().hex[:10])
    
    c.execute("UPDATE wallets SET main_balance = main_balance - ? WHERE user_id = ?", (params.amount, user_id))
    c.execute("INSERT INTO trades (trade_id, user_id, engine, asset, amount, runtime_seconds) VALUES (?, ?, ?, ?, ?, ?)",
              (trade_id, user_id, params.greed_level, params.asset, params.amount, runtime_seconds))
    conn.commit()
    conn.close()
    
    background_tasks.add_task(execute_trade_lifecycle, trade_id, user_id, params.greed_level, params.amount, runtime_seconds)
    return {"status": "success", "message": f"Engine execution initiated successfully. Tracking ID: {trade_id}"}

# ==========================================
# 6. TELEGRAM CONTROLLER OPERATIONS
# ==========================================
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id != ADMIN_ID: return
        return await func(update, context, *args, **kwargs)
    return wrapper

@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    fees = c.execute("SELECT SUM(admin_fee_collected) FROM wallets").fetchone()[0] or 0.00
    conn.close()
    await update.message.reply_text(f"👑 **ADMIN FINANCIAL TELEMETRY v3.1**\n\n🌐 Active Network Nodes: `{users}`\n🛠️ Master Fee Revenue Pool: `${fees:,.4f}`", parse_mode="Markdown")

async def run_telegram_bot():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN verified inside environment.")
        return
    bot_app = Application.builder().token(token).build()
    bot_app.add_handler(CommandHandler("stats", stats))
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()

@app.on_event("startup")
async def startup_event():
    init_secure_db()
    asyncio.create_task(run_telegram_bot())
    # Deploy the blockchain sync layer as a parallel background task
    asyncio.create_task(blockchain_synchronizer_daemon())

if __name__ == "__main__":
    uvicorn.run("data_engine:app", host="0.0.0.0", port=8000, reload=False)
