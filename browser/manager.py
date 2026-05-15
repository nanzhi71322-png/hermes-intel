import asyncio
import os

from datetime import datetime

from loguru import logger
from playwright.async_api import async_playwright

from config.settings import (
    BROWSER_DATA_DIR,
    CHROMIUM_EXECUTABLE,
    DEFAULT_BROWSER_DATA_DIR,
    SCREENSHOT_DIR,
)
from utils.urls import normalize_browser_target


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

    profile_dir = f"{BROWSER_DATA_DIR}/{agent_name}"

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

    profile_dir = f"{BROWSER_DATA_DIR}/{agent_name}"
    os.makedirs(profile_dir, exist_ok=True)

    context = await playwright_instance.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        executable_path=CHROMIUM_EXECUTABLE,
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
        user_data_dir=DEFAULT_BROWSER_DATA_DIR,
        executable_path=CHROMIUM_EXECUTABLE,
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
        target = normalize_browser_target(target)

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

        return {
            "title": title,
            "url": current_url,
            "preview": body_text,
        }

    except Exception as e:
        logger.exception("browser error")
        return {
            "title": "",
            "url": "",
            "preview": f"browser error: {str(e)}",
        }


async def browser_screenshot(target):
    global browser_page

    await init_browser()

    try:
        target = normalize_browser_target(target)

        await browser_page.goto(
            target,
            timeout=60000,
            wait_until="domcontentloaded"
        )

        await browser_page.wait_for_timeout(5000)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        path = f"{SCREENSHOT_DIR}/{timestamp}.png"

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
