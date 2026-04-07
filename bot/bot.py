import asyncio
import json
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Your instruments
INSTRUMENTS = {
    "GOLD (XAUUSD)": "GC=F",
    "BTCUSD": "BTC-USD",
    "US30": "^DJI",
    "US100": "^NDX",
    "US500": "^GSPC",
    "DE40": "^GDAXI",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X",
    "XAGUSD (Silver)": "SI=F",
}

user_lang = {}
alerts_data = {}
pending_alert = {}   # {user_id: symbol} for adding alert

DATA_FILE = "alerts.json"

def load_alerts():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_alerts():
    with open(DATA_FILE, "w") as f:
        json.dump(alerts_data, f, indent=2)

alerts_data = load_alerts()

def get_text(user_id, key):
    lang = user_lang.get(str(user_id), "en")
    texts = {
        "en": {
            "welcome": "🚨 Price Alert Bot\nChoose action:",
            "add_alert": "➕ Add Alert",
            "my_alerts": "📋 My Alerts",
            "current_price": "💰 Current Price",
            "select_instrument": "Select instrument:",
            "enter_price": "Send target price (example: 5200.50):",
            "alert_added": "✅ Alert set for {symbol} at {price}",
            "alert_triggered": "🚨 {symbol} reached {price}!\nCurrent price: {current}",
            "no_alerts": "You have no active alerts yet.",
        },
        "ru": {
            "welcome": "🚨 Бот алертов по цене\nВыберите действие:",
            "add_alert": "➕ Добавить алерт",
            "my_alerts": "📋 Мои алерты",
            "current_price": "💰 Текущая цена",
            "select_instrument": "Выберите инструмент:",
            "enter_price": "Отправьте целевую цену (например 5200.50):",
            "alert_added": "✅ Алерт установлен для {symbol} на {price}",
            "alert_triggered": "🚨 {symbol} достиг {price}!\nТекущая цена: {current}",
            "no_alerts": "У вас пока нет активных алертов.",
        }
    }
    return texts[lang].get(key, key)

def main_keyboard(user_id):
    lang = user_lang.get(str(user_id), "en")
    btns = [
        [types.KeyboardButton(text=get_text(user_id, "add_alert"))],
        [types.KeyboardButton(text=get_text(user_id, "my_alerts"))],
        [types.KeyboardButton(text=get_text(user_id, "current_price"))],
        [types.KeyboardButton(text="🌐 Change Language / Сменить язык")],
    ]
    return types.ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def instrument_keyboard(prefix: str):
    kb = []
    for name in INSTRUMENTS.keys():
        kb.append([InlineKeyboardButton(text=name, callback_data=f"{prefix}:{name}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

import yfinance as yf
def get_current_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d", interval="1m")
        if not data.empty:
            return round(data['Close'].iloc[-1], 4)
    except:
        pass
    return None

# Background checker (every 50 seconds)
async def price_checker():
    while True:
        for user_id_str, user_alerts in list(alerts_data.items()):
            for alert in user_alerts[:]:
                if alert.get("triggered"):
                    continue
                symbol = alert["symbol"]
                target = alert["price"]
                ticker = INSTRUMENTS.get(symbol)
                if not ticker:
                    continue
                current = get_current_price(ticker)
                if current is None:
                    continue

                if (target >= current and current >= target) or (target <= current and current <= target):
                    alert["triggered"] = True
                    save_alerts()
                    msg = get_text(user_id_str, "alert_triggered").format(
                        symbol=symbol, price=target, current=current
                    )
                    try:
                        await bot.send_message(int(user_id_str), msg)
                    except:
                        pass
        await asyncio.sleep(50)

@dp.message(Command("start"))
async def start(message: types.Message):
    uid = str(message.from_user.id)
    if uid not in user_lang:
        user_lang[uid] = "en"
    await message.answer(get_text(uid, "welcome"), reply_markup=main_keyboard(uid))

@dp.message(F.text.in_(["➕ Add Alert", "➕ Добавить алерт"]))
async def add_alert_start(message: types.Message):
    await message.answer(get_text(message.from_user.id, "select_instrument"), reply_markup=instrument_keyboard("add"))

@dp.message(F.text.in_(["💰 Current Price", "💰 Текущая цена"]))
async def current_price_start(message: types.Message):
    await message.answer(get_text(message.from_user.id, "select_instrument"), reply_markup=instrument_keyboard("price"))

@dp.message(F.text.in_(["📋 My Alerts", "📋 Мои алерты"]))
async def my_alerts(message: types.Message):
    uid = str(message.from_user.id)
    alerts = alerts_data.get(uid, [])
    if not alerts:
        await message.answer(get_text(uid, "no_alerts"))
        return
    text = "Your active alerts:\n\n"
    for a in alerts:
        status = "✅ Triggered" if a.get("triggered") else "⏳ Waiting"
        text += f"• {a['symbol']} @ {a['price']} — {status}\n"
    await message.answer(text)

@dp.callback_query(F.data.startswith("add:"))
async def handle_add_instrument(callback: types.CallbackQuery):
    symbol = callback.data.split(":", 1)[1]
    pending_alert[str(callback.from_user.id)] = symbol
    await callback.message.edit_text(f"Selected: **{symbol}**\n\n{get_text(callback.from_user.id, 'enter_price')}")

@dp.callback_query(F.data.startswith("price:"))
async def handle_price_instrument(callback: types.CallbackQuery):
    symbol = callback.data.split(":", 1)[1]
    ticker = INSTRUMENTS[symbol]
    current = get_current_price(ticker)
    price_text = f"**{current}**" if current else "Could not get price right now"
    await callback.message.edit_text(f"Current price of **{symbol}**: {price_text}")

@dp.message()
async def handle_price_input(message: types.Message):
    uid = str(message.from_user.id)
    if uid not in pending_alert:
        return

    try:
        target_price = float(message.text.replace(",", "."))
        symbol = pending_alert.pop(uid)

        if uid not in alerts_data:
            alerts_data[uid] = []
        alerts_data[uid].append({"symbol": symbol, "price": target_price, "triggered": False})
        save_alerts()

        await message.answer(get_text(uid, "alert_added").format(symbol=symbol, price=target_price))
    except ValueError:
        await message.answer("Please send a valid number (example: 5200.50)")

async def main():
    asyncio.create_task(price_checker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
