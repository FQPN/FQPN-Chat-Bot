import asyncio
import logging
import webbrowser

from core import auth, dashboard
from core.bot import TwitchBot
from core.store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("twitchbot")


async def main(open_browser=True):
    store = Store()
    state = {"bot": None, "account": None}   # shared with the dashboard

    # The dashboard starts first so it's available even if Twitch is down.
    try:
        await dashboard.start(store, state)
        if open_browser:   # the installed app shows its own window instead
            webbrowser.open(f"http://localhost:{dashboard.PORT}")
    except OSError:
        print(f"Could not start the dashboard: port {dashboard.PORT} is already in use "
              "(is the bot already running?). The bot will still run.")

    state["login"] = {"status": "idle"}
    state["wake"] = asyncio.Event()
    auto_login = True    # first start: begin "Connect Twitch" automatically, like before

    # Waits for a Twitch account (the dashboard's Connect button can start the login),
    # then runs the bot. Automatic reconnection: if the bot ever stops or crashes, start it again.
    while True:
        state["wake"].clear()
        account = await auth.get_account()
        if account is None:
            state["account"] = None
            state["avatar"] = None
            state["bot"] = None
            if auth.last_problem == "permissions":
                print("This version needs new Twitch permissions (announcements, title and game). "
                      "Please connect again and click Authorize.")
            if auto_login:
                auto_login = False
                print("No Twitch account connected. Starting Connect Twitch...")
                dashboard.start_login(state)
            await state["wake"].wait()      # set when a login finishes
            continue

        auto_login = False
        print(f"Connected as {account['login']}")
        state["account"] = account["login"]
        state["avatar_task"] = asyncio.create_task(dashboard.load_avatar(state, account))   # profile picture for the dashboard
        bot = TwitchBot(account, store)
        state["bot"] = bot
        try:
            await bot.start(
                token=account["access_token"],
                with_adapter=False,   # no local web server needed for chat
                load_tokens=False,
                save_tokens=False,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Bot stopped unexpectedly")
        finally:
            await bot.close()
        if auth.load_token() is None:     # disconnected from the dashboard
            continue
        log.info("Restarting in 10 seconds...")
        await asyncio.sleep(10)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass