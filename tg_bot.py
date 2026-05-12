import os
import redis
import requests
import subprocess
import asyncio
import json
import hashlib

from urllib.parse import urlparse
from datetime import datetime

from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI

from playwright.async_api import async_playwright

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

load_dotenv("/opt/hermes/.env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

os.makedirs("/opt/hermes/logs", exist_ok=True)
os.makedirs("/opt/hermes/workspace/screenshots", exist_ok=True)
os.makedirs("/opt/hermes/browser-data/default", exist_ok=True)

logger.add("/opt/hermes/logs/tg.log", rotation="100 MB")

r = redis.Redis(
    host="127.0.0.1",
    port=6379,
    decode_responses=True
)

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

SYSTEM_PROMPT = """
you are hermes-core

rules:
- concise
- technical
- no fluff
- no emojis
- prioritize execution
- give direct answers
"""

playwright_instance = None
browser_context = None
browser_page = None
browser_lock = asyncio.Lock()

browser_pool = {}

async def reset_agent_browser(agent_name):
    global browser_pool

    item = browser_pool.get(agent_name)

    if item:
        try:
            await item["context"].close()
        except Exception:
            pass

        try:
            del browser_pool[agent_name]
        except Exception:
            pass

    profile_dir = f"/opt/hermes/browser-data/{agent_name}"

    for lock_name in [
        "SingletonLock",
        "SingletonSocket",
        "SingletonCookie"
    ]:
        lock_path = os.path.join(profile_dir, lock_name)
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception:
            pass

    logger.warning(f"agent browser reset: {agent_name}")

async def get_agent_page(agent_name):
    global playwright_instance
    global browser_pool

    if playwright_instance is None:
        playwright_instance = await async_playwright().start()

    if agent_name in browser_pool:
        return browser_pool[agent_name]["page"]

    profile_dir = f"/opt/hermes/browser-data/{agent_name}"
    os.makedirs(profile_dir, exist_ok=True)

    context = await playwright_instance.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        executable_path="/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome",
        headless=False,
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox"
        ]
    )

    if context.pages:
        page = context.pages[0]
    else:
        page = await context.new_page()

    browser_pool[agent_name] = {
        "context": context,
        "page": page
    }

    return page


async def init_browser():
    global playwright_instance
    global browser_context
    global browser_page

    if browser_context:
        return

    playwright_instance = await async_playwright().start()

    browser_context = await playwright_instance.chromium.launch_persistent_context(
        user_data_dir="/opt/hermes/browser-data/default",
        executable_path="/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome",
        headless=False,
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox"
        ]
    )

    pages = browser_context.pages

    if pages:
        browser_page = pages[0]
    else:
        browser_page = await browser_context.new_page()

async def browser_open(target):
    global browser_page

    await init_browser()

    try:
        if not target.startswith("http"):
            if "." not in target:
                target = f"https://www.{target}.com"
            else:
                target = f"https://{target}"

        await browser_page.goto(
            target,
            timeout=60000,
            wait_until="domcontentloaded"
        )

        await browser_page.wait_for_timeout(3000)

        title = await browser_page.title()
        current_url = browser_page.url

        try:
            body_text = await browser_page.locator("body").inner_text(timeout=5000)
        except Exception:
            body_text = ""

        if len(body_text) > 1200:
            body_text = body_text[:1200]

        return f"""browser opened

title: {title}
url: {current_url}

preview:
{body_text}
"""

    except Exception as e:
        logger.exception("browser error")
        return f"browser error: {str(e)}"

async def browser_screenshot(target):
    global browser_page

    await init_browser()

    try:
        if not target.startswith("http"):
            if "." not in target:
                target = f"https://www.{target}.com"
            else:
                target = f"https://{target}"

        await browser_page.goto(
            target,
            timeout=60000,
            wait_until="domcontentloaded"
        )

        await browser_page.wait_for_timeout(5000)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        path = f"/opt/hermes/workspace/screenshots/{timestamp}.png"

        await browser_page.screenshot(
            path=path,
            full_page=True
        )

        title = await browser_page.title()
        current_url = browser_page.url

        return path, title, current_url

    except Exception as e:
        logger.exception("screenshot error")
        return None, None, f"screenshot error: {str(e)}"

