import os
import time
import uuid
import asyncio
import logging
import sqlite3
import jwt
import random
from datetime import datetime, timedelta
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
    format='%(asctime)s - [LENs-CORE-v3] - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ADMIN_ID = 6546954770
DB_FILE = "lens_secure_vault.db"
SECRET_KEY = "lens_institutional_secure_key_override"
ALGORITHM = "HS256"

app = FastAPI(title="LENs Advanced Unified Gateway Platform", version="3.0")

# Enable Cross-Origin Resource Sharing (CORS) for decoupled mobile frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 2. MULTI-TENANT & TRADE ENGINE LEDGER SCHEMA
# ==========================================
def init_secure_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    c = conn.cursor()
    
    # Core User Identity
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Core Isolated Ledger Wallets with platform administration fee pool slots
    c.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            user_id TEXT PRIMARY KEY,
            main_balance REAL DEFAULT 0.00,
            bonus_pool REAL DEFAULT 45.00,
            unlocked_bonus REAL DEFAULT 5.00,
            admin_fee_collected REAL DEFAULT 0.00,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)
    
    # Active & Historic Automated Trade Executions Log
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
    
    # Immutable Security Audit Tracking Layout
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
    logger.info("Database matrix structural validation complete.")

# ==========================================
# 3. BACKGROUND ALGORITHMIC TRADING RUNTIMES
# ==========================================
async def execute_trade_lifecycle(trade_id: str, user_id: str, engine: str, amount: float, runtime_seconds: int):
    """
    Handles background execution, applies structural win-rate mechanics based on grid choice, 
    processes 0.5% optimization administration fees, and increments funds to client states.
    """
    logger.info(f"Asynchronous engine worker deployed for Trade ID: {trade_id}. Lock duration: {runtime_seconds}s")
    await asyncio.sleep(runtime_seconds)  # Simulate live pipeline execution
    
    # 1. Define Engine Success Parameters & Logic Constraints
    win_odds = 0.50
    pnl_multiplier = 0.15  # Default returns parameter space
    
    if engine == "low":      # Strong-Regular AI: 50% - 65% Win Rate
        win_odds = random.uniform(0.50, 0.65)
        pnl_multiplier = random.uniform(0.05, 0.12)
    elif engine == "mid":    # Advance AI Bot: 60% - 70% Win Rate
        win_odds = random.uniform(0.60, 0.70)
        pnl_multiplier = random.uniform(0.12, 0.28)
    elif engine == "high":   # Quantum AI Bot: 85% - 90% Win Rate (Aggressive Long/Short scanning)
        win_odds = random.uniform(0.85, 0.90)
        pnl_multiplier = random.uniform(0.30, 0.65)

    is_win = random.random() < win_odds
    gross_pnl = (amount * pnl_multiplier) if is_win else -(amount * 0.40) # Managed Risk Stop-Loss
    
    # 2. Strict Fee Matrix Routing Rule Engine (0.5% Admin Collection)
    execution_fee = amount * 0.005
    net_return = amount + gross_pnl - execution_fee if is_win else (amount + gross_pnl)

    # 3. Secure Atomic Settlement Transaction Block
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        # Update Trade status to complete
        c.execute("UPDATE trades SET profit_loss = ?, status = 'completed' WHERE trade_id = ?", (gross_pnl, trade_id))
        
        # Adjust tenant balance pools and dispatch 0.5% admin commission overhead
        c.execute("UPDATE wallets SET main_balance = main_balance + ? WHERE user_id = ?", (net_return, user_id))
        c.execute("UPDATE wallets SET admin_fee_collected = admin_fee_collected + ? WHERE user_id = 'mock_user_1'", (execution_fee,))
        
        c.execute("INSERT INTO audit_logs (event_type, description) VALUES (?, ?)", 
                  ("TRADE_SETTLED", f"Node {user_id} complete. Gross PnL: ${gross_pnl:.2f}, Fee: ${execution_fee:.2f}"))
        conn.commit()
    except Exception as e:
        logger.error(f"Critical execution engine settlement structural failure: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

# ==========================================
# 4. API ROUTING GATEWAY ENDPOINTS
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
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
    c.execute("INSERT INTO wallets (user_id, main_balance) VALUES (?, ?)", (user_id, 500.00)) # Default $500 simulation assets for testing
    conn.commit()
    conn.close()
    
    token = jwt.encode({"user_id": user_id, "exp": time.time() + 86400}, SECRET_KEY, algorithm=ALGORITHM)
    return {"status": "success", "user_id": user_id, "token": token}

@app.get("/api/wallet/state")
async def get_wallet_state(user_id: str = Depends(verify_jwt)):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT main_balance, bonus_pool, unlocked_bonus FROM wallets WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Identity context missing.")
    return {"main_balance": row[0], "bonus_pool": row[1], "unlocked_bonus": row[2]}

@app.post("/api/trade/deploy")
async def deploy_ai_engine(params: CreateTradeParams, background_tasks: BackgroundTasks, user_id: str = Depends(verify_jwt)):
    # Runtime parsing mapping matrix
    runtime_map = {"30mins": 5, "1hr": 10, "3hrs": 20, "6hrs": 40, "12hrs": 60} # Accelerated time frame parameters for system responsiveness
    runtime_seconds = runtime_map.get(params.runtime_options, 10)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT main_balance FROM wallets WHERE user_id = ?", (user_id,))
    balance = c.fetchone()[0]
    
    if balance < params.amount:
        conn.close()
        raise HTTPException(status_code=400, detail="Insufficient liquid deployment capital inside user node.")
        
    trade_id = str(uuid.uuid4().hex[:10])
    
    # Deduct structural trade pool size from client live system
    c.execute("UPDATE wallets SET main_balance = main_balance - ? WHERE user_id = ?", (params.amount, user_id))
    c.execute("INSERT INTO trades (trade_id, user_id, engine, asset, amount, runtime_seconds) VALUES (?, ?, ?, ?, ?, ?)",
              (trade_id, user_id, params.greed_level, params.asset, params.amount, runtime_seconds))
    conn.commit()
    conn.close()
    
    # Offload execution pipeline calculation metrics to decoupled worker threads
    background_tasks.add_task(execute_trade_lifecycle, trade_id, user_id, params.greed_level, params.amount, runtime_seconds)
    return {"status": "success", "message": f"Engine initialization successful. ID: {trade_id}"}

# ==========================================
# 5. TELEGRAM CONTROLLER OPERATIONS
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
    await update.message.reply_text(f"👑 **ADMIN SYSTEM TELEMETRY v3**\n\n🌐 Active Network Nodes: `{users}`\n🛠️ Accumulating Administration Revenue Pool: `${fees:,.4f}`", parse_mode="Markdown")

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

if __name__ == "__main__":
    uvicorn.run("data_engine:app", host="0.0.0.0", port=8000, reload=False)
