import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from config.clients import redis_client as r
from memory.signals import SIGNAL_MEMORY_PREFIX


autonomous_tasks = None
agent_loop = None
save_autonomous_tasks = None
AGENT_PROFILES = None


def configure(tasks, loop_func, save_func, profiles):
    global autonomous_tasks
    global agent_loop
    global save_autonomous_tasks
    global AGENT_PROFILES

    autonomous_tasks = tasks
    agent_loop = loop_func
    save_autonomous_tasks = save_func
    AGENT_PROFILES = profiles


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