async def ask_llm(user_id, text):
    history_key = f"memory:{user_id}"

    history = r.lrange(history_key, 0, 10)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    for item in reversed(history):
        role, content = item.split("|||", 1)

        messages.append({
            "role": role,
            "content": content
        })

    messages.append({
        "role": "user",
        "content": text
    })

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.3
    )

    answer = response.choices[0].message.content

    r.lpush(history_key, f"user|||{text}")
    r.lpush(history_key, f"assistant|||{answer}")

    r.ltrim(history_key, 0, 20)

    return answer

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = subprocess.getoutput(
        "systemctl status hermes hermes-bot --no-pager"
    )

    await update.message.reply_text(result[:4000])

async def memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = subprocess.getoutput("free -h")

    await update.message.reply_text(result)

async def disk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = subprocess.getoutput("df -h")

    await update.message.reply_text(result[:4000])

async def docker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = subprocess.getoutput("docker ps")

    await update.message.reply_text(result[:4000])

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = subprocess.getoutput(
        "tail -100 /opt/hermes/logs/tg.log"
    )

    await update.message.reply_text(result[:4000])

async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("restarting bot")

    subprocess.Popen(
        "systemctl restart hermes-bot",
        shell=True
    )

async def restart_runtime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("restarting runtime")

    subprocess.Popen(
        "systemctl restart hermes",
        shell=True
    )

async def open_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("usage: /open target")
        return

    target = " ".join(context.args)

    await update.message.reply_text(f"opening: {target}")

    result = await browser_open(target)

    await update.message.reply_text(result[:4000])

async def screenshot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("usage: /screenshot target")
        return

    target = " ".join(context.args)

    await update.message.reply_text(f"screenshot: {target}")

    path, title, current_url = await browser_screenshot(target)

    if not path:
        await update.message.reply_text(current_url)
        return

    with open(path, "rb") as img:
        await update.message.reply_photo(
            photo=img,
            caption=f"title: {title}\nurl: {current_url}"
        )

async def click_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("usage: /click text")
        return

    target = " ".join(context.args)

    await init_browser()

    try:
        await browser_page.get_by_text(target, exact=False).click(timeout=10000)
        await update.message.reply_text(f"clicked: {target}")
    except Exception as e:
        await update.message.reply_text(f"click error: {str(e)}")


async def type_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("usage: /type selector text")
        return

    selector = context.args[0]
    text = " ".join(context.args[1:])

    await init_browser()

    try:
        await browser_page.locator(selector).fill(text, timeout=10000)
        await update.message.reply_text(f"typed into: {selector}")
    except Exception as e:
        await update.message.reply_text(f"type error: {str(e)}")


async def press_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("usage: /press Enter")
        return

    key = " ".join(context.args)

    await init_browser()

    try:
        await browser_page.keyboard.press(key)
        await update.message.reply_text(f"pressed: {key}")
    except Exception as e:
        await update.message.reply_text(f"press error: {str(e)}")

async def typeactive_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("usage: /typeactive text")
        return

    text = " ".join(context.args)

    await init_browser()

    try:
        await browser_page.keyboard.type(text, delay=30)
        await update.message.reply_text(f"typed active: {text}")
    except Exception as e:
        await update.message.reply_text(f"typeactive error: {str(e)}")

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("usage: /search keyword")
        return

    keyword = " ".join(context.args)
    url = "https://x.com/search?q=" + keyword.replace(" ", "%20") + "&src=typed_query"

    await update.message.reply_text(f"searching x: {keyword}")

    result = await browser_open(url)

    await update.message.reply_text(result[:4000])

async def read_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await init_browser()

    try:
        title = await browser_page.title()
        url = browser_page.url

        try:
            text = await browser_page.locator("body").inner_text(timeout=8000)
        except Exception:
            text = ""

        if len(text) > 3500:
            text = text[:3500]

        await update.message.reply_text(
            f"title: {title}\nurl: {url}\n\n{text}"
        )

    except Exception as e:
        await update.message.reply_text(f"read error: {str(e)}")

