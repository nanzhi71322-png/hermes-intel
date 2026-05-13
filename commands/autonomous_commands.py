import asyncio

from telegram import Update
from telegram.ext import ContextTypes


autonomous_tasks = None
autonomous_loop = None
save_autonomous_tasks = None


def configure(tasks, loop_func, save_func):
    global autonomous_tasks
    global autonomous_loop
    global save_autonomous_tasks

    autonomous_tasks = tasks
    autonomous_loop = loop_func
    save_autonomous_tasks = save_func


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
