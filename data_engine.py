import os
import logging
import httpx
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# --- NEW: TELEGRAM BOT IMPORTS ---
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# ==========================================
# 1. CONFIGURATION & LOGGING
# ==========================================
logging.basicConfig(format='%(asctime)s - [LENs-DEX-ROUTER] - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ⚠️ TELEGRAM BOT & WEBAPP CONFIGURATION
TELEGRAM_TOKEN = "8959355486:AAExJ0nE_-HRrQDG-YzoYws54LYfqWU4_ss"
WEBAPP_URL = "https://comforting-buttercream-660b69.netlify.app"

app = FastAPI(title="LENs Web3 API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# YOUR ADMIN FEE WALLET ON SOLANA
ADMIN_FEE_ACCOUNT = "Your_Solana_Wallet_Address_Here" 

# ==========================================
# 2. TELEGRAM BOT ENGINE
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the user a button to launch your WebApp inside Telegram."""
    keyboard = [
        [InlineKeyboardButton("Launch LENs Engine 🚀", web_app=WebAppInfo(url=WEBAPP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Welcome to the LENs Premium Trading Core. Click below to initialize the Web3 terminal:",
        reply_markup=reply_markup
    )

# Initialize the Bot Application
bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
bot_app.add_handler(CommandHandler("start", start_command))

# Run Telegram Bot alongside the FastAPI Server
@app.on_event("startup")
async def startup_event():
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    logger.info("🟢 Telegram Bot Engine & Web3 Gateway Successfully Started!")

@app.on_event("shutdown")
async def shutdown_event():
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()

# ==========================================
# 3. SOLANA TOKEN MINT DIRECTORY
# ==========================================
TOKENS = {
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "SOL": "So11111111111111111111111111111111111111112",
    "WBTC": "3NZ9JMVBmO8E6Z5wZ2aCj6O1o5x3Z2aCj6O1o5x3Z2aCj6O1o5x3Z2aC", 
    "WETH": "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs", 
    "WBNB": "9gP2kCy3wA1ctvYWQkZHh5pD2qAEM4L9x8yZ9uN5RzH"   
}

# ==========================================
# 4. JUPITER DEX ROUTING LOGIC
# ==========================================
class SwapRequest(BaseModel):
    user_public_key: str
    target_asset: str
    amount_usdc: float

@app.post("/api/build_swap")
async def build_dex_swap(request: SwapRequest):
    """
    Fetches the best DEX route from Jupiter and builds the transaction.
    Injects a 50 BPS (0.5%) platform maintenance fee.
    """
    if request.target_asset not in TOKENS:
        raise HTTPException(status_code=400, detail="Invalid target asset.")

    amount_in_lamports = int(request.amount_usdc * 1_000_000)
    input_mint = TOKENS["USDC"]
    output_mint = TOKENS[request.target_asset]

    async with httpx.AsyncClient() as client:
        quote_url = f"https://quote-api.jup.ag/v6/quote?inputMint={input_mint}&outputMint={output_mint}&amount={amount_in_lamports}&platformFeeBps=50"
        
        try:
            quote_response = await client.get(quote_url)
            quote_response.raise_for_status()
            quote_data = quote_response.json()
        except httpx.HTTPError as e:
            logger.error(f"Jupiter API Error: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch DEX route from liquidity pools.")

        swap_payload = {
            "quoteResponse": quote_data,
            "userPublicKey": request.user_public_key,
            "wrapAndUnwrapSol": True,
            "feeAccount": ADMIN_FEE_ACCOUNT 
        }
        
        try:
            swap_response = await client.post("https://quote-api.jup.ag/v6/swap", json=swap_payload)
            swap_response.raise_for_status()
            swap_data = swap_response.json()
        except httpx.HTTPError as e:
            logger.error(f"Jupiter Transaction Build Error: {e}")
            raise HTTPException(status_code=500, detail="Failed to construct blockchain transaction.")
        
        return {"swapTransaction": swap_data["swapTransaction"]}

if __name__ == "__main__":
    uvicorn.run("data_engine:app", host="0.0.0.0", port=8000, reload=False)