async def askpage_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args).strip()

    if not question:
        await update.message.reply_text("usage: /askpage question")
        return

    await init_browser()

    try:
        title = await browser_page.title()
        url = browser_page.url

        try:
            body = await browser_page.locator("body").inner_text(timeout=8000)
        except Exception:
            body = ""

        if len(body) > 12000:
            body = body[:12000]

        prompt = f"""
current page:

title:
{title}

url:
{url}

content:
{body}

user request:
{question}
"""

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "you analyze browser pages and extract useful information"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )

        answer = response.choices[0].message.content

        if len(answer) > 4000:
            answer = answer[:4000]

        await update.message.reply_text(answer)

    except Exception as e:
        await update.message.reply_text(f"askpage error: {str(e)}")

async def scroll_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await init_browser()

    amount = 900
    if context.args:
        try:
            amount = int(context.args[0])
        except Exception:
            amount = 900

    try:
        await browser_page.mouse.wheel(0, amount)
        await browser_page.wait_for_timeout(1500)
        await update.message.reply_text(f"scrolled: {amount}")
    except Exception as e:
        await update.message.reply_text(f"scroll error: {str(e)}")


async def extractlinks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await init_browser()

    try:
        links = await browser_page.locator("a").evaluate_all("""
            els => els.slice(0, 30).map((a, i) => ({
                i,
                text: (a.innerText || a.textContent || '').trim().slice(0, 80),
                href: a.href
            }))
        """)

        lines = []
        for item in links:
            text = item.get("text") or "(no text)"
            href = item.get("href") or ""
            lines.append(f'{item["i"]}. {text}\n{href}')

        out = "\n\n".join(lines)
        if len(out) > 3800:
            out = out[:3800]

        await update.message.reply_text(out or "no links found")

    except Exception as e:
        await update.message.reply_text(f"extractlinks error: {str(e)}")


async def clickindex_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await init_browser()

    if not context.args:
        await update.message.reply_text("usage: /clickindex 0")
        return

    try:
        index = int(context.args[0])
    except Exception:
        await update.message.reply_text("index must be number")
        return

    try:
        links = browser_page.locator("a")
        count = await links.count()

        if index < 0 or index >= count:
            await update.message.reply_text(f"index out of range. total links: {count}")
            return

        await links.nth(index).click(timeout=10000)
        await browser_page.wait_for_timeout(3000)

        title = await browser_page.title()
        url = browser_page.url

        await update.message.reply_text(f"clicked index: {index}\n\ntitle: {title}\nurl: {url}")

    except Exception as e:
        await update.message.reply_text(f"clickindex error: {str(e)}")

autonomous_tasks = {}

AGENT_PROFILES = {
    "btc": {
        "keyword": "bitcoin",
        "role": "BTC market sentiment and macro narrative analyst",
        "focus": "bitcoin price sentiment, whale movement, macro narratives, ETF/institutional activity, bull/bear traps"
    },
    "eth": {
        "keyword": "ethereum",
        "role": "ETH ecosystem and DeFi sentiment analyst",
        "focus": "ETH price sentiment, staking, L2, DeFi, Ethereum upgrades, institutional flows"
    },
    "sol": {
        "keyword": "solana",
        "role": "Solana ecosystem intelligence analyst",
        "focus": "SOL price sentiment, meme coins, ecosystem launches, outages, scam tokens, volume spikes"
    },
    "scam": {
        "keyword": "crypto wallet drainer OR rug pull OR fake airdrop OR phishing crypto",
        "role": "crypto scam and phishing detection analyst",
        "focus": "wallet drainers, fake airdrops, phishing domains, rug pulls, fake token launches, suspicious KOL promotions, wallet connection scams"
    },
    "breaking": {
        "keyword": "crypto breaking news",
        "role": "breaking crypto news analyst",
        "focus": "urgent news, exchange issues, hacks, regulation, ETF, liquidation cascades, major announcements"
    }
}



