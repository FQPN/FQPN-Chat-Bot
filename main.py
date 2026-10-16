import asyncio
import contextvars
import logging
import time

from core import accounts, auth, botauth, dashboard, desktop, donations, notify, publiclist, updater, usage, watchdog
from core.bot import TwitchBot
from core.store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("twitchbot")


async def _two_copies_watch(store, state, clock=time.time, every=20):
    """Two copies of the app (for example the installed one and one started from VS Code) share one Twitch login and burn
    each other's renewal key, which makes the bot go silent. Each copy writes "I'm alive" here; a fresh note from another
    copy means two are running: say so (once), in the log, a desktop pop-up and the dashboard."""
    import json, os
    from core import store as _store
    path = _store.DATA_DIR / "running.json"
    me, warned, sightings = os.getpid(), False, set()
    while True:
        try:
            other = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            if other.get("pid") not in (None, me) and clock() - float(other.get("at", 0)) < 3 * every:
                sightings.add(other.get("at"))     # a closed copy writes once at most; a running one keeps writing
            if len(sightings) >= 2 and not warned:
                warned = True
                state["two_copies"] = True
                log.warning("Another copy of the app is running (process %s): two copies break each other's Twitch login", other.get("pid"))
                notify.error(store.get("prefs"), "Two copies of FQPN's Chat Bot are running. Close one: together they break the Twitch login and the bot goes silent.")
            path.write_text(json.dumps({"pid": me, "at": clock()}), encoding="utf-8")
        except (OSError, ValueError):
            pass
        await asyncio.sleep(every)


APP_KEYS = {"two_copies", "update_loop", "update_wake", "update_task", "copies_task", "runtimes", "app"}


class Runtime:
    """One channel: its own data (store), its own state (bot, login, health, ...), its own loop. 1.12.0."""
    def __init__(self, cid, store):
        self.cid, self.store = cid, store
        self.state = {"bot": None, "account": None}
        self.task = None


class AppState(dict):
    """What the dashboard sees as `state`: the app-wide keys, plus the keys of the channel this request is for (the
    page names it; otherwise the channel the app shows). Nearly all of the dashboard keeps working unchanged."""
    def __init__(self, runtimes: dict):
        super().__init__()
        self.runtimes = runtimes

    def rt(self) -> Runtime:
        cid = accounts.current_channel()
        return self.runtimes.get(cid) or self.runtimes.get(accounts.ACTIVE["id"]) or next(iter(self.runtimes.values()))

    def _d(self, key):
        return super() if key in APP_KEYS else None

    def __getitem__(self, k): return dict.__getitem__(self, k) if k in APP_KEYS else self.rt().state[k]
    def __setitem__(self, k, v): dict.__setitem__(self, k, v) if k in APP_KEYS else self.rt().state.__setitem__(k, v)
    def __delitem__(self, k): dict.__delitem__(self, k) if k in APP_KEYS else self.rt().state.__delitem__(k)
    def __contains__(self, k): return dict.__contains__(self, k) if k in APP_KEYS else k in self.rt().state
    def get(self, k, default=None): return dict.get(self, k, default) if k in APP_KEYS else self.rt().state.get(k, default)
    def setdefault(self, k, default=None): return dict.setdefault(self, k, default) if k in APP_KEYS else self.rt().state.setdefault(k, default)
    def pop(self, k, *default): return dict.pop(self, k, *default) if k in APP_KEYS else self.rt().state.pop(k, *default)
    def update(self, *a, **kw):
        for k, v in dict(*a, **kw).items():
            self[k] = v


class StoreRouter:
    """What the dashboard sees as `store`: the data of the channel this request is for."""
    def __init__(self, app_state: AppState):
        self._app = app_state

    def __getattr__(self, name):
        return getattr(self._app.rt().store, name)


