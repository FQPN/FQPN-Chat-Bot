import asyncio
import logging
import time

from core import auth, botauth, dashboard, desktop, donations, notify, publiclist, updater, usage, watchdog
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
    state["watchdog"] = watchdog.Watchdog(state, store, lambda: dashboard.restart_bot(state))   # reconnects the bot by itself if it silently stops hearing Twitch
    state["watchdog_task"] = asyncio.create_task(state["watchdog"].run())
    state["publist_syncer"] = publiclist.Syncer(store, state)    # the public command list website (off until switched on)
    state["publist_task"] = asyncio.create_task(state["publist_syncer"].run())
    state["banned"] = bool((store.get("usage_state") or {}).get("banned"))     # the last answer, until the website says otherwise
    state["usage_task"] = asyncio.create_task(usage.Reporter(state, store=store, on_change=lambda: dashboard.restart_bot(state)).run())     # channel name + app version, once a day (Settings > App explains it)
    last_error_notice = 0.0

    async def on_donation(d):   # a donation from Streamlabs / StreamElements: the running bot thanks the donor in chat
        bot = state.get("bot")
        if bot is not None and bot.connected:
            await bot.on_donation(d)

    state["donations"] = donations.DonationManager(on_donation)
    await state["donations"].start()        # reconnects to the services that have a saved token

    # The dashboard starts first so it's available even if Twitch is down.
    try:
        await dashboard.start(store, state)
    except OSError as e:
        print(f"Could not start the dashboard: {e}. The bot will still run.")

    state["login"] = {"status": "idle"}
    state["bot_login"] = {"status": "idle"}      # the login of the separate bot account
    state["wake"] = asyncio.Event()
    auto_login = True    # first start: begin "Connect Twitch" automatically, like before

    # Waits for a Twitch account (the dashboard's Connect button can start the login),
    # then runs the bot. Automatic reconnection: if the bot ever stops or crashes, start it again.
    while True:
        state["wake"].clear()
        state["lost"] = False
        state["restart"] = False
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
        state["account_id"] = account["user_id"]
        if state.get("banned"):
            # the developer turned the app off for this channel: no bot, the dashboard explains it; an unban wakes this up
            state["bot"] = None
            print("FQPN's Chat Bot has been turned off for this channel by its developer.")
            await state["wake"].wait()
            continue

        # "Use a separate bot account" (Settings > Bot): another Twitch account writes the replies in your chat.
        bot_account = await botauth.get_account()          # None when no bot account is connected
        state["bot_account"] = bot_account["login"] if bot_account else None
        separate = bool(store.get("settings").get("separate_bot"))
        if separate and bot_account is None:
            # The option is on but there is no bot account yet: stay silent (never talk as your own account by surprise)
            # and wait until the Connect button finishes or the option is switched off.
            state["bot"] = None
            print("The separate bot account is switched on but not connected. Waiting for it to be connected...")
            await state["wake"].wait()
            continue
        if separate and state.get("bot_mod") is None:
            state["mod_task"] = asyncio.create_task(dashboard.refresh_bot_mod(state))
        bot = TwitchBot(account, store, bot_account=bot_account if separate else None)
        state["bot"] = bot
        try:
            await bot.start(
                token=(bot_account if separate else account)["access_token"],
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
        if state.get("restart"):          # a setting changed (separate bot account on/off, a new bot account): start again now
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