SIGNAL_MEMORY_PREFIX = "signal_memory:"

def signal_hash(text):
    raw = (text or "").strip().lower()
    raw = " ".join(raw.split())
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def filter_new_signals(keyword, text):
    key = SIGNAL_MEMORY_PREFIX + keyword.lower().strip()

    blocks = []
    current = []

    for line in text.splitlines():
        if line.strip():
            current.append(line)
        else:
            if current:
                blocks.append("\n".join(current))
                current = []

    if current:
        blocks.append("\n".join(current))

    new_blocks = []

    for block in blocks:
        if len(block) < 40:
            continue

        h = signal_hash(block)

        if not r.sismember(key, h):
            r.sadd(key, h)
            new_blocks.append(block)

    r.expire(key, 60 * 60 * 24 * 7)

    return "\n\n---\n\n".join(new_blocks[:20])

TASKS_FILE = "/opt/hermes/tg-bot/autonomous_tasks.json"

def save_autonomous_tasks():
    data = []

    for key in autonomous_tasks.keys():
        try:
            chat_id, keyword = key.split(":", 1)

            data.append({
                "chat_id": int(chat_id),
                "keyword": keyword
            })

        except Exception:
            pass

    try:
        with open(TASKS_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"save task error: {e}")


async def restore_autonomous_tasks():
    global autonomous_tasks

    try:
        with open(TASKS_FILE, "r") as f:
            data = json.load(f)

    except Exception:
        data = []

    for item in data:
        try:
            chat_id = item["chat_id"]
            keyword = item["keyword"]

            key = f"{chat_id}:{keyword}"

            if key in autonomous_tasks:
                continue

            if keyword.startswith("agent:"):
                name = keyword.split(":", 1)[1]
                task = asyncio.create_task(
                    agent_loop(chat_id, name)
                )
                key = f"{chat_id}:agent:{name}"
            else:
                task = asyncio.create_task(
                    autonomous_loop(chat_id, keyword)
                )
                key = f"{chat_id}:{keyword}"

            autonomous_tasks[key] = task

            logger.info(f"restored autonomous: {key}")

        except Exception as e:
            logger.error(f"restore task error: {e}")


async def autonomous_loop(chat_id, keyword):
    while True:
        try:
            url = "https://x.com/search?q=" + keyword.replace(" ", "%20") + "&src=typed_query"

            await browser_open(url)

            await browser_page.wait_for_timeout(3000)

            await browser_page.mouse.wheel(0, 1200)

            await browser_page.wait_for_timeout(2000)

            body = await browser_page.locator("body").inner_text(timeout=8000)

            body = filter_new_signals(keyword, body)

            if not body:
                await asyncio.sleep(300)
                continue

            if len(body) > 12000:
                body = body[:12000]

            prompt = f"""
analyze this x search page.

focus:
- market sentiment
- bullish views
- bearish views
- important accounts
- scams
- unusual activity

content:
{body}
"""

            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": "you are a crypto intelligence analyst"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2
            )

            answer = response.choices[0].message.content

            if len(answer) > 4000:
                answer = answer[:4000]

            await app.bot.send_message(
                chat_id=chat_id,
                text=f"[autonomous: {keyword}]\n\n{answer}"
            )

        except Exception as e:
            await app.bot.send_message(
                chat_id=chat_id,
                text=f"autonomous error: {str(e)}"
            )

        await asyncio.sleep(300)


async def autonomous_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global autonomous_tasks

    if not context.args:
        await update.message.reply_text("usage: /autonomous keyword")
        return

    keyword = " ".join(context.args)

    chat_id = update.effective_chat.id

    key = f"{chat_id}:{keyword}"

    if key in autonomous_tasks:
        await update.message.reply_text("already running")
        return

    task = asyncio.create_task(
        autonomous_loop(chat_id, keyword)
    )

    autonomous_tasks[key] = task
    save_autonomous_tasks()

    await update.message.reply_text(
        f"autonomous started: {keyword}"
    )


