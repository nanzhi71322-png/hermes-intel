from telegram.ext import CommandHandler, MessageHandler, filters

from commands import agent_commands, autonomous_commands, browser_commands, system_commands, trading_commands


def register_handlers(
    app,
    autonomous_tasks,
    autonomous_loop,
    agent_loop,
    save_autonomous_tasks,
    agent_profiles,
):
    autonomous_commands.configure(
        autonomous_tasks,
        autonomous_loop,
        save_autonomous_tasks,
    )
    agent_commands.configure(
        autonomous_tasks,
        agent_loop,
        save_autonomous_tasks,
        agent_profiles,
    )

    app.add_handler(CommandHandler("status", system_commands.status))
    app.add_handler(CommandHandler("memory", system_commands.memory))
    app.add_handler(CommandHandler("disk", system_commands.disk))
    app.add_handler(CommandHandler("docker", system_commands.docker))
    app.add_handler(CommandHandler("logs", system_commands.logs))

    app.add_handler(CommandHandler("restartbot", system_commands.restart_bot))
    app.add_handler(CommandHandler("restartruntime", system_commands.restart_runtime))

    app.add_handler(CommandHandler("open", browser_commands.open_cmd))
    app.add_handler(CommandHandler("search", browser_commands.search_cmd))
    app.add_handler(CommandHandler("read", browser_commands.read_cmd))

    app.add_handler(CommandHandler("scroll", browser_commands.scroll_cmd))
    app.add_handler(CommandHandler("extractlinks", browser_commands.extractlinks_cmd))
    app.add_handler(CommandHandler("clickindex", browser_commands.clickindex_cmd))
    app.add_handler(CommandHandler("askpage", browser_commands.askpage_cmd))
    app.add_handler(CommandHandler("intel", browser_commands.intel_cmd))

    app.add_handler(CommandHandler("autonomous", autonomous_commands.autonomous_cmd))
    app.add_handler(CommandHandler("stopauto", autonomous_commands.stopauto_cmd))
    app.add_handler(CommandHandler("autolist", autonomous_commands.autolist_cmd))

    app.add_handler(CommandHandler("agent", agent_commands.agent_cmd))
    app.add_handler(CommandHandler("stopagent", agent_commands.stopagent_cmd))
    app.add_handler(CommandHandler("agents", agent_commands.agents_cmd))
    app.add_handler(CommandHandler("clear_signal_memory", agent_commands.clear_signal_memory_cmd))
    app.add_handler(CommandHandler("screenshot", browser_commands.screenshot_cmd))

    app.add_handler(CommandHandler("click", browser_commands.click_cmd))
    app.add_handler(CommandHandler("type", browser_commands.type_cmd))
    app.add_handler(CommandHandler("press", browser_commands.press_cmd))
    app.add_handler(CommandHandler("typeactive", browser_commands.typeactive_cmd))

    app.add_handler(CommandHandler("tradereport", trading_commands.tradereport))
    app.add_handler(CommandHandler("tradestatus", trading_commands.tradestatus))
    app.add_handler(CommandHandler("tradetest", trading_commands.tradetest))
    app.add_handler(CommandHandler("tradepause", trading_commands.tradepause))
    app.add_handler(CommandHandler("traderesume", trading_commands.traderesume))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            system_commands.chat
        )
    )
