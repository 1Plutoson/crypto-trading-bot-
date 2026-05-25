import os
import time
import uuid
import asyncio
import logging
import sqlite3
import jwt
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel
import uvicorn
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ==========================================
# 1. SYSTEM CONFIGURATION & LOGGING
# ==========================================
logging.basicConfig(
    format='%(asctime)s - [LENs-CORE] - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Security Constants
ADMIN_ID = 6546954770
DB_FILE = "lens_secure_vault.db"
SECRET_KEY = "lens_institutional_secure_key_override" # Use .env for production
ALGORITHM = "HS256"

# Initialize FastAPI App
app = FastAPI(title="LENs Core Unified Gateway", version="3.0")

# ==========================================
# 2. MULTI-TENANT DATABASE SCHEMA
# ==========================================
def init_secure_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    c = conn.cursor()
    
    # Isolated User Identity
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Strict Wallet State
    c.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            wallet_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            main_balance REAL DEFAULT 0.00,
            bonus_pool REAL DEFAULT 45.00,
            unlocked_bonus REAL DEFAULT 0.00,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)
    
    # Immutable Security Ledger
    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            description TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Initial Baseline Data Check
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO audit_logs (event_type, description) VALUES (?, ?)", 
                  ("SYSTEM_INIT", "Unified multi-tenant database initialized and secured."))
    
    conn.commit()
    conn.close()
    logger.info("Database schema verified and secured.")

# ==========================================
# 3. FASTAPI GATEWAY (WEBAPP BACKEND)
# ==========================================
class TradeRequest(BaseModel):
    greed_level: str
    asset: str

class DepositRequest(BaseModel):
    amount: float
    asset: str

def verify_jwt(authorization: str = Header(None)):
    """Middleware to enforce strict tenant isolation via JWT."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")
    
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["user_id"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Cryptographic signature invalid.")

@app.post("/api/wallet/burner")
async def create_burner_wallet():
    """Creates an isolated user account and issues a secure JWT."""
    user_id = f"lens_node_{uuid.uuid4().hex[:8]}"
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        c.execute("INSERT INTO wallets (user_id) VALUES (?)", (user_id,))
        c.execute("INSERT INTO audit_logs (event_type, description) VALUES (?, ?)", 
                  ("NEW_NODE", f"Burner wallet generated for ID: {user_id}"))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Ledger allocation failed.")
    finally:
        conn.close()

    # Issue 24-hour token
    payload = {"user_id": user_id, "exp": time.time() + 86400}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    return {"status": "success", "user_id": user_id, "token": token}

@app.post("/api/trade/auto")
async def process_auto_trade(request: TradeRequest, user_id: str = Depends(verify_jwt)):
    """Routes the AI trading engine request."""
    engines = {"low": "Strong-Regular AI", "mid": "Advance AI", "high": "Quantum AI"}
    
    selected = engines.get(request.greed_level)
    if not selected:
        raise HTTPException(status_code=400, detail="Invalid Greed Engine.")
    
    # Log trade request securely
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT INTO audit_logs (event_type, description) VALUES (?, ?)", 
                 ("TRADE_INIT", f"User {user_id} deployed {selected} on {request.asset}"))
    conn.commit()
    conn.close()

    return {"status": "active", "message": f"{selected} successfully deployed on {request.asset}."}

@app.post("/api/wallet/deposit")
async def process_deposit(request: DepositRequest, user_id: str = Depends(verify_jwt)):
    """Handles the 5% bonus unlock logic securely."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Fetch current wallet state safely
    c.execute("SELECT main_balance, bonus_pool, unlocked_bonus FROM wallets WHERE user_id = ?", (user_id,))
    wallet = c.fetchone()
    if not wallet:
        conn.close()
        raise HTTPException(status_code=404, detail="Wallet state not found.")
        
    main_bal, bonus_pool, unlocked_bonus = wallet
    
    # 2. Process logic
    new_main = main_bal + request.amount
    msg = f"Deposit of ${request.amount} confirmed."
    
    if request.amount >= 20.00 and bonus_pool > 0:
        unlock_amount = bonus_pool * 0.05
        bonus_pool -= unlock_amount
        unlocked_bonus += unlock_amount
        msg += f" 5% Bonus (${unlock_amount:.2f}) Unlocked!"
        
    # 3. Commit isolated changes
    c.execute("""
        UPDATE wallets SET main_balance = ?, bonus_pool = ?, unlocked_bonus = ? WHERE user_id = ?
    """, (new_main, bonus_pool, unlocked_bonus, user_id))
    
    c.execute("INSERT INTO audit_logs (event_type, description) VALUES (?, ?)", 
              ("DEPOSIT", f"User {user_id} deposited {request.amount} {request.asset}"))
    
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": msg}

# ==========================================
# 4. TELEGRAM ADMIN CONTROLLER
# ==========================================
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id != ADMIN_ID:
            logger.warning(f"UNAUTHORIZED ACCESS ATTEMPT BY ID: {update.effective_user.id}")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🛡️ **LENs SECURE COMMAND CENTER** 🛡️\n\n"
        "API Gateway and Admin Nodes Online.\n"
        "📊 `/stats` - View Telemetry\n"
        "🔐 `/audit` - View Ledger\n"
        "🧹 `/reconcile` - Optimize Database"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_liquidity = c.execute("SELECT SUM(main_balance) FROM wallets").fetchone()[0] or 0.00
    conn.close()
    
    msg = f"👥 **NODE TELEMETRY**\n🌐 Users: `{total_users}`\n💰 Total Liquidity: `${total_liquidity:,.2f}`"
    await update.message.reply_text(msg, parse_mode="Markdown")

@admin_only
async def audit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    logs = conn.execute("SELECT event_type, description, timestamp FROM audit_logs ORDER BY timestamp DESC LIMIT 5").fetchall()
    conn.close()
    
    if not logs:
        await update.message.reply_text("No recent logs.")
        return

    msg = "🔐 **SECURITY LOGS**\n\n"
    for log in logs:
        msg += f"[{log[2]}] **{log[0]}**\n`{log[1]}`\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

@admin_only
async def reconcile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧹 *Reconciling Database States...*", parse_mode="Markdown")
    conn = sqlite3.connect(DB_FILE)
    conn.execute("VACUUM") 
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ **RECONCILIATION COMPLETE.**")

# ==========================================
# 5. ASYNC EXECUTION MANAGER
# ==========================================
async def run_telegram_bot():
    """Runs the Telegram bot continuously alongside the FastAPI server."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("CRITICAL: TELEGRAM_BOT_TOKEN not set. Bot will not start.")
        return
        
    bot_app = Application.builder().token(token).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("stats", stats))
    bot_app.add_handler(CommandHandler("audit", audit))
    bot_app.add_handler(CommandHandler("reconcile", reconcile))
    
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    logger.info("Telegram Admin Bot is actively polling.")

@app.on_event("startup")
async def startup_event():
    """Triggered automatically when FastAPI (Uvicorn) starts."""
    init_secure_db()
    # Schedule the Telegram bot to run in the background event loop
    asyncio.create_task(run_telegram_bot())

if __name__ == "__main__":
    # Start the unified engine on local port 8000
    uvicorn.run("data_engine:app", host="0.0.0.0", port=8000, reload=False)
