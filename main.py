import os
import time
import requests
from datetime import datetime
import json
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode
from bs4 import BeautifulSoup

# Настройки
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 300))
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
DAILY_DIGEST_HOUR = int(os.getenv("DAILY_DIGEST_HOUR", 8))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

DATA_FILE = "data/sent_listings.json"
os.makedirs("data", exist_ok=True)

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump([], f)

EXCHANGES = {
    "MEXC": "https://www.mexc.com/support/articles/530000033958",
    "Gate.io": "https://www.gate.io/news",
    "BingX": "https://bingx.zendesk.com/hc/en-001/sections/18530471187725-New-Listing-Announcements",
    "Ourbit": "https://twitter.com/Ourbit_en"
}

def load_sent():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_sent(sent):
    with open(DATA_FILE, "w") as f:
        json.dump(sent, f, indent=2)

async def send_message(text):
    try:
        await bot.send_message(CHAT_ID, text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        logging.info("Сообщение отправлено")
    except Exception as e:
        logging.error(f"Ошибка отправки: {e}")

def parse_mexc():
    try:
        r = requests.get(EXCHANGES["MEXC"], timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        listings = []
        for a in soup.find_all('a', href=True):
            txt = a.get_text().lower()
            if 'listing' in txt and 'new' in txt:
                title = a.get_text().strip()
                coin = title.split('$')[1].split()[0] if '$' in title else title[:8]
                link = "https://www.mexc.com" + a['href']
                listings.append({
                    'exchange': 'MEXC',
                    'coin': coin,
                    'title': title,
                    'link': link,
                    'spot_time': '12:00 UTC',
                    'futures_time': '12:10 UTC',
                    'date': (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y")
                })
        return listings
    except:
        return []

def parse_gate():
    try:
        r = requests.get("https://www.gate.io/news", timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        listings = []
        for h4 in soup.find_all('h4'):
            txt = h4.get_text().lower()
            if 'listing' in txt and 'new' in txt:
                title = h4.get_text().strip()
                coin = title.split('$')[1].split()[0] if '$' in title else title[:8]
                link = "https://www.gate.io" + h4.find_parent('a')['href']
                listings.append({
                    'exchange': 'Gate.io',
                    'coin': coin,
                    'title': title,
                    'link': link,
                    'spot_time': '12:00 UTC',
                    'futures_time': None,
                    'date': (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y")
                })
        return listings
    except:
        return []

def parse_bingx():
    try:
        r = requests.get(EXCHANGES["BingX"], timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        listings = []
        for h3 in soup.find_all('h3'):
            txt = h3.get_text().lower()
            if 'listing' in txt:
                title = h3.get_text().strip()
                coin = title.split('$')[1].split()[0] if '$' in title else title[:8]
                link = h3.find_parent('a')['href'] if h3.find_parent('a') else '#'
                listings.append({
                    'exchange': 'BingX',
                    'coin': coin,
                    'title': title,
                    'link': link,
                    'spot_time': '12:00 UTC' if 'spot' in txt else None,
                    'futures_time': '12:10 UTC' if 'futures' in txt else None,
                    'date': (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y")
                })
        return listings
    except:
        return []

def parse_ourbit():
    return []  # Позже добавим Twitter

async def check_new_listings():
    all_listings = []
    all_listings.extend(parse_mexc())
    all_listings.extend(parse_gate())
    all_listings.extend(parse_bingx())
    all_listings.extend(parse_ourbit())

    sent = load_sent()
    new_alerts = []
    digest_data = []

    for item in all_listings:
        key = f"{item['exchange']}_{item['coin']}_{item['date']}"
        if key not in sent:
            sent.append(key)
            msg = f"""
🔔 *НОВЫЙ ЛИСТИНГ!*

📅 {item['date']}
🏦 {item['exchange']}
🪙 ${item['coin']}
{'🟢 Spot ' + item['spot_time'] if item['spot_time'] else ''}
{'🔵 Futures ' + item['futures_time'] if item['futures_time'] else ''}
🔗 [Анонс]({item['link']})
            """.strip()
            await send_message(msg)
            new_alerts.append(item)
        digest_data.append(item)

    save_sent(sent)
    return digest_data

async def send_daily_digest():
    sent = load_sent()
    today = datetime.utcnow().strftime("%d.%m.%Y")
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%d.%m.%Y")
    digest = [i for i in sent if i.split('_')[2] in [today, tomorrow]]

    if not digest:
        await send_message("📭 *На сегодня и завтра нет новых листингов*")
        return

    from collections import defaultdict
    grouped = defaultdict(list)
    for key in digest:
        ex, coin, date = key.split('_', 2)
        grouped[date].append({'exchange': ex, 'coin': coin})

    msg = "🌅 *ДАЙДЖЕСТ НА БЛИЖАЙШИЕ ДНИ*\n\n"
    for date in sorted(grouped.keys()):
        msg += f"📅 *{date}*\n"
        for item in grouped[date]:
            msg += f"🏦 {item['exchange']}\n🪙 ${item['coin']}\n\n"
    await send_message(msg)

async def main():
    logging.info("Бот запущен")
    last_digest_check = datetime.utcnow()
    while True:
        try:
            await check_new_listings()
            now = datetime.utcnow()
            if now.hour == DAILY_DIGEST_HOUR and now.day != last_digest_check.day:
                await send_daily_digest()
                last_digest_check = now
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            logging.error(f"Ошибка: {e}")
            time.sleep(60)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
