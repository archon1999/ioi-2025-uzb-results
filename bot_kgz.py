import asyncio
import datetime
import json
import os
from collections import defaultdict
from pathlib import Path

import aiohttp
from aiogram import Bot
from aiogram.enums import ParseMode
from dotenv import load_dotenv
from aiogram.client.default import DefaultBotProperties

load_dotenv()

KGZ = {
    "KGZ1": "Alihan Aidarbekov",
    # "KGZ2": "Ulug'bek Rahmatullayev",
    "KGZ3": "Abdullahan Abdirasulov",
    "KGZ4": "Ali Arapov",
}

HISTORY = "https://ranking.ioi2025.bo/history"
SCORES = "https://ranking.ioi2025.bo/scores"
FILE = Path("sent_kgz.json")
POLL = 10


class Store:
    def __init__(self):
        self.sent = set()
        self.count = 0
        self.last_ts = 0
        self.best = defaultdict(dict)

    def load(self):
        if FILE.exists():
            self.sent = {tuple(x) for x in json.loads(FILE.read_text())}
            if self.sent:
                self.last_ts = max(x[2] for x in self.sent)

    async def init_first(self, session):
        if FILE.exists():
            return
        async with session.get(HISTORY) as r:
            data = await r.json(content_type=None)
        latest = sorted(data, key=lambda x: x[2], reverse=True)[:10]
        self.sent = {tuple(x) for x in latest}
        self.last_ts = max(x[2] for x in latest) if latest else 0
        FILE.write_text(json.dumps([list(x) for x in self.sent]))

    def remember(self, items):
        self.sent.update(items)
        FILE.write_text(json.dumps([list(x) for x in self.sent]))


async def summary(bot, chat, session):
    async with session.get(SCORES) as r:
        raw = await r.json(content_type=None)
    totals = {k: sum(v.values()) for k, v in raw.items()}
    ranked = sorted(totals.items(), key=lambda x: -x[1])
    n = len(ranked)
    gold = (n + 11) // 12
    silver = (n + 5) // 6 + gold
    bronze = (n + 3) // 4 + silver
    lines = []
    for i, (t, s) in enumerate(ranked, 1):
        if i <= gold:
            medal = "🥇 "
        elif i <= silver:
            medal = "🥈 "
        elif i <= bronze:
            medal = "🥉 "
        else:
            medal = ""

        if t.startswith("KGZ"):
            lines.append(f"<b>{i}</b>. <i>{KGZ[t]}</i> — <code>{s:.2f}</code> {medal}")

    duration = datetime.datetime.now() - (datetime.datetime.now().replace(hour=19, minute=0, second=0, microsecond=0))
    msg = f"<b>🏅 Scoreboard</b> ({str(duration)[:7]})\n\n"
    msg += "\n".join(lines)
    await bot.send_message(chat, msg)


async def runner():
    bot = Bot(
        token=os.environ["BOT_TOKEN"],
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    chat = "-1002815493497"
    store = Store()
    store.load()
    async with aiohttp.ClientSession() as session:
        # await store.init_first(session)
        while True:
            try:
                async with session.get(HISTORY) as r:
                    data = await r.json(content_type=None)

                async with session.get(SCORES) as r:
                    raw = await r.json(content_type=None)

                fresh = [d for d in data if tuple(d) not in store.sent and d[2] > store.last_ts and d[0] in KGZ]
                fresh.sort(key=lambda x: x[2])
                fresh = fresh[:10]
                for team, task, ts, pts in fresh:
                    if team not in KGZ:
                        continue

                    totals = {k: sum(v.values()) for k, v in raw.items()}
                    ranked = sorted(totals.items(), key=lambda x: -x[1])
                    total = sum(store.best[team].values())
                    for i, (t, s) in enumerate(ranked, 1):
                        if t == team:
                            total = s

                    prev = store.best[team].get(task, 0)
                    if pts > prev:
                        store.best[team][task] = pts

                    t = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).time()
                    msg = f"[{t.hour - 14}:{t.minute:02}:{t.second:02}]: {KGZ[team]} submitted {task} for {pts:.2f} points\nTotal: {total:.2f}"
                    await bot.send_message(chat, msg)
                    store.count += 1
                if fresh:
                    store.remember(tuple(d) for d in fresh)
                    store.last_ts = max(store.last_ts, max(x[2] for x in fresh))
                if store.count >= 10:
                    await summary(bot, chat, session)
                    store.count = 0
            except Exception as e:
                print("Error:", e)
            await asyncio.sleep(POLL)


if __name__ == "__main__":
    asyncio.run(runner())