async def main(open_browser=False):    # open_browser is ignored: the dashboard is only shown in the app window
    reg = accounts.load()                 # 1.12.0: one folder per channel (None = the old layout, not moved yet)
    accounts.ACTIVE["id"] = reg["active"] if reg else None
    runtimes: dict = {}
    for cid in ([c["id"] for c in reg["channels"]] if reg else [None]):
        runtimes[cid] = Runtime(cid, Store(channel=cid))
    state = AppState(runtimes)            # shared with the dashboard
    store = StoreRouter(state)
    state["runtimes"] = runtimes
    store.apply_launch_defaults() if len(runtimes) == 1 else [rt.store.apply_launch_defaults() for rt in runtimes.values()]
    state["update_wake"] = asyncio.Event()
    try:   # the Windows start-up entry follows the settings (this also repairs it after an update)
        desktop.apply_prefs(store.get("prefs"))
    except Exception:
        log.exception("Could not update the Windows start-up entry")
    updater.cleanup()
    state["update_loop"] = asyncio.create_task(updater.loop(updater.U, store, state["update_wake"]))
    state["copies_task"] = asyncio.create_task(_two_copies_watch(store, state))

    # The dashboard starts first so it's available even if Twitch is down.
    try:
        await dashboard.start(store, state)
    except OSError as e:
        print(f"Could not start the dashboard: {e}. The bot will still run.")

    def start_channel(rt: Runtime):
        """Each channel runs in its own context: everything it does (its bot, logins, files) is that channel's."""
        ctx = contextvars.copy_context()
        ctx.run(accounts.CURRENT.set, rt.cid)
        rt.task = ctx.run(asyncio.create_task, channel_loop(rt, runtimes))
        return rt.task

    state["app"] = {"start_channel": start_channel,
                    "add_channel": lambda: add_channel(runtimes, start_channel),
                    "switch_channel": lambda cid: switch_channel(runtimes, cid),
                    "remove_channel": lambda cid: remove_channel(runtimes, cid)}
    await asyncio.gather(*[start_channel(rt) for rt in list(runtimes.values())])


PENDING = "pending"        # a channel being added: its Twitch login is running, its id isn't known yet


async def pick_sender(rt: Runtime, account: dict):
    """The BotSender for this channel, or None (its own account sends). Moves a pre-1.12.0 separate bot account into the
    shared list once (copying its login), so nothing changes in chat. A bot that was removed -> its own account, warned."""
    from core import botsender
    store, state, cid = rt.store, rt.state, rt.cid
    reg = accounts.load()
    entry = next((c for c in reg["channels"] if c.get("id") == cid), None)
    if entry is None:
        return None
    if store.get("settings").get("separate_bot") and not entry.get("bot_moved"):
        legacy = await botauth.get_account()       # this channel's old bot_token.json (copied into its folder)
        if legacy and str(legacy["user_id"]) != str(account["user_id"]):
            bid = str(legacy["user_id"])
            dest = accounts.bot_token_file(bid)
            if not dest.exists():
                accounts._copy_checked(botauth.token_file(), dest)
            if bid not in [b.get("id") for b in reg["bots"]]:
                reg["bots"].append({"id": bid, "login": legacy["login"], "added": int(time.time())})
            entry.update(sender=bid, bot_moved=True)
            accounts.save(reg)
            log.info("Moved the bot account %s into the bot list, sending for %s as before", legacy["login"], account["login"])
        elif not legacy:
            return "wait"          # switched on but never connected: stay silent like before 1.12.0 (no surprise as your own account)
    sid = entry.get("sender") or "own"
    state["sender_note"] = entry.get("sender_note")
    if sid == "own":
        return None
    bot = next((b for b in reg["bots"] if b.get("id") == sid), None)
    if bot is None or not accounts.bot_token_file(sid).exists():
        # never silently stop replying: the channel's own account sends, and the app says why
        entry.update(sender="own", sender_note={"what": "removed", "login": (bot or {}).get("login", sid), "at": int(time.time())})
        accounts.save(reg)
        state["sender_note"] = entry["sender_note"]
        log.warning("The bot account for %s is gone: its own account sends the replies now", account["login"])
        return None
    return botsender.get(sid, bot.get("login", ""))


async def run_bot(rt: Runtime, bot, token: str) -> bool:
    """Runs one channel's bot until it stops. True = start again at once (a setting changed / a new login)."""
    state = rt.state
    state["bot"] = bot
    def _reconnect(why, st=state):
        st["last_reconnect"] = {"why": why, "at": time.time()}
        dashboard.restart_bot(st)
    bot.request_restart = _reconnect
    bot.chat_verified = state["watchdog"].chat_verified
    try:
        await bot.start(token=token, with_adapter=False, load_tokens=False, save_tokens=False)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("Bot stopped unexpectedly")
        state["crashed"] = True
    finally:
        await bot.close()
    return bool(auth.load_token() is None or state.get("restart"))


