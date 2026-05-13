import subprocess

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import LOG_FILE
from memory.chat import ask_llm


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
        f"tail -100 {LOG_FILE}"
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


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    user_id = update.effective_user.id

    logger.info(f"{user_id}: incoming message: {text}")

    answer = await ask_llm(user_id, text)

    await update.message.reply_text(answer[:4000])