async def stopauto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global autonomous_tasks

    if not context.args:
        await update.message.reply_text("usage: /stopauto keyword")
        return

    keyword = " ".join(context.args)

    chat_id = update.effective_chat.id

    key = f"{chat_id}:{keyword}"

    task = autonomous_tasks.get(key)

    if not task:
        await update.message.reply_text("not running")
        return

    task.cancel()

    del autonomous_tasks[key]
    save_autonomous_tasks()

    await update.message.reply_text(
        f"autonomous stopped: {keyword}"
    )

async def autolist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global autonomous_tasks

    if not autonomous_tasks:
        await update.message.reply_text("no autonomous tasks running")
        return

    lines = []

    for key in autonomous_tasks.keys():
        lines.append(key)

    out = "\n".join(lines)

    await update.message.reply_text(
        f"running autonomous tasks:\n\n{out}"
    )

async def intel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("usage: /intel keyword")
        return

    keyword = " ".join(context.args)

    await update.message.reply_text(f"intel scan started: {keyword}")

    try:
        url = "https://x.com/search?q=" + keyword.replace(" ", "%20") + "&src=typed_query"

        await browser_open(url)
        await browser_page.wait_for_timeout(3000)

        for _ in range(3):
            await browser_page.mouse.wheel(0, 1200)
            await browser_page.wait_for_timeout(1500)

        body = await browser_page.locator("body").inner_text(timeout=10000)

        if len(body) > 16000:
            body = body[:16000]

        prompt = f"""
you are a crypto intelligence analyst.

analyze the following X search page and produce a high-signal intelligence brief.

keyword:
{keyword}

scoring dimensions:
- breaking news
- whale movement
- smart money
- major KOL influence
- scam / phishing
- extreme bullish sentiment
- extreme bearish sentiment
- unusual engagement
- actionable risk

output format:
1. executive conclusion
2. top 5 high-signal items
3. bullish signals
4. bearish signals
5. scam / manipulation risks
6. accounts worth monitoring
7. final intelligence score from 0-100

content:
{body}
"""

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "you are a senior crypto intelligence analyst. be concise and high-signal."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )

        answer = response.choices[0].message.content

        if len(answer) > 4000:
            answer = answer[:4000]

        await update.message.reply_text(answer)

    except Exception as e:
        await update.message.reply_text(f"intel error: {str(e)}")

async def clear_signal_memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("usage: /clear_signal_memory keyword")
        return

    keyword = " ".join(context.args).lower().strip()
    key = SIGNAL_MEMORY_PREFIX + keyword

    try:
        r.delete(key)
        await update.message.reply_text(f"signal memory cleared: {keyword}")
    except Exception as e:
        await update.message.reply_text(f"clear signal memory error: {str(e)}")

async def agent_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        names = ", ".join(AGENT_PROFILES.keys())
        await update.message.reply_text(f"usage: /agent name\navailable: {names}")
        return

    name = context.args[0].lower().strip()

    if name not in AGENT_PROFILES:
        names = ", ".join(AGENT_PROFILES.keys())
        await update.message.reply_text(f"unknown agent: {name}\navailable: {names}")
        return

    profile = AGENT_PROFILES[name]
    keyword = profile["keyword"]

    chat_id = update.effective_chat.id
    key = f"{chat_id}:agent:{name}"

    if key in autonomous_tasks:
        await update.message.reply_text(f"agent already running: {name}")
        return

    task = asyncio.create_task(
        agent_loop(chat_id, name)
    )

    autonomous_tasks[key] = task
    save_autonomous_tasks()

    await update.message.reply_text(
        f"agent started: {name}\nkeyword: {keyword}\nrole: {profile['role']}"
    )


