import asyncio
import logging
import time

from core import auth, dashboard, desktop, notify, updater
from core.bot import TwitchBot
from core.store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("twitchbot")


async def main(open_browser=False):    # open_browser is ignored: the dashboard is only shown in the app window
    store = Store()
    store.apply_launch_defaults()   # "Start the bot when the app opens" (Settings > Bot)
    state = {"bot": None, "account": None}   # shared with the dashboard
    state["update_wake"] = asyncio.Event()
    try:   # the Windows start-up entry follows the settings (this also repairs it after an update)
        desktop.apply_prefs(store.get("prefs"))
    except Exception:
        log.exception("Could not update the Windows start-up entry")
    updater.cleanup()
    state["update_loop"] = asyncio.create_task(updater.loop(updater.U, store, state["update_wake"]))
    last_error_notice = 0.0

    # The dashboard starts first so it's available even if Twitch is down.
    try:
        await dashboard.start(store, state)
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
        state["lost"] = False
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
            if time.time() - last_error_notice > 600:    # at most one pop-up per 10 minutes
                last_error_notice = time.time()
                notify.error(store.get("prefs"), "The bot stopped unexpectedly. Details are in bot.log.")
        finally:
            await bot.close()
        if auth.load_token() is None:     # disconnected from the dashboard
            continue
        prefs = store.get("prefs")
        if not prefs.get("auto_reconnect", True):
            # "Reconnect to Twitch automatically" is off: wait until the dashboard's Reconnect button is pressed
            state["bot"] = None
            state["lost"] = True
            notify.error(prefs, "Lost the connection to Twitch. Open the dashboard and press Reconnect.")
            log.info("Connection lost; waiting for Reconnect")
            await state["wake"].wait()
            continue
        log.info("Restarting in 10 seconds...")
        await asyncio.sleep(10)


if __name__ == "__main__":
    print("The bot is starting without an app window. To open the app, run:  python launcher.py")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
