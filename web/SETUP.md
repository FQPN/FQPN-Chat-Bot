# Public command list website: setup

This folder is the website for **Commands → Public list** in the app. It is one file, `worker.js`, that runs on
Cloudflare's free plan. It is **not** part of the app or the installer.

You do this once. It takes about 10 minutes. Cloudflare changes its menus now and then, so if a button has a slightly
different name, look for the closest match.

## 1. Make a free Cloudflare account
1. Go to <https://dash.cloudflare.com/sign-up> and sign up (free, no card needed).
2. In the left menu open **Workers & Pages** (on some accounts it is under **Compute**).
   The first time, Cloudflare asks you to pick your **workers.dev subdomain**. Pick something short, for example `fqpn`.
   Your website address will be `https://fqpn-commands.<your-subdomain>.workers.dev`.

## 2. Make the database
1. Left menu: **Storage & Databases → D1 SQL Database → Create**.
2. Name: `fqpn-commands` → **Create**. (You don't need to make any tables: the website makes them by itself.)

## 3. Make the website
1. Left menu: **Workers & Pages → Create → Create Worker** (or "Start with Hello World").
2. Name: `fqpn-commands` → **Deploy**.
3. Click **Edit code**. Delete everything in the editor, paste the whole of `worker.js` from this folder, then **Deploy**.

## 4. Connect the database to the website
1. Open the worker `fqpn-commands` → **Bindings** (or **Settings → Bindings**) → **Add binding → D1 database**.
2. **Variable name:** `DB` (exactly, in capitals) → **D1 database:** `fqpn-commands` → **Add binding** / **Deploy**.

## 5. Tell it which app may save lists
1. Same worker → **Settings → Variables and Secrets → Add**.
2. Type **Text**, name `TWITCH_CLIENT_ID`, value `sk61bb5z9anwbymut5y6svq13q6q5c` → **Deploy**.
   (This is your app's public Twitch client ID, the same one in `core/auth.py`. With it, only logins made by
   FQPN's Chat Bot can save lists.)

## 5b. Your private users list (v1.4.0)
1. Same worker → **Settings → Variables and Secrets → Add**.
2. Type **Secret** (not Text), name `ADMIN_KEY`, value: a long password only you know (at least 12 characters) → **Deploy**.
3. Open `https://<your website>/admin` and type that password. It shows every channel that uses the app: name (a link to
   their Twitch), app version, last seen and first seen. Nobody without the password can see it.
   Or in D1 → Console: `SELECT login, version, datetime(last_seen,'unixepoch') FROM seen ORDER BY last_seen DESC;`

## 6. Check it
- Open `https://fqpn-commands.<your-subdomain>.workers.dev/` → you should see "Public command lists".
- Open `https://fqpn-commands.<your-subdomain>.workers.dev/fqpn_` → "No list here" (correct: nothing is saved yet).

## 7. Put the address in the app
Send the address to Claude, or set it yourself in `core/publiclist.py`:
```python
SITE = "https://fqpn-commands.<your-subdomain>.workers.dev"
```
(no slash at the end). Then release the app as usual. A build with `SITE = ""` keeps the feature switched off and
says "isn't set up" in the app.

---

## Looking after it

**Free limits (checked October 2026):** Workers: 100,000 requests a day. D1: 5 million rows read and 100,000 rows written
a day, 5 GB stored. One save writes about 3 rows; one page view reads 1. Current numbers:
<https://developers.cloudflare.com/workers/platform/pricing/> and <https://developers.cloudflare.com/d1/platform/pricing/>.
If a daily limit is reached, saves and pages fail until 00:00 UTC; the app simply tries again later.

**Remove someone's list** (for example, an offensive command name): D1 → `fqpn-commands` → **Console**, run
```sql
DELETE FROM lists WHERE login = 'channelname';
```
**Stop that channel from publishing again:**
```sql
INSERT INTO blocked (who, note) VALUES ('channelname', 'why');
```
Undo the block: `DELETE FROM blocked WHERE who = 'channelname';`
See every list: `SELECT login, display, updated FROM lists ORDER BY updated DESC;`

**Switch the website off:** worker `fqpn-commands` → **Settings → Domains & Routes** → turn off the `workers.dev` route
(links stop working, saved lists stay). Turn it on again later and the old links work again. To remove everything, delete
the worker and the database.

**Update the website:** open the worker → **Edit code** → paste the new `worker.js` → **Deploy**. Saved lists are kept.

## What it stores
For each channel: the Twitch login and user ID, display name, profile picture link, the command names with who can use
them, and when it was saved. It never stores the Twitch token: it only uses it to ask Twitch whose channel it is.