async def agent_loop(chat_id, name):
    profile = AGENT_PROFILES[name]
    keyword = profile["keyword"]

    while True:
        try:
            url = "https://x.com/search?q=" + keyword.replace(" ", "%20") + "&src=typed_query"

            async with browser_lock:
                await init_browser()

                await browser_page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await browser_page.wait_for_timeout(3000)

                for _ in range(3):
                    await browser_page.mouse.wheel(0, 1200)
                    await browser_page.wait_for_timeout(1500)

                body = await browser_page.locator("body").inner_text(timeout=10000)

            body = filter_new_signals(f"agent:{name}", body)

            if not body:
                await asyncio.sleep(300)
                continue

            if len(body) > 16000:
                body = body[:16000]

            prompt = f"""
you are {profile['role']}.

focus:
{profile['focus']}

analyze this X search page.

output format:
1. executive conclusion
2. top high-signal items
3. key accounts
4. bullish / positive signals
5. bearish / risk signals
6. scam / manipulation / abnormal activity
7. final score 0-100
8. what to monitor next

content:
{body}
"""

            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": "you are a senior crypto intelligence analyst. be concise, factual, and high-signal."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2
            )

            answer = response.choices[0].message.content

            if len(answer) > 4000:
                answer = answer[:4000]

            await app.bot.send_message(
                chat_id=chat_id,
                text=f"[agent:{name}]\n\n{answer}"
            )

        except Exception as e:
            await app.bot.send_message(
                chat_id=chat_id,
                text=f"agent error {name}: {str(e)}\n\nself-healing: resetting browser context"
            )

            try:
                await reset_agent_browser(f"agent_{name}")
            except Exception as reset_error:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=f"self-healing reset error {name}: {str(reset_error)}"
                )

        await asyncio.sleep(300)


async def stopagent_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("usage: /stopagent name")
        return

    name = context.args[0].lower().strip()
    chat_id = update.effective_chat.id
    key = f"{chat_id}:agent:{name}"

    task = autonomous_tasks.get(key)

    if not task:
        await update.message.reply_text(f"agent not running: {name}")
        return

    task.cancel()
    del autonomous_tasks[key]
    save_autonomous_tasks()

    await update.message.reply_text(f"agent stopped: {name}")


async def agents_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = []

    for name, profile in AGENT_PROFILES.items():
        lines.append(f"{name}: {profile['keyword']} | {profile['role']}")

    await update.message.reply_text("available agents:\n\n" + "\n".join(lines))

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    user_id = update.effective_user.id

    logger.info(f"{user_id}: incoming message: {text}")

    answer = await ask_llm(user_id, text)

    await update.message.reply_text(answer[:4000])

def main():
    global app
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("memory", memory))
    app.add_handler(CommandHandler("disk", disk))
    app.add_handler(CommandHandler("docker", docker))
    app.add_handler(CommandHandler("logs", logs))

    app.add_handler(CommandHandler("restartbot", restart_bot))
    app.add_handler(CommandHandler("restartruntime", restart_runtime))

    app.add_handler(CommandHandler("open", open_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("read", read_cmd))

    app.add_handler(CommandHandler("scroll", scroll_cmd))
    app.add_handler(CommandHandler("extractlinks", extractlinks_cmd))
    app.add_handler(CommandHandler("clickindex", clickindex_cmd))
    app.add_handler(CommandHandler("askpage", askpage_cmd))
    app.add_handler(CommandHandler("intel", intel_cmd))

    app.add_handler(CommandHandler("autonomous", autonomous_cmd))
    app.add_handler(CommandHandler("stopauto", stopauto_cmd))
    app.add_handler(CommandHandler("autolist", autolist_cmd))

    app.add_handler(CommandHandler("agent", agent_cmd))
    app.add_handler(CommandHandler("stopagent", stopagent_cmd))
    app.add_handler(CommandHandler("agents", agents_cmd))
    app.add_handler(CommandHandler("clear_signal_memory", clear_signal_memory_cmd))
    app.add_handler(CommandHandler("screenshot", screenshot_cmd))

    app.add_handler(CommandHandler("click", click_cmd))
    app.add_handler(CommandHandler("type", type_cmd))
    app.add_handler(CommandHandler("press", press_cmd))
    app.add_handler(CommandHandler("typeactive", typeactive_cmd))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            chat
        )
    )

    asyncio.get_event_loop().create_task(restore_autonomous_tasks())

    logger.info("hermes telegram bot started")

    app.run_polling()

if __name__ == "__main__":
    main()