async def after_stop(rt: Runtime, last_error_notice: float):
    """After a bot stopped by itself: reconnect (in 10 s, or when the Reconnect button is pressed)."""
    state, store = rt.state, rt.store
    if state.pop("crashed", False) and time.time() - last_error_notice > 600:
        last_error_notice = time.time()
        notify.error(store.get("prefs"), "The bot stopped unexpectedly. Details are in bot.log.")
    prefs = store.get("prefs")
    if not prefs.get("auto_reconnect", True):
        state["bot"] = None
        state["lost"] = True
        notify.error(prefs, "Lost the connection to Twitch. Open the dashboard and press Reconnect.")
        await state["wake"].wait()
        return last_error_notice
    log.info("Restarting in 10 seconds...")
    await asyncio.sleep(10)
    return last_error_notice


def switch_channel(runtimes: dict, cid) -> None:
    """The channel the app shows (and edits). The others keep running."""
    cid = str(cid)
    if cid not in runtimes or cid == PENDING:
        raise ValueError("Unknown channel.")
    accounts.ACTIVE["id"] = cid
    reg = accounts.load()
    if reg and reg.get("active") != cid:
        reg["active"] = cid
        accounts.save(reg)


def add_channel(runtimes: dict, start_channel) -> None:
    """"Add another channel": a Twitch login for it (in its own temporary place). When it is done, the channel gets its
    own folder (fresh), its own bot, and becomes the one the app shows. Signing in to a channel that is already there
    just switches to it (and refreshes its login)."""
    if accounts.load() is None:
        raise ValueError("Connect your first channel before adding another one.")
    if PENDING in runtimes:
        return
    shown = runtimes.get(accounts.ACTIVE["id"]) or next(iter(runtimes.values()))
    rt = Runtime(PENDING, shown.store)        # (pages show the current channel's data until the login is done)
    rt.state.update(login={"status": "idle"}, wake=asyncio.Event(), pending=True, back_to=accounts.ACTIVE["id"])
    runtimes[PENDING] = rt
    accounts.ACTIVE["id"] = PENDING
    ctx = contextvars.copy_context()
    ctx.run(accounts.CURRENT.set, PENDING)
    rt.task = ctx.run(asyncio.create_task, _finish_add(rt, runtimes, start_channel))


async def _finish_add(rt: Runtime, runtimes: dict, start_channel) -> None:
    import shutil
    try:
        dashboard.start_login(rt.state)
        await asyncio.sleep(0.5)
        while not rt.state["wake"].is_set() and rt.state["login"].get("status") == "waiting":
            await asyncio.sleep(0.5)
        account = await auth.get_account() if rt.state["wake"].is_set() else None
        if not account:
            return                                   # cancelled or failed: back to the channel shown before
        cid = str(account["user_id"])
        accounts.channel_token_file(cid).parent.mkdir(parents=True, exist_ok=True)
        accounts._copy_checked(accounts.channel_token_file(PENDING), accounts.channel_token_file(cid))
        if cid in runtimes:                           # already one of the channels: just refresh its login and show it
            dashboard.restart_bot(runtimes[cid].state)
        else:
            reg = accounts.load()
            reg["channels"].append({"id": cid, "login": account["login"], "added": int(time.time()), "sender": "own"})
            accounts.save(reg)
            runtimes[cid] = Runtime(cid, Store(channel=cid))
            start_channel(runtimes[cid])
            log.info("Added the channel %s", account["login"])
        rt.state["back_to"] = cid
    except Exception:
        log.exception("Adding a channel failed")
    finally:
        runtimes.pop(PENDING, None)
        shutil.rmtree(accounts.channel_token_file(PENDING).parent, ignore_errors=True)    # (only the temporary login)
        back = rt.state.get("back_to")
        accounts.ACTIVE["id"] = back if back in runtimes else next(iter(runtimes))
        try:
            switch_channel(runtimes, accounts.ACTIVE["id"])
        except ValueError:
            pass


