import os
import time
import asyncio
import logging
import requests

from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]

logging.basicConfig(level=logging.INFO)

TEHRAN = ZoneInfo("Asia/Tehran")


def get_tgju_price(url):
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        element = soup.select_one(
            '[data-col="info.last_trade.PDrCotVal"]'
        )

        if element:
            return element.get_text(strip=True)

    except Exception:
        logging.exception("TGJU price error")

    return None


def get_btc_price():
    try:
        response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
            timeout=15,
        )
        response.raise_for_status()

        return response.json()["bitcoin"]["usd"]

    except Exception:
        logging.exception("Bitcoin price error")

    return None


def get_prices():
    return {
        "usd": get_tgju_price(
            "https://www.tgju.org/profile/price_dollar_rl"
        ),
        "gold": get_tgju_price(
            "https://www.tgju.org/profile/geram18"
        ),
        "btc": get_btc_price(),
    }


def format_report(prices):
    usd = prices.get("usd") or "دریافت نشد"
    gold = prices.get("gold") or "دریافت نشد"
    btc = prices.get("btc")

    btc_text = (
        f"${btc:,.2f}"
        if isinstance(btc, (int, float))
        else "دریافت نشد"
    )

    now = datetime.now(TEHRAN).strftime("%H:%M")

    return (
        "📊🔥 نبض بازار | موبایل ۲۰\n"
        "━━━━━━━━━━━━━━\n"
        f"💵 دلار آزاد: {usd}\n"
        f"🥇 طلای ۱۸ عیار: {gold}\n"
        f"₿ بیت‌کوین: {btc_text}\n"
        "━━━━━━━━━━━━━━\n"
        f"🕒 آخرین بررسی: {now}\n"
        "📡 منابع: TGJU و CoinGecko\n"
        "━━━━━━━━━━━━━━\n"
        "📱 همراه بازار با موبایل ۲۰"
    )


def number_value(value):
    if value is None:
        return None

    digits = str(value).translate(
        str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
            "01234567890123456789",
        )
    )

    try:
        return float(
            digits.replace(",", "").replace("٬", "")
        )
    except ValueError:
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 به ربات بازار موبایل ۲۰ خوش آمدی!\n\n"
        "/usd - قیمت دلار\n"
        "/gold - قیمت طلای ۱۸ عیار\n"
        "/btc - قیمت بیت‌کوین\n"
        "/all - گزارش کامل بازار"
    )


async def show_prices(update, context, key=None):
    prices = await asyncio.to_thread(get_prices)

    if key:
        names = {
            "usd": "💵 دلار آزاد",
            "gold": "🥇 طلای ۱۸ عیار",
            "btc": "₿ بیت‌کوین",
        }

        value = prices.get(key)

        if value is None:
            await update.message.reply_text(
                "قیمت فعلاً دریافت نشد؛ بعداً دوباره امتحان کن."
            )
            return

        if key == "btc":
            value = f"${value:,.2f}"

        await update.message.reply_text(
            f"{names[key]}: {value}"
        )
        return

    await update.message.reply_text(format_report(prices))


async def usd_command(update, context):
    await show_prices(update, context, "usd")


async def gold_command(update, context):
    await show_prices(update, context, "gold")


async def btc_command(update, context):
    await show_prices(update, context, "btc")


async def all_command(update, context):
    await show_prices(update, context)


async def publish_report(context):
    prices = await asyncio.to_thread(get_prices)

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=format_report(prices),
    )


async def check_prices(context):
    data = context.application.bot_data
    prices = await asyncio.to_thread(get_prices)

    now = time.monotonic()
    previous = data.get("last_prices", {})
    changed = False

    for key, current in prices.items():
        old = previous.get(key)

        current_num = number_value(current)
        old_num = number_value(old)

        if (
            current_num is not None
            and old_num is not None
            and old_num != 0
        ):
            difference = abs(current_num - old_num) / abs(old_num)

            if difference >= 0.005:
                changed = True

        if current is not None:
            previous[key] = current

    data["last_prices"] = previous

    last_report = data.get("last_report", 0)

    # Publish after a significant price change,
    # or at least every 30 minutes.
    if changed or now - last_report >= 1800:
       
