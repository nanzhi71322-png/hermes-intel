from telegram import Update
from telegram.ext import ContextTypes

import browser.manager as browser_manager
from browser.manager import browser_open, browser_screenshot, init_browser
from config.clients import llm_client as client
from config.settings import DEEPSEEK_MODEL
from utils.urls import build_x_search_url


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
        await browser_manager.browser_page.get_by_text(target, exact=False).click(timeout=10000)
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
        await browser_manager.browser_page.locator(selector).fill(text, timeout=10000)
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
        await browser_manager.browser_page.keyboard.press(key)
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
        await browser_manager.browser_page.keyboard.type(text, delay=30)
        await update.message.reply_text(f"typed active: {text}")
    except Exception as e:
        await update.message.reply_text(f"typeactive error: {str(e)}")


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("usage: /search keyword")
        return

    keyword = " ".join(context.args)
    url = build_x_search_url(keyword)

    await update.message.reply_text(f"searching x: {keyword}")

    result = await browser_open(url)

    await update.message.reply_text(result[:4000])


async def read_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await init_browser()

    try:
        title = await browser_manager.browser_page.title()
        url = browser_manager.browser_page.url

        try:
            text = await browser_manager.browser_page.locator("body").inner_text(timeout=8000)
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
        title = await browser_manager.browser_page.title()
        url = browser_manager.browser_page.url

        try:
            body = await browser_manager.browser_page.locator("body").inner_text(timeout=8000)
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
            model=DEEPSEEK_MODEL,
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
        await browser_manager.browser_page.mouse.wheel(0, amount)
        await browser_manager.browser_page.wait_for_timeout(1500)
        await update.message.reply_text(f"scrolled: {amount}")
    except Exception as e:
        await update.message.reply_text(f"scroll error: {str(e)}")


async def extractlinks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await init_browser()

    try:
        links = await browser_manager.browser_page.locator("a").evaluate_all("""
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
        links = browser_manager.browser_page.locator("a")
        count = await links.count()

        if index < 0 or index >= count:
            await update.message.reply_text(f"index out of range. total links: {count}")
            return

        await links.nth(index).click(timeout=10000)
        await browser_manager.browser_page.wait_for_timeout(3000)

        title = await browser_manager.browser_page.title()
        url = browser_manager.browser_page.url

        await update.message.reply_text(f"clicked index: {index}\n\ntitle: {title}\nurl: {url}")

    except Exception as e:
        await update.message.reply_text(f"clickindex error: {str(e)}")


async def intel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("usage: /intel keyword")
        return

    keyword = " ".join(context.args)

    await update.message.reply_text(f"intel scan started: {keyword}")

    try:
        url = build_x_search_url(keyword)

        await browser_open(url)
        await browser_manager.browser_page.wait_for_timeout(3000)

        for _ in range(3):
            await browser_manager.browser_page.mouse.wheel(0, 1200)
            await browser_manager.browser_page.wait_for_timeout(1500)

        body = await browser_manager.browser_page.locator("body").inner_text(timeout=10000)

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
            model=DEEPSEEK_MODEL,
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