async def remove_channel(runtimes: dict, cid) -> None:
    """Stops a channel's bot and takes it off the list. Its data folder is KEPT (adding it again brings everything back)."""
    cid = str(cid)
    reg = accounts.load()
    if not reg or cid not in runtimes or len([c for c in reg["channels"]]) <= 1:
        raise ValueError("The last channel can't be removed.")
    rt = runtimes.pop(cid)
    bot = rt.state.get("bot")
    if rt.task:
        rt.task.cancel()
    if bot is not None:
        try:
            await bot.close()
        except Exception:
            pass
    reg["channels"] = [c for c in reg["channels"] if c.get("id") != cid]
    if reg.get("active") == cid:
        reg["active"] = reg["channels"][0]["id"]
    accounts.save(reg)
    if accounts.ACTIVE["id"] == cid:
        accounts.ACTIVE["id"] = reg["active"]
    log.info("Removed the channel %s from the list (its data folder is kept)", cid)


async def channel_loop(rt: Runtime, runtimes: dict):
    """One channel's bot, from its login to reconnecting: the same as the whole app did before 1.12.0."""
    store, state = rt.store, rt.state
    state["watchdog"] = watchdog.Watchdog(state, store, lambda: dashboard.restart_bot(state))   # reconnects the bot by itself if it silently stops hearing Twitch
    state["watchdog_task"] = asyncio.create_task(state["watchdog"].run())
    state["publist_syncer"] = publiclist.Syncer(store, state)    # the public command list website
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

    state["login"] = {"status": "idle"}
    state["bot_login"] = {"status": "idle"}      # the login of the separate bot account
    state["wake"] = asyncio.Event()
    auto_login = len(runtimes) == 1    # first start: begin "Connect Twitch" automatically, like before

    # Waits for a Twitch account (the dashboard's Connect button can start the login),
    # then runs the bot. Automatic reconnection: if the bot ever stops or crashes, start it again.
    while True:
        state["wake"].clear()
        state["lost"] = False
        state["restart"] = False
        account = await auth.get_account()
        if account is None:
            if state.get("had_login") and not state.get("user_logout"):
                # the login was rejected and the saved one is dead too: say so once (instead of a silent bot)
                notify.error(store.get("prefs"), "Your Twitch login expired. Open the app and connect Twitch again.")
                log.warning("The saved Twitch login is no longer valid: waiting for the user to connect again")
            state["had_login"] = False
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
        if rt.cid is None:
            # First start of 1.12.0: copy the data into its channel folder (backup zip first, checked copies, the old files
            # stay). If anything fails, cid is None and the app simply keeps using the old files, like before.
            cid = accounts.migrate_legacy(account)
            if cid:
                accounts.CURRENT.set(cid)      # (this channel's context only)
                accounts.ACTIVE["id"] = cid
                runtimes[cid] = runtimes.pop(None)
                rt.cid = cid
                store.use_channel(cid)
                store.apply_launch_defaults()
        print(f"Connected as {account['login']}")
        state["account"] = account["login"]
        state["had_login"], state["user_logout"] = True, False
        state["avatar_task"] = asyncio.create_task(dashboard.load_avatar(state, account))   # profile picture for the dashboard
        state["account_id"] = account["user_id"]
        if state.get("banned"):
            # the developer turned the app off for this channel: no bot, the dashboard explains it; an unban wakes this up
            state["bot"] = None
            print("FQPN's Chat Bot has been turned off for this channel by its developer.")
            await state["wake"].wait()
            continue

        if accounts.load() is not None and rt.cid not in (None, PENDING):
            # 1.12.0: who sends this channel's replies comes from the shared bot list (its own account, or one bot account)
            sender = await pick_sender(rt, account)
            if sender == "wait":
                state["bot"] = None
                print("The separate bot account is switched on but not connected. Waiting for it to be connected...")
                await state["wake"].wait()
                continue
            state["bot_account"] = sender.login if sender else None
            bot = TwitchBot(account, store, sender=sender)
            if await run_bot(rt, bot, account["access_token"]):
                continue
            last_error_notice = await after_stop(rt, last_error_notice)
            if last_error_notice is None:
                return
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
        def _reconnect(why, st=state):
            st["last_reconnect"] = {"why": why, "at": time.time()}
            dashboard.restart_bot(st)
        bot.request_restart = _reconnect          # a rejected login / a silent chat: reconnect by itself
        bot.chat_verified = state["watchdog"].chat_verified   # a quiet chat with a confirmed connection is not reconnected
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
