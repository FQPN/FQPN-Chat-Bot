// FQPN's Chat Bot: public command lists.
//
// One Cloudflare Worker with one D1 database (bound as DB). The app sends a channel's public commands here and viewers open
// SITE/<channel> to see them. Setup steps: web/SETUP.md.
//
//   GET    /                    the app's home page: download, features, install steps, FAQ (and what the lists are)
//   GET    /download/windows    the newest installer (asks GitHub's releases; two path parts, so never a channel name)
//   GET    /api/latest          the newest release as JSON (version, date, size, installer link)
//   POST   /api/support         a suggestion or problem from the app's Support page, forwarded to the developers' Discord
//                                (the webhook link is the secret DISCORD_WEBHOOK_URL: it never leaves Cloudflare)
//   GET    /<channel>           the channel's command list (English / Arabic)
//   GET    /api/list/<channel>  the same list as JSON
//   PUT    /api/list            save your list    (Authorization: OAuth <your Twitch login token from the app>)
//   DELETE /api/list            remove your list  (same)
//   PUT    /api/seen            "this channel uses the app, version X" (once a day from every app; same login check)
//   GET    /api/dev/users       the users list, ONLY for the app's developers (their Twitch login, checked by user ID)
//   PUT    /api/dev/ban         ban / unban a channel from using the app (developers only)
//
// The Twitch token is only used to ask Twitch whose channel it is. It is never stored or logged.

const FORMAT = 1;              // the newest data format the app sends; older formats keep working
const MAX_COMMANDS = 500;
const MAX_NAME = 60;
const MAX_BODY = 256 * 1024;   // bytes (1.13.0: 64 -> 256 KB, each command can carry a short example)
const MAX_EX = 100;             // 1.13.0: an example reply, at most this many characters
const BI_KEYS = ["commands", "title", "game", "app", "addcom", "editcom", "delcom"];
const GAME_ROWS = { letters: ["start", "approve"], scramble: ["start"], emoji: ["start"], reverse: ["start"], math: ["start"], ladder: ["start"], trivia: ["start"], shared: ["wins", "top", "random"] };
const LB_KEYS = ["l", "u", "e", "r", "m", "s", "q"];          // 1.14.0: حروف, رتب, ايموجي, عكس, احسب
const MIN_GAP = 5;             // seconds between two saves of the same channel
const PERMS = ["everyone", "subscriber", "vip", "moderator", "broadcaster"];
const LOGIN_RE = /^[a-z0-9_]{1,25}$/;
const VERSION_RE = /^[0-9A-Za-z.+-]{1,32}$/;
const SEEN_GAP = 3600;
// The app's developers by permanent Twitch user ID (same list as core/greetings.py). To add one, add the ID in both places.
const DEVELOPERS = new Set(["1299878164" /* 1asoom */, "754527671" /* fqpn_ */]);         // one report per channel per hour is plenty (the app sends once a day)
const AVATAR_RE = /^https:\/\/static-cdn\.jtvnw\.net\/[A-Za-z0-9._\/-]+$/;
// The download (home page): the newest release of the app on GitHub, asked at most every 10 minutes.
const REPO = "FQPN/FQPN-Chat-Bot";
const RELEASES = "https://github.com/" + REPO + "/releases";
const LATEST_TTL = 600;        // seconds a good answer from GitHub is kept
const LATEST_RETRY = 60;       // seconds before asking again after GitHub failed
const LOGO = "data:image/png;base64,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";
let latestCache = null;        // { at, data } (one copy per worker instance; Cloudflare's cache keeps GitHub's answer too)

async function latest() {
  const now = Date.now();
  if (latestCache && now - latestCache.at < (latestCache.data ? LATEST_TTL : LATEST_RETRY) * 1000) return latestCache.data;
  let data = null;
  try {
    const r = await fetch("https://api.github.com/repos/" + REPO + "/releases/latest", {
      headers: { "User-Agent": "FQPN-Chat-Bot-website", Accept: "application/vnd.github+json" },
      cf: { cacheTtl: LATEST_TTL, cacheEverything: true } });
    if (r.ok) {
      const j = await r.json();
      const assets = Array.isArray(j.assets) ? j.assets : [];
      const a = assets.find((x) => /setup.*\.exe$/i.test(x.name || "")) || assets.find((x) => /\.exe$/i.test(x.name || ""));
      const v = String(j.tag_name || "").replace(/^v/i, "");
      if (a && /^\d+\.\d+\.\d+$/.test(v) && /^https:\/\/github\.com\//.test(a.browser_download_url || "")) {
        const t = Date.parse(j.published_at || "");
        data = { version: v, date: Number.isFinite(t) ? Math.floor(t / 1000) : 0, size: Number(a.size) || 0, url: a.browser_download_url,
                 notes: /^https:\/\/github\.com\//.test(j.html_url || "") ? j.html_url : RELEASES };
      }
    }
  } catch { data = null; }
  // GitHub down: keep showing the last good answer (and ask again in a minute)
  latestCache = { at: now, data: data || (latestCache && latestCache.data) || null };
  if (!data && latestCache.data) latestCache.at = now - (LATEST_TTL - LATEST_RETRY) * 1000;
  return latestCache.data;
}

function logoBytes() {
  const b = atob(LOGO.split(",")[1]);
  const u = new Uint8Array(b.length);
  for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i);
  return u;
}

let tablesReady = false;
async function setup(db) {
  if (tablesReady) return;
  await db.batch([
    db.prepare("CREATE TABLE IF NOT EXISTS lists (login TEXT PRIMARY KEY, user_id TEXT NOT NULL, display TEXT, avatar TEXT, data TEXT NOT NULL, updated INTEGER NOT NULL)"),
    db.prepare("CREATE INDEX IF NOT EXISTS lists_user ON lists(user_id)"),
    db.prepare("CREATE TABLE IF NOT EXISTS blocked (who TEXT PRIMARY KEY, note TEXT)"),
    db.prepare("CREATE TABLE IF NOT EXISTS bans (user_id TEXT PRIMARY KEY, login TEXT, at INTEGER NOT NULL, by TEXT)"),
    db.prepare("CREATE TABLE IF NOT EXISTS support (user_id TEXT NOT NULL, at INTEGER NOT NULL)"),
    db.prepare("CREATE INDEX IF NOT EXISTS support_at ON support(at)"),
    db.prepare("CREATE TABLE IF NOT EXISTS seen (user_id TEXT PRIMARY KEY, login TEXT NOT NULL, display TEXT, version TEXT, first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL)"),
  ]);
  tablesReady = true;
}

export default {
  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (e) {
      // The usual reason after moving the worker (a new Cloudflare account): no database connected. Say exactly that.
      if (!env || !env.DB) {
        const msg = "The website's database isn't connected. In Cloudflare: this worker → Settings → Bindings → Add → D1 database, variable name DB.";
        if (new URL(request.url).pathname.startsWith("/api/")) return json({ error: msg }, 503);
        return page(`<section class="hero"><h1>Website not set up yet</h1><p class="lead">${esc(msg)}</p>` +
          `<p class="lead" dir="rtl" lang="ar">قاعدة بيانات الموقع غير موصولة. في Cloudflare: هذا الـ worker ← Settings ← Bindings ← Add ← D1 database، والاسم DB.</p></section>`,
          "Website not set up", 503, 0);
      }
      return json({ error: "Something went wrong on the website. Try again later." }, 500);
    }
  },
};

async function handle(req, env) {
  const url = new URL(req.url);
  const path = url.pathname;
  if (path === "/api/list") {
    if (req.method === "PUT") return saveList(req, env, url);
    if (req.method === "DELETE") return deleteList(req, env);
    return json({ error: "Method not allowed." }, 405, { Allow: "PUT, DELETE" });
  }
  if (path === "/api/seen") {
    if (req.method === "PUT") return saveSeen(req, env);
    return json({ error: "Method not allowed." }, 405, { Allow: "PUT" });
  }
  if (path === "/api/support") {
    if (req.method !== "POST") return json({ error: "Method not allowed." }, 405, { Allow: "POST" });
    return support(req, env);
  }
  if (path === "/api/dev/users") {
    if (req.method !== "GET") return json({ error: "Method not allowed." }, 405, { Allow: "GET" });
    return devUsers(req, env);
  }
  if (path === "/api/dev/ban") {
    if (req.method !== "PUT") return json({ error: "Method not allowed." }, 405, { Allow: "PUT" });
    return devBan(req, env);
  }
  if (path.startsWith("/api/editor/")) {          // 1.13.0: the editor link
    return ["/api/editor/link", "/api/editor/page", "/api/editor/data", "/api/editor/changes", "/api/editor/ack"].includes(path) ? editorOwner(req, env, url) : editorGuest(req, env, url);
  }
  if (req.method !== "GET" && req.method !== "HEAD") return json({ error: "Method not allowed." }, 405, { Allow: "GET" });
  if (path === "/") return page(homeBody(url.origin, await latest(), await userCount(env)), "FQPN's Chat Bot · Twitch moderation chat bot", 200, 600);
  if (path === "/download/windows" || path === "/download") {
    const l = await latest();                      // the newest installer, or the releases page when GitHub can't be reached
    return new Response(null, { status: 302, headers: { Location: l ? l.url : RELEASES + "/latest", "Cache-Control": "no-store" } });
  }
  if (path === "/api/latest") {
    const l = await latest();
    return l ? json({ version: l.version, date: l.date, size: l.size, url: l.url }, 200, { ...CORS, "Cache-Control": "public, max-age=300" })
             : json({ error: "GitHub can't be reached right now.", releases: RELEASES }, 503, CORS);
  }
  if (path === "/robots.txt") return new Response("User-agent: *\nAllow: /\n", { headers: { "Content-Type": "text/plain; charset=utf-8" } });
  if (path === "/favicon.ico" || path === "/favicon.png") {
    return new Response(logoBytes(), { headers: { "Content-Type": "image/png", "Cache-Control": "public, max-age=86400" } });
  }

  let m = path.match(/^\/api\/list\/([^/]+)$/);
  if (m) {
    const login = cleanLogin(m[1]);
    if (!login) return json({ error: "Not found." }, 404, CORS);
    await setup(env.DB);
    const row = await env.DB.prepare("SELECT * FROM lists WHERE login = ?").bind(login).first();
    if (!row) return json({ error: "Not found." }, 404, CORS);
    return json(publicView(row), 200, { ...CORS, "Cache-Control": "public, max-age=30" });
  }
  m = path.match(/^\/@?([^/]+)\/edit\/([^/]+)\/app\/?$/);
  if (m) {                                         // 1.13.0: the app's own page, working on this channel through the link
    let raw; try { raw = decodeURIComponent(m[1]); } catch { raw = ""; }
    const login = cleanLogin(raw) || "", token = m[2];
    const link = login ? await editorLink(env, login, token) : null;
    const pg = link ? await env.DB.prepare("SELECT html FROM editor_page WHERE login = ?").bind(login).first() : null;
    if (!pg) return Response.redirect(new URL("/" + login + "/edit/" + token, url).toString(), 302);
    const boot = `<script>window.REMOTE=${JSON.stringify({ login, token, expires: link.expires }).replace(/</g, "\\u003c")};</script>`;
    const html = pg.html.replace(/<head>/i, "<head>" + boot);
    return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
      "X-Robots-Tag": "noindex, nofollow", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
      // the app's page uses inline scripts and styles (it is the app's own file, uploaded by the channel's app)
      "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com data:; img-src 'self' data: https://static-cdn.jtvnw.net; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'" } });
  }
  m = path.match(/^\/@?([^/]+)\/edit\/([^/]+)\/?$/);
  if (m) {                                         // 1.13.0: the editor page (a secret link; three path parts, never a channel)
    let raw; try { raw = decodeURIComponent(m[1]); } catch { raw = ""; }
    const login = cleanLogin(raw) || "", token = m[2];
    const link = login ? await editorLink(env, login, token) : null;
    const row = link ? await env.DB.prepare("SELECT display FROM lists WHERE login = ?").bind(login).first() : null;
    // the editor's script runs INSIDE the page script, so it can use its helpers ($, t, toast) and its language switch
    const script = CLIENT.replace(/\napply\(\);\n\}\)\(\);$/, "\napply();\n" + EDITOR_JS + "\n})();");
    const resp = page(editorBody(login, row && row.display, token, !!link), "FQPN's Chat Bot · " + TEXT.en.ed_t, link ? 200 : 410, 0, null, script, "connect-src 'self'; ");
    resp.headers.set("Referrer-Policy", "no-referrer");       // the secret link never goes to another site
    resp.headers.set("X-Robots-Tag", "noindex, nofollow");
    return resp;
  }
  m = path.match(/^\/@?([^/]+?)(\/leaderboard)?\/?$/);
  if (m) {
    let raw;
    try { raw = decodeURIComponent(m[1]); } catch { raw = ""; }
    const login = cleanLogin(raw);
    if (!login) return page(missingBody(""), "Not found", 404, 60);
    const tab = m[2] ? "lb" : "cmds", canon = "/" + login + (m[2] ? "/leaderboard" : "");
    if (path !== canon) return Response.redirect(url.origin + canon, 301);
    await setup(env.DB);
    const row = await env.DB.prepare("SELECT * FROM lists WHERE login = ?").bind(login).first();
    if (!row) return page(missingBody(login), "Not found", 404, 30);
    const view = publicView(row);
    return page(listBody(view), (view.display || login) + (tab === "lb" ? " · leaderboard" : " · commands"), 200, 30, { ...view, tab });
  }
  return page(missingBody(""), "Not found", 404, 60);
}

const CORS = { "Access-Control-Allow-Origin": "*" };

function cleanLogin(s) {
  const login = String(s || "").trim().replace(/^@/, "").toLowerCase();
  return LOGIN_RE.test(login) ? login : "";
}

function publicView(row) {
  let data = {};
  try { data = JSON.parse(row.data); } catch { data = {}; }
  return { v: FORMAT, login: row.login, display: row.display || row.login, avatar: row.avatar || "",
           updated: row.updated, commands: Array.isArray(data.commands) ? data.commands : [],
           accent: (typeof data.accent === "string" && HEX_RE.test(data.accent)) ? data.accent : "",
           leaderboard: data.leaderboard && typeof data.leaderboard === "object" ? data.leaderboard : null };
}

// ----------------------------------------------------------------------------------------------- saving and removing

async function whoIs(req, env) {
  const m = (req.headers.get("Authorization") || "").match(/^(?:OAuth|Bearer)\s+([A-Za-z0-9]{10,200})$/);
  if (!m) return { status: 401, error: "Connect Twitch in the app first." };
  let r;
  try {
    r = await fetch("https://id.twitch.tv/oauth2/validate", { headers: { Authorization: "OAuth " + m[1] } });
  } catch {
    return { status: 503, error: "Twitch can't be reached right now." };
  }
  if (r.status === 401) return { status: 401, error: "Twitch didn't accept this login. Connect Twitch again in the app." };
  if (!r.ok) return { status: 503, error: "Twitch can't be reached right now." };
  const v = await r.json();
  const login = cleanLogin(v.login);
  if (!login || !v.user_id) return { status: 401, error: "Twitch didn't accept this login." };
  if (env.TWITCH_CLIENT_ID && v.client_id !== env.TWITCH_CLIENT_ID) {
    return { status: 403, error: "Only FQPN's Chat Bot can save lists here." };
  }
  return { login, userId: String(v.user_id), token: m[1], clientId: v.client_id };
}

async function profile(who) {
  // the channel's display name and picture, for the page (if Twitch does not answer, the login is shown instead)
  try {
    const r = await fetch("https://api.twitch.tv/helix/users", { headers: { Authorization: "Bearer " + who.token, "Client-Id": who.clientId } });
    if (!r.ok) return {};
    const u = ((await r.json()).data || [])[0] || {};
    const display = typeof u.display_name === "string" && u.display_name.toLowerCase() === who.login ? u.display_name : "";
    const avatar = typeof u.profile_image_url === "string" && AVATAR_RE.test(u.profile_image_url) ? u.profile_image_url : "";
    return { display, avatar };
  } catch {
    return {};
  }
}

function cleanLeaderboard(lb) {
  if (!lb || typeof lb !== "object" || Array.isArray(lb)) return null;
  const n = (x) => Math.max(0, Math.min(1e9, Math.floor(Number(x) || 0)));
  const rows = (a, parts) => (Array.isArray(a) ? a : []).slice(0, 10).map((r) => {
    const name = String((r && r.n) || "").replace(/[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/g, "").trim().slice(0, 40);
    if (!name) return null;
    const out = { n: name, w: n(r.w) };
    if (parts) LB_KEYS.forEach((k) => { out[k] = n(r[k]); });
    return out;
  }).filter((r) => r && r.w > 0);
  const out = { all: rows(lb.all, true) };
  LB_KEYS.forEach((k) => { out[k] = rows(lb[k], false); });
  return out;
}

function cleanList(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) return { error: "The list couldn't be read." };
  const v = Number(body.v);
  if (!Number.isInteger(v) || v < 1) return { error: "The list couldn't be read." };
  if (!Array.isArray(body.commands)) return { error: "The list couldn't be read." };
  if (body.commands.length > MAX_COMMANDS) return { error: `A list can have at most ${MAX_COMMANDS} commands.` };
  const seen = new Set();
  const commands = [];
  for (const c of body.commands) {
    if (!c || typeof c !== "object") continue;
    // keep printable text only: no control characters, no invisible direction overrides
    const name = String(c.name ?? "").replace(/[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/g, "").trim();
    if (!name || [...name].length > MAX_NAME || seen.has(name)) continue;
    seen.add(name);
    const row = { name, perm: PERMS.includes(c.perm) ? c.perm : "everyone" };
    if (c.builtin === true) {                          // 1.12.0: the app's built-in commands (shown in their own group)
      row.builtin = true;
      if (BI_KEYS.includes(c.key)) row.key = c.key;      // 1.13.0: the page words what it does
    } else if (GAME_ROWS[c.game] && GAME_ROWS[c.game].includes(c.what)) {
      row.game = c.game; row.what = c.what;            // 1.13.0: a mini game's command (its own group)
    } else if (typeof c.ex === "string") {
      const ex = [...c.ex.replace(/[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/g, "").trim()].slice(0, MAX_EX).join("");
      if (ex) row.ex = ex;                               // 1.13.0: a short example of the reply
    }
    commands.push(row);
  }
  const accent = typeof body.accent === "string" && HEX_RE.test(body.accent.trim().toLowerCase()) ? body.accent.trim().toLowerCase() : "";
  const lb = cleanLeaderboard(body.leaderboard);        // 1.13.0: the games' top 10 (only when the app sends it)
  return { list: { v: FORMAT, commands, ...(accent ? { accent } : {}), ...(lb ? { leaderboard: lb } : {}) } };
}

async function saveList(req, env, url) {
  const text = await req.text();
  if (new TextEncoder().encode(text).length > MAX_BODY) return json({ error: "The list is too big." }, 413);
  let body;
  try { body = JSON.parse(text); } catch { return json({ error: "The list couldn't be read." }, 400); }
  const clean = cleanList(body);
  if (clean.error) return json({ error: clean.error }, 400);
  const who = await whoIs(req, env);
  if (who.error) return json({ error: who.error }, who.status);
  await setup(env.DB);
  const blocked = await env.DB.prepare("SELECT 1 FROM blocked WHERE who IN (?, ?)").bind(who.login, "id:" + who.userId).first();
  if (blocked) return json({ error: "This channel can't publish a list here." }, 403);
  const now = Math.floor(Date.now() / 1000);
  const last = await env.DB.prepare("SELECT MAX(updated) AS t FROM lists WHERE user_id = ?").bind(who.userId).first();
  if (last && last.t && now - last.t < MIN_GAP) {
    return json({ error: "Saving too often. Wait a few seconds." }, 429, { "Retry-After": String(MIN_GAP) });
  }
  const p = await profile(who);
  await env.DB.batch([
    // a channel that changed its name: the list moves to the new name
    env.DB.prepare("DELETE FROM lists WHERE user_id = ? AND login <> ?").bind(who.userId, who.login),
    env.DB.prepare("INSERT INTO lists (login, user_id, display, avatar, data, updated) VALUES (?, ?, ?, ?, ?, ?) " +
                   "ON CONFLICT(login) DO UPDATE SET user_id = excluded.user_id, display = excluded.display, " +
                   "avatar = excluded.avatar, data = excluded.data, updated = excluded.updated")
      .bind(who.login, who.userId, p.display || who.login, p.avatar || "", JSON.stringify(clean.list), now),
  ]);
  // 1.13.0: what this website understands, so a newer app knows it can send them (an older website says nothing -> the app
  // keeps the mini games' commands back instead of seeing them land among the streamer's own commands)
  return json({ ok: true, login: who.login, count: clean.list.commands.length, url: url.origin + "/" + who.login, features: ["examples", "games", "builtin_keys"] });
}

async function deleteList(req, env) {
  const who = await whoIs(req, env);
  if (who.error) return json({ error: who.error }, who.status);
  await setup(env.DB);
  await env.DB.prepare("DELETE FROM lists WHERE user_id = ?").bind(who.userId).run();
  return json({ ok: true });
}

// ----------------------------------------------------------------------------------------------- who uses the app

async function saveSeen(req, env) {
  const text = await req.text();
  if (text.length > 1024) return json({ error: "Too big." }, 413);
  let body;
  try { body = JSON.parse(text); } catch { return json({ error: "The report couldn't be read." }, 400); }
  const version = String((body && body.version) || "");
  if (!VERSION_RE.test(version)) return json({ error: "The report couldn't be read." }, 400);
  const who = await whoIs(req, env);
  if (who.error) return json({ error: who.error }, who.status);
  await setup(env.DB);
  const now = Math.floor(Date.now() / 1000);
  const banned = !!(await env.DB.prepare("SELECT 1 FROM bans WHERE user_id = ?").bind(who.userId).first());
  const row = await env.DB.prepare("SELECT last_seen FROM seen WHERE user_id = ?").bind(who.userId).first();
  if (row && now - row.last_seen < SEEN_GAP) return json({ ok: true, counted: false, banned }, 429, { "Retry-After": String(SEEN_GAP) });
  const p = await profile(who);
  await env.DB.prepare("INSERT INTO seen (user_id, login, display, version, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?) " +
                       "ON CONFLICT(user_id) DO UPDATE SET login = excluded.login, display = excluded.display, version = excluded.version, last_seen = excluded.last_seen")
    .bind(who.userId, who.login, p.display || who.login, version, now, now).run();
  return json({ ok: true, counted: true, banned });
}

// ---- Support (1.11.0): the app's Support page -> here -> the developers' Discord channel
const SUPPORT = { text: 2000, contact: 50, images: 4, imageBytes: 4 * 1024 * 1024, allBytes: 8 * 1024 * 1024, logBytes: 256 * 1024,
                  perHour: 5, allPerHour: 120 };
const IMAGE_TYPES = [["png", [0x89, 0x50, 0x4e, 0x47]], ["jpg", [0xff, 0xd8, 0xff]], ["gif", [0x47, 0x49, 0x46, 0x38]], ["webp", [0x52, 0x49, 0x46, 0x46]]];

async function imageKind(file) {            // what the file really is (its first bytes), not what its name says
  const head = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  for (const [kind, magic] of IMAGE_TYPES) {
    if (magic.every((b, i) => head[i] === b) && (kind !== "webp" || String.fromCharCode(...head.slice(8, 12)) === "WEBP")) return kind;
  }
  return "";
}

function oneLine(s, max) { return String(s || "").replace(/[\u0000-\u001f\u007f]+/g, " ").trim().slice(0, max); }

async function support(req, env) {
  if (!env.DISCORD_WEBHOOK_URL) return json({ error: "Support isn't set up on the website yet." }, 503);
  if (Number(req.headers.get("Content-Length") || 0) > SUPPORT.allBytes + SUPPORT.logBytes + 64 * 1024) return json({ error: "The message is too big." }, 413);
  let form;
  try { form = await req.formData(); } catch { return json({ error: "The message couldn't be read." }, 400); }
  const kind = form.get("kind") === "problem" ? "problem" : form.get("kind") === "suggestion" ? "suggestion" : "";
  const text = String(form.get("text") || "").replace(/\r\n?/g, "\n").trim();
  const contact = oneLine(form.get("contact"), SUPPORT.contact);
  const version = oneLine(form.get("version"), 40), os = oneLine(form.get("os"), 80);
  if (!kind) return json({ error: "Choose Suggestion or Problem." }, 400);
  if (text.length < 5) return json({ error: "Write a few words first." }, 400);
  if (text.length > SUPPORT.text) return json({ error: `A message can be at most ${SUPPORT.text} characters.` }, 400);
  const images = form.getAll("image").filter((f) => typeof f === "object" && f && f.size > 0);
  if (images.length > SUPPORT.images) return json({ error: `At most ${SUPPORT.images} images.` }, 400);
  let total = 0;
  const files = [];
  for (const f of images) {
    const k = await imageKind(f);
    if (!k) return json({ error: "Only pictures can be sent (PNG, JPG, WebP or GIF)." }, 400);
    if (f.size > SUPPORT.imageBytes) return json({ error: "A picture can be at most 4 MB." }, 400);
    total += f.size;
    files.push([f, "image" + (files.length + 1) + "." + k]);
  }
  if (total > SUPPORT.allBytes) return json({ error: "All pictures together can be at most 8 MB." }, 400);
  const log = form.get("log");
  if (log && typeof log === "object" && log.size > 0) {
    if (kind !== "problem" || log.size > SUPPORT.logBytes) return json({ error: "The log couldn't be attached." }, 400);
    files.push([log, "bot.log.txt"]);
  }
  const who = await whoIs(req, env);
  if (who.error) return json({ error: who.error }, who.status);
  await setup(env.DB);
  if (await env.DB.prepare("SELECT 1 FROM bans WHERE user_id = ?").bind(who.userId).first()) return json({ error: "This channel can't send messages." }, 403);
  const now = Math.floor(Date.now() / 1000);
  const mine = await env.DB.prepare("SELECT COUNT(*) AS n FROM support WHERE user_id = ? AND at > ?").bind(who.userId, now - 3600).first();
  if (!DEVELOPERS.has(who.userId) && mine && mine.n >= SUPPORT.perHour) {
    return json({ error: `You can send ${SUPPORT.perHour} messages an hour. Try again later.` }, 429, { "Retry-After": "3600" });
  }
  const all = await env.DB.prepare("SELECT COUNT(*) AS n FROM support WHERE at > ?").bind(now - 3600).first();
  if (all && all.n >= SUPPORT.allPerHour) return json({ error: "Too many messages right now. Try again later." }, 429, { "Retry-After": "600" });

  const p = await profile(who);
  const embed = {
    title: (kind === "problem" ? "🐞 Problem" : "💡 Suggestion") + " · " + (p.display || who.login),
    url: "https://www.twitch.tv/" + who.login,
    description: text,
    color: kind === "problem" ? 0xe5484d : 0xe5b74b,
    fields: [{ name: "Channel", value: `[${who.login}](https://www.twitch.tv/${who.login})`, inline: true },
             { name: "App", value: version || "?", inline: true }].concat(
             contact ? [{ name: "Contact", value: contact.replace(/([*_~`|>\\])/g, "\\$1"), inline: true }] : [],
             os ? [{ name: "Windows", value: os, inline: true }] : []),
    timestamp: new Date(now * 1000).toISOString(),
  };
  if (files.length && files[0][1].startsWith("image")) embed.image = { url: "attachment://" + files[0][1] };
  const out = new FormData();
  // allowed_mentions: nobody is pinged, whatever the message says (no @everyone, no roles, no users)
  out.append("payload_json", JSON.stringify({ username: "FQPN's Chat Bot · Support", embeds: [embed], allowed_mentions: { parse: [] } }));
  files.forEach(([f, name], i) => out.append("files[" + i + "]", f, name));
  let r;
  try { r = await fetch(env.DISCORD_WEBHOOK_URL, { method: "POST", body: out }); } catch { r = null; }
  if (!r || !r.ok) {
    return json({ error: r && r.status === 429 ? "Too many messages right now. Try again later." : "The message couldn't be delivered. Try again later." },
                r && r.status === 429 ? 429 : 502);
  }
  await env.DB.batch([env.DB.prepare("INSERT INTO support (user_id, at) VALUES (?, ?)").bind(who.userId, now),
                      env.DB.prepare("DELETE FROM support WHERE at < ?").bind(now - 86400)]);
  return json({ ok: true });
}

// ---- Editor link (1.13.0): someone the streamer trusts edits the commands from a secret link + password
// The app makes the link (a 256-bit secret in the URL) and a new password each time; the website only keeps their SHA-256
// hashes (never the link or the password). One link per channel, it ends after 24 h, when the app cancels it, or after 5
// wrong passwords. The edits wait here; the streamer's app takes them, checks them with its own rules, saves them and says
// which were applied or refused. The commands the editor sees are a private copy the app uploads (not the public page).
const ED = { maxHours: 24, attempts: 5, pending: 100, perHour: 120, name: 40, response: 500, aliases: 10, cooldown: 86400,
             pageMax: 1800000, dataMax: 1500000, putMax: 600000 };
// 1.13.0: the editor works on the APP'S OWN page (uploaded by the app with the link), on these tools; the rest isn't there
const ED_SECTIONS = ["commands", "timers", "greetings", "events", "blocklist", "moderation", "games", "settings"];
async function sha256hex(s) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(String(s)));
  return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join("");
}
function randHex(n) { return [...crypto.getRandomValues(new Uint8Array(n))].map((x) => x.toString(16).padStart(2, "0")).join(""); }
const HEX_RE = /^#[0-9a-f]{6}$/;
const EDTOKEN_RE = /^[A-Za-z0-9_-]{30,100}$/;
function cleanText(s, max) { return String(s ?? "").replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, "").trim().slice(0, max); }
function cleanCmdName(s) { return String(s ?? "").replace(/[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/g, "").trim(); }

async function edTables(db) {
  await db.batch([
    db.prepare("CREATE TABLE IF NOT EXISTS editor_links (login TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT NOT NULL, pw_salt TEXT NOT NULL, pw_hash TEXT NOT NULL, expires INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL)"),
    db.prepare("CREATE TABLE IF NOT EXISTS editor_data (login TEXT PRIMARY KEY, data TEXT NOT NULL, updated INTEGER NOT NULL)"),
    db.prepare("CREATE TABLE IF NOT EXISTS editor_sessions (id_hash TEXT PRIMARY KEY, login TEXT NOT NULL, token_hash TEXT NOT NULL, name TEXT, expires INTEGER NOT NULL)"),
    db.prepare("CREATE TABLE IF NOT EXISTS editor_changes (id INTEGER PRIMARY KEY AUTOINCREMENT, login TEXT NOT NULL, token_hash TEXT NOT NULL, at INTEGER NOT NULL, editor TEXT, op TEXT NOT NULL, name TEXT NOT NULL, old_name TEXT, cmd TEXT, status TEXT NOT NULL, note TEXT)"),
    db.prepare("CREATE INDEX IF NOT EXISTS editor_changes_login ON editor_changes(login, status)"),
    db.prepare("CREATE TABLE IF NOT EXISTS editor_page (login TEXT PRIMARY KEY, html TEXT NOT NULL, updated INTEGER NOT NULL)"),
  ]);
}

function edSnapshot(body) {        // the app's private copy of the commands, for the editor page
  if (!body || !Array.isArray(body.commands)) return null;
  const out = [];
  for (const c of body.commands.slice(0, MAX_COMMANDS)) {
    if (!c || typeof c !== "object") continue;
    const name = cleanCmdName(c.name);
    if (!name || [...name].length > MAX_NAME) continue;
    out.push({ name, response: cleanText(c.response, ED.response), perm: PERMS.includes(c.perm) ? c.perm : "everyone",
               cooldown: Math.max(0, Math.min(ED.cooldown, Math.floor(Number(c.cooldown) || 0))), enabled: c.enabled !== false,
               aliases: (Array.isArray(c.aliases) ? c.aliases : []).map(cleanCmdName).filter((a) => a && [...a].length <= MAX_NAME).slice(0, ED.aliases),
               locked: c.locked === true });          // (a shortcut or a game command: shown, but changed in the app only)
  }
  return out;
}

async function editorOwner(req, env, url) {        // the streamer's app: PUT/DELETE the link, the copy, the edits
  const who = await whoIs(req, env);
  if (who.error) return json({ error: who.error }, who.status);
  await setup(env.DB); await edTables(env.DB);
  const now = Math.floor(Date.now() / 1000), db = env.DB, path = url.pathname;
  if (path === "/api/editor/link" && req.method === "PUT") {
    let body; try { body = await req.json(); } catch { body = null; }
    const th = String(body?.token_hash || ""), salt = String(body?.pw_salt || ""), ph = String(body?.pw_hash || "");
    if (!/^[0-9a-f]{64}$/.test(th) || !/^[0-9a-f]{32}$/.test(salt) || !/^[0-9a-f]{64}$/.test(ph)) return json({ error: "The link couldn't be read." }, 400);
    const snap = edSnapshot(body);
    if (!snap) return json({ error: "The commands couldn't be read." }, 400);
    const expires = now + ED.maxHours * 3600;
    await db.batch([       // a new link replaces the old one at once (its sessions and waiting edits end with it)
      db.prepare("INSERT OR REPLACE INTO editor_links (login, user_id, token_hash, pw_salt, pw_hash, expires, attempts, created) VALUES (?, ?, ?, ?, ?, ?, 0, ?)").bind(who.login, who.userId, th, salt, ph, expires, now),
      db.prepare("INSERT OR REPLACE INTO editor_data (login, data, updated) VALUES (?, ?, ?)").bind(who.login, JSON.stringify(snap), now),
      db.prepare("DELETE FROM editor_sessions WHERE login = ?").bind(who.login),
      db.prepare("DELETE FROM editor_changes WHERE login = ? AND token_hash != ?").bind(who.login, th),
    ]);
    return json({ ok: true, login: who.login, expires });
  }
  if (path === "/api/editor/page" && req.method === "PUT") {
    const raw = await req.text();
    if (raw.length > ED.pageMax + 100) return json({ error: "The app's page is too big." }, 413);
    let body; try { body = JSON.parse(raw); } catch { body = null; }
    const html = typeof body?.html === "string" ? body.html : "";
    if (!html.startsWith("<!doctype html>") && !html.startsWith("<!DOCTYPE html>")) return json({ error: "The app's page couldn't be read." }, 400);
    await db.prepare("INSERT OR REPLACE INTO editor_page (login, html, updated) VALUES (?, ?, ?)").bind(who.login, html, now).run();
    return json({ ok: true });
  }
  if (path === "/api/editor/link" && req.method === "DELETE") {
    await db.batch([db.prepare("DELETE FROM editor_page WHERE login = ?").bind(who.login),
                    db.prepare("DELETE FROM editor_links WHERE login = ?").bind(who.login), db.prepare("DELETE FROM editor_sessions WHERE login = ?").bind(who.login),
                    db.prepare("DELETE FROM editor_data WHERE login = ?").bind(who.login), db.prepare("DELETE FROM editor_changes WHERE login = ?").bind(who.login)]);
    return json({ ok: true });
  }
  const link = await db.prepare("SELECT * FROM editor_links WHERE login = ?").bind(who.login).first();
  if (!link || link.expires <= now) return json({ ok: true, active: false, changes: [] });
  if (path === "/api/editor/data" && req.method === "PUT") {
    const raw = await req.text();
    if (raw.length > ED.dataMax) return json({ error: "Too much data." }, 413);
    let body; try { body = JSON.parse(raw); } catch { body = null; }
    const snap = edSnapshot(body);
    if (!snap) return json({ error: "The commands couldn't be read." }, 400);
    const full = body && typeof body.sections === "object" && body.sections ? { commands: snap, sections: body.sections, digests: body.digests || {}, logs: body.logs || {}, status: body.status || {} } : snap;
    await db.prepare("INSERT OR REPLACE INTO editor_data (login, data, updated) VALUES (?, ?, ?)").bind(who.login, JSON.stringify(full), now).run();
    return json({ ok: true });
  }
  if (path === "/api/editor/changes" && req.method === "GET") {
    const rows = (await db.prepare("SELECT id, at, editor, op, name, old_name, cmd FROM editor_changes WHERE login = ? AND token_hash = ? AND status = 'pending' ORDER BY id LIMIT 50").bind(who.login, link.token_hash).all()).results || [];
    return json({ ok: true, active: true, expires: link.expires, changes: rows.map((r) => r.op === "put"
      ? { id: r.id, at: r.at, editor: r.editor, op: "put", section: r.name, base: r.old_name || "", data: r.cmd ? JSON.parse(r.cmd) : null }
      : { ...r, cmd: r.cmd ? JSON.parse(r.cmd) : null }) });
  }
  if (path === "/api/editor/ack" && req.method === "POST") {
    let body; try { body = await req.json(); } catch { body = null; }
    const res = Array.isArray(body?.results) ? body.results.slice(0, 100) : [];
    const stmts = res.filter((r) => Number.isInteger(r?.id)).map((r) => db.prepare("UPDATE editor_changes SET status = ?, note = ? WHERE id = ? AND login = ?")
      .bind(r.ok ? "applied" : "refused", cleanText(r.error, 200), r.id, who.login));
    if (stmts.length) await db.batch(stmts);
    return json({ ok: true });
  }
  return json({ error: "Not found." }, 404);
}

async function editorLink(env, login, token) {
  await setup(env.DB); await edTables(env.DB);
  if (!LOGIN_RE.test(login) || !EDTOKEN_RE.test(token)) return null;
  const link = await env.DB.prepare("SELECT * FROM editor_links WHERE login = ?").bind(login).first();
  if (!link || link.expires <= Math.floor(Date.now() / 1000) || link.attempts >= ED.attempts) return null;
  return link.token_hash === await sha256hex(token) ? link : null;
}

async function editorGuest(req, env, url) {        // the editor's page: password, then read / change
  const path = url.pathname, db = env.DB, now = Math.floor(Date.now() / 1000);
  let body = null;
  if (req.method === "POST") { try { body = await req.json(); } catch { body = null; } }
  const login = cleanLogin(String((body?.login ?? req.headers.get("X-Editor-Login")) || "")), token = String((body?.token ?? req.headers.get("X-Editor-Token")) || "");
  const link = await editorLink(env, login, token);
  if (!link) return json({ error: "expired" }, 410);
  if (path === "/api/editor/session" && req.method === "POST") {
    const name = cleanText(body?.name, ED.name);
    if (!name) return json({ error: "name" }, 400);
    if (await sha256hex(link.pw_salt + String(body?.password || "").trim().toUpperCase()) !== link.pw_hash) {
      await db.prepare("UPDATE editor_links SET attempts = attempts + 1 WHERE login = ?").bind(login).run();
      const left = ED.attempts - link.attempts - 1;
      return json({ error: left > 0 ? "password" : "locked", left }, 403);
    }
    const sid = randHex(32);
    await db.prepare("INSERT INTO editor_sessions (id_hash, login, token_hash, name, expires) VALUES (?, ?, ?, ?, ?)").bind(await sha256hex(sid), login, link.token_hash, name, link.expires).run();
    return json({ ok: true, session: sid, expires: link.expires });
  }
  const sid = String(req.headers.get("X-Editor-Session") || "");
  const ses = /^[0-9a-f]{64}$/.test(sid) ? await db.prepare("SELECT * FROM editor_sessions WHERE id_hash = ?").bind(await sha256hex(sid)).first() : null;
  if (!ses || ses.login !== login || ses.token_hash !== link.token_hash || ses.expires <= now) return json({ error: "session" }, 401);
  if (path === "/api/editor/state" && req.method === "GET") {
    const data = await db.prepare("SELECT data, updated FROM editor_data WHERE login = ?").bind(login).first();
    const recent = (await db.prepare("SELECT id, at, editor, op, name, status, note FROM editor_changes WHERE login = ? AND token_hash = ? ORDER BY id DESC LIMIT 30").bind(login, link.token_hash).all()).results || [];
    const d = data ? JSON.parse(data.data) : [];
    const full = Array.isArray(d) ? { commands: d } : d;
    return json({ ok: true, commands: full.commands || [], sections: full.sections || null, digests: full.digests || {}, logs: full.logs || {}, status: full.status || {},
                  updated: data ? data.updated : 0, expires: link.expires, changes: recent, me: ses.name, login });
  }
  if (path === "/api/editor/change" && req.method === "POST") {
    if (body?.op === "put") {               // a whole tool, saved on the app's own page
      const section = String(body.section || "");
      if (!ED_SECTIONS.includes(section)) return json({ error: "This can't be changed through the editor link." }, 400);
      const data = JSON.stringify(body.data ?? null);
      if (data.length > ED.putMax) return json({ error: "Too much data in one change." }, 413);
      const base = /^[0-9a-f]{64}$/.test(String(body.base || "")) ? String(body.base) : "";
      const pending = await db.prepare("SELECT COUNT(*) AS n FROM editor_changes WHERE login = ? AND status = 'pending'").bind(login).first();
      if (pending && pending.n >= ED.pending) return json({ error: "Too many changes are waiting for the app. Try again when it has taken them." }, 429);
      const hour = await db.prepare("SELECT COUNT(*) AS n FROM editor_changes WHERE login = ? AND at > ?").bind(login, now - 3600).first();
      if (hour && hour.n >= ED.perHour) return json({ error: "Too many changes this hour. Try again later." }, 429);
      const r = await db.prepare("INSERT INTO editor_changes (login, token_hash, at, editor, op, name, old_name, cmd, status) VALUES (?, ?, ?, ?, 'put', ?, ?, ?, 'pending')")
        .bind(login, link.token_hash, now, ses.name, section, base || null, data).run();
      return json({ ok: true, id: r.meta?.last_row_id ?? null });
    }
    const op = body?.op === "delete" ? "delete" : body?.op === "set" ? "set" : "";
    const name = cleanCmdName(body?.name), old = body?.old_name ? cleanCmdName(body.old_name) : "";
    if (!op || !name || [...name].length > MAX_NAME || /\s{2,}/.test(name)) return json({ error: "A command name is 1 to 60 characters." }, 400);
    let cmd = null;
    if (op === "set") {
      const c = body?.cmd || {};
      const response = cleanText(c.response, ED.response + 1);
      if (!response) return json({ error: "Write the reply." }, 400);
      if ([...response].length > ED.response) return json({ error: `A reply can be at most ${ED.response} characters.` }, 400);
      cmd = { response, permission: PERMS.includes(c.permission) ? c.permission : "everyone",
              cooldown: Math.max(0, Math.min(ED.cooldown, Math.floor(Number(c.cooldown) || 0))), enabled: c.enabled !== false,
              aliases: (Array.isArray(c.aliases) ? c.aliases : []).map(cleanCmdName).filter(Boolean).slice(0, ED.aliases) };
      if (cmd.aliases.some((a) => [...a].length > MAX_NAME)) return json({ error: "An extra name is at most 60 characters." }, 400);
    }
    const pending = await db.prepare("SELECT COUNT(*) AS n FROM editor_changes WHERE login = ? AND status = 'pending'").bind(login).first();
    if (pending && pending.n >= ED.pending) return json({ error: "Too many changes are waiting for the app. Try again when it has taken them." }, 429);
    const hour = await db.prepare("SELECT COUNT(*) AS n FROM editor_changes WHERE login = ? AND at > ?").bind(login, now - 3600).first();
    if (hour && hour.n >= ED.perHour) return json({ error: "Too many changes this hour. Try again later." }, 429);
    const r = await db.prepare("INSERT INTO editor_changes (login, token_hash, at, editor, op, name, old_name, cmd, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')")
      .bind(login, link.token_hash, now, ses.name, op, name, old || null, cmd ? JSON.stringify(cmd) : null).run();
    return json({ ok: true, id: r.meta?.last_row_id ?? null });
  }
  return json({ error: "Not found." }, 404);
}

function editorBody(login, display, token, ok) {
  if (!ok) return `<header class="top"><div class="who"><div class="av mark" aria-hidden="true"></div><div><h1 data-t="ed_t">${T("ed_t")}</h1></div></div>${langBtn()}</header>
<div class="miss"><h2 data-t="ed_gone_t">${T("ed_gone_t")}</h2><p data-t="ed_gone_d">${T("ed_gone_d")}</p></div>`;
  return `<header class="top"><div class="who"><div class="av mark" aria-hidden="true"></div><div><h1><bdi>${esc(display || login)}</bdi> <span class="sub2" data-t="ed_t">${T("ed_t")}</span></h1><p class="count" id="edexp"></p></div></div>${langBtn()}</header>
<div id="ed" data-login="${esc(login)}" data-token="${esc(token)}">
<form class="edlogin" id="edlogin" autocomplete="off"><h2 data-t="ed_in_t">${T("ed_in_t")}</h2><p class="lead small" data-t="ed_in_d">${T("ed_in_d")}</p>
<label for="edname" data-t="ed_name">${T("ed_name")}</label><input id="edname" maxlength="40" required>
<label for="edpw" data-t="ed_pw">${T("ed_pw")}</label><input id="edpw" maxlength="20" required spellcheck="false" autocapitalize="characters" dir="ltr">
<p class="ederr" id="ederr" role="alert" hidden></p><button class="edbtn" type="submit" data-t="ed_go">${T("ed_go")}</button></form>
<section id="edmain" hidden>
<p class="ednote" data-t="ed_how">${T("ed_how")}</p>
<div class="edbar"><input id="q" type="search" autocomplete="off"><button class="edbtn" type="button" id="edadd" data-t="ed_add">${T("ed_add")}</button></div>
<form class="edform" id="edform" hidden autocomplete="off">
<h2 id="edftitle"></h2>
<label for="efname" data-t="ed_cmd">${T("ed_cmd")}</label><input id="efname" maxlength="60" required dir="auto">
<label for="efresp" data-t="ed_resp">${T("ed_resp")}</label><textarea id="efresp" maxlength="500" rows="4" required dir="auto"></textarea><span class="edcount" id="efcnt"></span>
<div class="edrow"><div><label for="efperm" data-t="ed_who">${T("ed_who")}</label><select id="efperm">${PERMS.map((p) => `<option value="${p}" data-t="g_${p}">${T("g_" + p)}</option>`).join("")}</select></div>
<div><label for="efcd" data-t="ed_cd">${T("ed_cd")}</label><input id="efcd" type="number" min="0" max="86400" value="5"></div></div>
<label for="efal" data-t="ed_al">${T("ed_al")}</label><input id="efal" dir="auto">
<label class="edcheck"><input type="checkbox" id="efon" checked><span data-t="ed_on">${T("ed_on")}</span></label>
<p class="ederr" id="eferr" role="alert" hidden></p>
<div class="edrow end"><button class="edbtn ghost" type="button" id="efcancel" data-t="ed_cancel">${T("ed_cancel")}</button><button class="edbtn" type="submit" data-t="ed_save">${T("ed_save")}</button></div></form>
<div id="edlist" class="edlist"></div>
<h2 class="edh" data-t="ed_recent">${T("ed_recent")}</h2><div id="edrecent" class="edrecent"></div>
</section></div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>`;
}

const EDITOR_JS = `
;(function(){var box=$("ed");if(!box)return;var L=box.dataset.login,TK=box.dataset.token,SID=null,ST=null,EDIT=null,poll=null;
try{SID=sessionStorage.getItem("ed:"+TK)}catch(e){}
function esc2(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
async function api(path,body){var h={"X-Editor-Login":L,"X-Editor-Token":TK,"X-Editor-Session":SID||""};if(body)h["Content-Type"]="application/json";
  var r,d={};try{r=await fetch(path,{method:body?"POST":"GET",headers:h,body:body?JSON.stringify(Object.assign({login:L,token:TK},body)):undefined});d=await r.json()}catch(e){return {ok:false,status:0,d:{error:"net"}}}
  if(r.status==410){gone();return {ok:false,status:410,d:d}}
  if(r.status==401){SID=null;try{sessionStorage.removeItem("ed:"+TK)}catch(e){}$("edmain").hidden=true;$("edlogin").hidden=false}
  return {ok:r.ok,status:r.status,d:d}}
function gone(){box.innerHTML='<div class="miss"><h2>'+esc2(t("ed_gone_t"))+'</h2><p>'+esc2(t("ed_gone_d"))+'</p></div>';clearInterval(poll)}
function err(id,msg){var e=$(id);e.textContent=msg||"";e.hidden=!msg}
function left(){if(!ST)return;var s=ST.expires-Date.now()/1000,h=Math.floor(s/3600),m=Math.max(0,Math.floor(s%3600/60));$("edexp").textContent=s<=0?t("ed_gone_t"):h>0?t("ed_left_h",{h:h,m:m}):t("ed_left_m",{m:m})}
$("edlogin").addEventListener("submit",async function(e){e.preventDefault();err("ederr","");
  var r=await api("/api/editor/session",{name:$("edname").value,password:$("edpw").value});
  if(r.ok){SID=r.d.session;try{sessionStorage.setItem("ed:"+TK,SID)}catch(e){}location.replace(location.pathname.replace(/\\/$/,"")+"/app");return}
  var c=r.d.error;err("ederr",c=="password"?t("ed_wrong",{n:r.d.left}):c=="locked"?t("ed_locked"):c=="name"?t("ed_need_name"):c=="net"?t("ed_net"):t("ed_gone_t"));if(c=="locked")setTimeout(gone,2500)});
async function load(){var r=await api("/api/editor/state");if(!r.ok)return;ST=r.d;draw2();left()}
function permName(p){return t("g_"+p)}
function draw2(){if(!ST)return;var q=($("q").value||"").trim().toLowerCase();
  var rows=ST.commands.filter(function(c){return !q||c.name.toLowerCase().indexOf(q)>=0||c.response.toLowerCase().indexOf(q)>=0});
  $("edlist").innerHTML=rows.length?rows.map(function(c,i){return '<div class="edcmd'+(c.enabled?"":" off")+'"><div class="edtop"><bdi class="edname">'+esc2(c.name)+'</bdi>'
     +'<span class="edmeta">'+esc2(permName(c.perm))+' · '+esc2(t("ed_cd_s",{n:c.cooldown}))+(c.enabled?"":' · '+esc2(t("ed_offl")))+(c.aliases.length?' · '+esc2(c.aliases.join(", ")):"")+'</span>'
     +(c.locked?'<span class="edlock">'+esc2(t("ed_locked_cmd"))+'</span>':'<span class="edbtns"><button type="button" class="edbtn ghost sm" data-edit="'+esc2(c.name)+'">'+esc2(t("ed_edit"))+'</button><button type="button" class="edbtn ghost sm danger" data-del="'+esc2(c.name)+'">'+esc2(t("ed_del"))+'</button></span>')
     +'</div><p class="edresp" dir="auto">'+esc2(c.response)+'</p></div>'}).join(""):'<p class="ednote">'+esc2(t(ST.commands.length?"none":"ed_empty"))+'</p>';
  var waiting=ST.changes.filter(function(x){return x.status=="pending"}).length;
  $("edrecent").innerHTML=ST.changes.length?ST.changes.map(function(x){var st=x.status=="pending"?["wait",t("ed_st_wait")]:x.status=="applied"?["ok",t("ed_st_ok")]:["bad",t("ed_st_bad")+(x.note?": "+x.note:"")];
     return '<div class="edch"><i class="edot '+st[0]+'"></i><span><bdi>'+esc2(x.name)+'</bdi> · '+esc2(t(x.op=="delete"?"ed_op_del":"ed_op_set"))+' · '+esc2(x.editor||"")+'</span><span class="edst '+st[0]+'">'+esc2(st[1])+'</span></div>'}).join(""):'<p class="ednote">'+esc2(t("ed_no_recent"))+'</p>';
  clearInterval(poll);poll=setInterval(function(){load()},waiting?3000:15000)}
function openForm(c){EDIT=c?c.name:null;$("edform").hidden=false;$("edftitle").textContent=c?t("ed_edit_t",{n:c.name}):t("ed_add_t");
  $("efname").value=c?c.name:"";$("efresp").value=c?c.response:"";$("efperm").value=c?c.perm:"everyone";$("efcd").value=c?c.cooldown:5;$("efal").value=c?c.aliases.join(", "):"";$("efon").checked=c?c.enabled:true;err("eferr","");cnt();$("efname").focus();window.scrollTo(0,0)}
function cnt(){var n=[...$("efresp").value].length;$("efcnt").textContent=n+"/500";$("efcnt").classList.toggle("over",n>500)}
$("efresp").addEventListener("input",cnt);
$("edadd").onclick=function(){openForm(null)};$("efcancel").onclick=function(){$("edform").hidden=true;EDIT=null};
$("q").addEventListener("input",draw2);
$("edlist").addEventListener("click",async function(e){var b=e.target.closest("[data-edit]"),d=e.target.closest("[data-del]");
  if(b){openForm(ST.commands.filter(function(c){return c.name==b.dataset.edit})[0]);return}
  if(d&&confirm(t("ed_del_q",{n:d.dataset.del}))){var r=await api("/api/editor/change",{op:"delete",name:d.dataset.del});toast(r.ok?t("ed_sent"):(r.d.error||t("ed_net")));load()}});
$("edform").addEventListener("submit",async function(e){e.preventDefault();err("eferr","");
  var cmd={response:$("efresp").value,permission:$("efperm").value,cooldown:+$("efcd").value||0,enabled:$("efon").checked,aliases:$("efal").value.split(",").map(function(s){return s.trim()}).filter(Boolean)};
  var r=await api("/api/editor/change",{op:"set",name:$("efname").value,old_name:EDIT&&EDIT!=$("efname").value.trim()?EDIT:"",cmd:cmd});
  if(!r.ok){err("eferr",r.d.error||t("ed_net"));return}$("edform").hidden=true;EDIT=null;toast(t("ed_sent"));load()});
function start(){$("edlogin").hidden=true;$("edmain").hidden=false;load();setInterval(left,30000)}
var q=$("q");q.placeholder=t("search");
$("lang").addEventListener("click",function(){setTimeout(function(){draw2();left();q.placeholder=t("search")},0)});   // the lists follow the language
if(SID)location.replace(location.pathname.replace(/\\/$/,"")+"/app");
})();
`;


// ---- developers only: checked here by Twitch user ID, whatever the app shows
async function devWho(req, env) {
  const who = await whoIs(req, env);
  if (who.error) return { res: json({ error: who.error }, who.status) };
  if (!DEVELOPERS.has(who.userId)) {
    await new Promise((r) => setTimeout(r, 500));
    return { res: json({ error: "Only the app's developers can see this." }, 403) };
  }
  return { who };
}

async function devUsers(req, env) {
  const d = await devWho(req, env);
  if (d.res) return d.res;
  await setup(env.DB);
  const rows = (await env.DB.prepare("SELECT s.user_id, s.login, s.display, s.version, s.first_seen, s.last_seen, (b.user_id IS NOT NULL) AS banned, " +
                                     "(l.login IS NOT NULL) AS has_list FROM seen s LEFT JOIN bans b ON b.user_id = s.user_id " +
                                     "LEFT JOIN lists l ON l.login = s.login ORDER BY s.last_seen DESC").all()).results || [];
  const live = await liveNow(d.who, rows.map((r) => String(r.user_id)));     // 1.14.0: who is live right now (null: Twitch didn't answer)
  return json({ now: Math.floor(Date.now() / 1000), live_checked: live !== null, users: rows.map((r) => {
    const l = live && live.get(String(r.user_id));
    return { ...r, banned: !!r.banned, developer: DEVELOPERS.has(String(r.user_id)), has_list: !!r.has_list,
             live: live === null ? null : !!l, viewers: l ? l.viewers : 0, game: l ? l.game : "", live_since: l ? l.since : 0 };
  }) });
}

// 1.14.0: Twitch's "Get Streams" with the developer's own login (any Twitch login may ask it): up to 100 channels a call.
// Map user_id -> { viewers, game, since } for the ones live now; null when Twitch can't be asked (the page then says so).
async function liveNow(who, ids) {
  const out = new Map();
  try {
    for (let i = 0; i < ids.length; i += 100) {
      const q = ids.slice(i, i + 100).filter((x) => /^\d{1,20}$/.test(x)).map((x) => "user_id=" + x).join("&");
      if (!q) continue;
      const r = await fetch("https://api.twitch.tv/helix/streams?first=100&" + q, { headers: { Authorization: "Bearer " + who.token, "Client-Id": who.clientId } });
      if (!r.ok) return null;
      const j = await r.json();
      for (const st of j.data || []) {
        if (st.type !== "live") continue;
        out.set(String(st.user_id), { viewers: Number(st.viewer_count) || 0, game: String(st.game_name || "").slice(0, 80),
                                      since: Math.floor(Date.parse(st.started_at || "") / 1000) || 0 });
      }
    }
  } catch (e) {
    return null;
  }
  return out;
}

async function devBan(req, env) {
  const d = await devWho(req, env);
  if (d.res) return d.res;
  let body;
  try { body = JSON.parse(await req.text()); } catch { return json({ error: "The request couldn't be read." }, 400); }
  const uid = String((body && body.user_id) || "");
  if (!/^\d{1,20}$/.test(uid)) return json({ error: "The request couldn't be read." }, 400);
  if (DEVELOPERS.has(uid)) return json({ error: "A developer can't be banned." }, 400);
  await setup(env.DB);
  if (body.banned) {
    const s = await env.DB.prepare("SELECT login FROM seen WHERE user_id = ?").bind(uid).first();
    await env.DB.prepare("INSERT INTO bans (user_id, login, at, by) VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET at = excluded.at, by = excluded.by")
      .bind(uid, (s && s.login) || "", Math.floor(Date.now() / 1000), d.who.login).run();
  } else {
    await env.DB.prepare("DELETE FROM bans WHERE user_id = ?").bind(uid).run();
  }
  return json({ ok: true, user_id: uid, banned: !!body.banned });
}

// ----------------------------------------------------------------------------------------------- answers

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", ...headers },
  });
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// data placed inside <script type="application/json">: nothing in it can end the script tag
function scriptJson(data) {
  return JSON.stringify(data).replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
}

function page(body, title, status, maxAge, data, script = CLIENT, cspExtra = "") {
  const nonce = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16))));
  const html = `<!doctype html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark light">
<title>${esc(title)}</title>
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600&family=Tajawal:wght@400;500;700&display=swap">
<style nonce="${nonce}">${CSS}${data && HEX_RE.test(String(data.accent || "")) ? ":root{--red2:" + data.accent + ";--glow1:color-mix(in srgb," + data.accent + " 42%,transparent);--glow2:color-mix(in srgb," + data.accent + " 24%,transparent)}" +
  "@media (prefers-color-scheme:light){:root{--glow1:color-mix(in srgb," + data.accent + " 16%,transparent);--glow2:color-mix(in srgb," + data.accent + " 9%,transparent)}}" : ""}</style>
</head>
<body>
<main class="wrap">${body}</main>
${data ? `<script type="application/json" id="data">${scriptJson(data)}</script>` : ""}
<script nonce="${nonce}">${script}</script>
</body>
</html>`;
  return new Response(html, {
    status,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": maxAge ? `public, max-age=${maxAge}` : "no-store",
      "Content-Security-Policy": `default-src 'none'; ${cspExtra}script-src 'nonce-${nonce}'; style-src 'nonce-${nonce}' https://fonts.googleapis.com; ` +
        "font-src https://fonts.gstatic.com; img-src 'self' data: https://static-cdn.jtvnw.net; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
    },
  });
}

// Every text on the pages exists in English and Arabic; the script swaps them by the data-t keys.
const TEXT = {
  en: {
    commands: "Commands", count: "{n} commands", count1: "1 command", count2: "2 commands", count_few: "{n} commands", search: "Search commands", none: "No commands match your search.",
    empty: "This channel has no public commands yet.", copy: "Click a command to copy it.", copied: "Copied {c}",
    g_builtin: "Built-in commands", g_games: "Mini games", bd_commands: "Links to this page with every command.", bd_title: "Shows the stream title. Moderators change it by writing a new title after it.", bd_game: "Shows the game. Moderators change it by writing a game name after it.", bd_app: "Says which app runs this chat bot.", bd_addcom: "Moderators add a new command from chat.", bd_editcom: "Moderators change a command's reply from chat.", bd_delcom: "Moderators delete a command from chat.", gd_letters_start: "Starts a Letters round: be the first to write a word from the category that starts with the given letter.", gd_letters_approve: "Moderators accept a word the bot didn't know, and that viewer wins the round.", gd_scramble_start: "Starts a word scramble: the first to write the word in the right order wins.", gd_shared_wins: "Shows how many rounds you've won.", gd_shared_top: "Sends the link to the games leaderboard.", gd_emoji_start: "Starts «ايموجي»: guess the word from the emojis; the first right answer wins.", gd_reverse_start: "Starts «عكس»: a word written backwards; the first to write it the right way wins.", gd_math_start: "Starts «احسب»: a quick sum; the first right answer wins.", gd_ladder_start: "Starts «سلم»: the fastest to write a few words starting with a letter wins.", gd_trivia_start: "Starts «سؤال»: an easy question with 4 choices; the first right answer wins.", gd_shared_random: "Starts a round of a random game.", bi_who: "Built in to FQPN's Chat Bot · {w} can use it", g_everyone: "Everyone", g_subscriber: "Subscribers", g_vip: "VIPs", g_moderator: "Moderators", g_broadcaster: "Broadcaster",
    updated: "Updated {t}", made: "Made with FQPN's Chat Bot", lang: "العربية",
    home_t: "Public command lists", home_d: "Streamers who use FQPN's Chat Bot can share their chat commands here. Open a link like {u} to see a channel's list.",
    miss_t: "No list here", miss_d: "There is no public command list for {c}. The streamer can switch it on in FQPN's Chat Bot, on the Commands page.",
    lb_tab: "Games leaderboard", lb_all: "All games", wins: "{n} wins", win1: "1 win", lb_empty: "No wins yet.",
    players1: "1 player", players2: "2 players", players_few: "{n} players", players: "{n} players",
    ed_t: "Edit commands", ed_gone_t: "This editor link has ended", ed_gone_d: "It expired, was cancelled, or a new one replaced it. Ask the streamer for a new link and password.",
    ed_in_t: "Sign in to edit", ed_in_d: "The streamer gave you this link and a password. Your name is shown to the streamer next to each change.",
    ed_name: "Your name", ed_pw: "Password", ed_go: "Open the editor", ed_wrong: "Wrong password. {n} tries left.", ed_locked: "Too many wrong passwords: this link is locked. Ask the streamer for a new one.",
    ed_need_name: "Write your name.", ed_net: "The website can't be reached. Try again.",
    ed_left_h: "Link ends in {h} h {m} min", ed_left_m: "Link ends in {m} min",
    ed_how: "Your changes go to the streamer's app, which checks them and applies them within seconds while it runs (or as soon as it opens).",
    ed_add: "Add command", ed_add_t: "New command", ed_edit_t: "Edit {n}", ed_cmd: "Command", ed_resp: "Reply", ed_who: "Who can use it", ed_cd: "Wait between uses (seconds)",
    ed_al: "Extra names (separate with commas)", ed_on: "Switched on", ed_save: "Send the change", ed_cancel: "Cancel", ed_edit: "Edit", ed_del: "Delete",
    ed_del_q: "Delete {n}?", ed_sent: "Sent: the app applies it in a few seconds", ed_cd_s: "{n} s", ed_offl: "off", ed_locked_cmd: "change it in the app",
    ed_empty: "No commands yet. Add the first one.", ed_recent: "Your changes", ed_no_recent: "Nothing changed yet.",
    ed_st_wait: "waiting for the app", ed_st_ok: "applied", ed_st_bad: "refused", ed_op_set: "saved", ed_op_del: "deleted",
    miss_d0: "This page doesn't exist.",
    // the home page (download)
    h_title: "Twitch moderation chat bot", h_lead: "Commands, timers, greetings, replies to Twitch events, chat moderation and mini games, all set up in an app in English and Arabic. Free.",
    dl: "Download for Windows", dl_users: "streamers use it", dl_meta: "Version {v} · {d} · {s} MB", dl_down: "Get the newest version from GitHub", dl_req: "Windows 10 or 11 · installs for your user, no administrator needed",
    dl_all: "All versions and what changed",
    f_t: "What it does",
    f1_t: "Commands", f1_d: "With aliases, user levels, cooldowns and variables like $(user), $(followage), $(weather city) and $(accountage).",
    f2_t: "Timers", f2_d: "Messages on a schedule while you're live, like a reminder to follow or to join your Discord.",
    f3_t: "Twitch events", f3_d: "Replies for follows, subs, gift subs, raids, hype trains, bits, watch streaks and donations, with running totals.",
    f4_t: "Greetings", f4_d: "A hello for the people you choose, once per stream, in your own words.",
    f5_t: "Blocklist", f5_d: "People the bot ignores: their commands get no answer.",
    f6_t: "Moderation", f6_d: "Filters for bad words in Arabic and English, links, caps, emotes, symbols and spam, and a log of what was done.",
    f7_t: "Mini games", f7_d: "Five games: «حروف», «رتب», «ايموجي», «عكس» and «احسب», with «لعبه؟» for a random one, and leaderboards.",
    f8_t: "Test chat", f8_d: "Try every command, game and event reply as any viewer, without Twitch. With ready-made recipes.",
    f9_t: "Giveaways", f9_d: "Draw an active chatter, let viewers join with a keyword, or guess a number. Subscriber luck and rerolls.",
    f10_t: "Public command list", f10_d: "One link to a page with all your commands, an example of what each says, and the games leaderboard.",
    f11_t: "Editor link", f11_d: "Let someone you trust edit your commands from the website, with a link and a one-time password.",
    f12_t: "English and Arabic", f12_d: "The whole app in both languages, right to left in Arabic, in dark and light.",
    s_t: "Install in a minute",
    s1: "Download the installer above.",
    s2: "Run it. If Windows shows “Windows protected your PC”, click More info, then Run anyway.",
    s3: "Open FQPN's Chat Bot and connect Twitch: enter the short code on Twitch and click Authorize.",
    s4: "Done. The app updates itself when a new version comes out, and your settings always stay.",
    w_t: "Why does Windows warn me?", w_d: "The installer isn't digitally signed yet: an application for free code signing is waiting. The app is open source, and every installer is built on GitHub from the public code.",
    q_t: "Questions",
    q1: "Is it free?", a1: "Yes. It's free and open source (MIT license).",
    q2: "Does the bot work when my PC is off?", a2: "No. It runs on your PC, so it's in your chat while the app is open. It can start with Windows and wait in the tray.",
    q3: "Is my Twitch login safe?", a3: "Your login stays on your PC, in %APPDATA%\\TwitchChatBot. It is never uploaded.",
    q4: "What does the app send?", a4: "Once a day, your Twitch channel name and the app version, so the developers know who uses it. Never your replies, chat, viewers, settings or passwords. For the public command list (on from the start, you can switch it off), the names of your commands and who can use them. And whatever you send from the Support page, when you press Send.",
    q5: "Windows says “An Application Control policy has blocked this file”.", a5: "That's Smart App Control, which blocks programs that aren't signed yet. You can turn it off in Windows Security > App & browser control, or wait until the installer is signed.",
    q6: "How do I update?", a6: "The app finds new versions by itself and offers Restart and update. You can also run the newest installer from this page: it updates in place.",
    l_t: "Public command lists",
    c_t: "How it's different", c_lead: "Compared with Nightbot, StreamElements and WizeBot, which run on their companies' servers.",
    c_us: "FQPN's Chat Bot", c_yes: "Yes", c_no: "No",
    c1: "Where it runs", c1a: "On your PC", c1b: "On their servers",
    c2: "Runs 100% locally", c2a: "yes", c2b: "no",
    c10: "No account required", c10a: "yes", c10b: "no",
    c11: "No subscription", c11a: "yes", c11b: "yes", c11b2: "Paid extras",
    c5: "Free", c5a: "yes", c5b: "yes",
    c7: "Talks as you or your own bot", c7a: "yes", c7b: "no",
    c8: "Chat moderation (filters, blocklist)", c8a: "yes", c8b: "yes",
    c9: "Replies in chat to Twitch events (follows, subs, gift subs, raids, bits)", c9a: "yes", c9b: "yes", c9b0: "no",
    c6: "Works while your PC is off", c6a: "no", c6b: "yes",
    c_note: "Those bots stay in your chat when your PC is off; FQPN's Chat Bot runs while the app is open, which is usually the PC you stream from. By default they talk as their own bot account; some offer a custom bot name. Nightbot, StreamElements and WizeBot belong to their owners, and how they work can change.",
    by: "Made by",
  },
  ar: {
    commands: "الأوامر", count: "{n} أمر", count1: "أمر واحد", count2: "أمران", count_few: "{n} أوامر", search: "ابحث في الأوامر", none: "لا توجد أوامر تطابق بحثك.",
    empty: "لا توجد أوامر عامة لهذه القناة بعد.", copy: "اضغط على أمر لنسخه.", copied: "تم نسخ {c}",
    g_builtin: "الأوامر المدمجة", g_games: "الألعاب", bd_commands: "رابط لهذه الصفحة بكل الأوامر.", bd_title: "يعرض عنوان البث. يغيّره المشرفون بكتابة عنوان جديد بعده.", bd_game: "يعرض اللعبة. يغيّرها المشرفون بكتابة اسم لعبة بعده.", bd_app: "يقول أي برنامج يشغّل هذا البوت.", bd_addcom: "يضيف المشرفون أمرًا جديدًا من الدردشة.", bd_editcom: "يغيّر المشرفون رد أمر من الدردشة.", bd_delcom: "يحذف المشرفون أمرًا من الدردشة.", gd_letters_start: "يبدأ جولة «حروف»: أول من يكتب كلمة من الفئة تبدأ بالحرف المعروض يفوز.", gd_letters_approve: "يقبل المشرفون كلمة لم يعرفها البوت، ويفوز ذلك المشاهد بالجولة.", gd_scramble_start: "يبدأ لعبة «رتّب»: أول من يكتب الكلمة بالترتيب الصحيح يفوز.", gd_shared_wins: "يعرض كم جولة فزت بها.", gd_shared_top: "يرسل رابط لوحة أوائل الألعاب.", gd_emoji_start: "يبدأ «ايموجي»: خمّن الكلمة من الإيموجي؛ أول جواب صحيح يفوز.", gd_reverse_start: "يبدأ «عكس»: كلمة مكتوبة بالعكس؛ أول من يكتبها صح يفوز.", gd_math_start: "يبدأ «احسب»: عملية حسابية سريعة؛ أول جواب صحيح يفوز.", gd_ladder_start: "يبدأ «سلم»: أسرع من يكتب عدة كلمات تبدأ بحرف يفوز.", gd_trivia_start: "يبدأ «سؤال»: سؤال سهل بأربعة خيارات؛ أول جواب صحيح يفوز.", gd_shared_random: "يبدأ جولة من لعبة عشوائية.", bi_who: "مدمج في FQPN's Chat Bot · يستخدمه: {w}", g_everyone: "الجميع", g_subscriber: "المشتركون", g_vip: "VIP", g_moderator: "المشرفون", g_broadcaster: "صاحب القناة",
    updated: "آخر تحديث {t}", made: "صُنعت باستخدام FQPN's Chat Bot", lang: "English",
    home_t: "قوائم الأوامر العامة", home_d: "يمكن لصنّاع المحتوى الذين يستخدمون FQPN's Chat Bot مشاركة أوامر الشات هنا. افتح رابطًا مثل {u} لرؤية قائمة القناة.",
    miss_t: "لا توجد قائمة هنا", miss_d: "لا توجد قائمة أوامر عامة لـ {c}. يمكن لصاحب القناة تفعيلها في FQPN's Chat Bot من صفحة الأوامر.",
    lb_tab: "لوحة صدارة الألعاب", lb_all: "كل الألعاب", wins: "{n} فوز", win1: "فوز واحد", lb_empty: "لا توجد انتصارات بعد.",
    players1: "لاعب واحد", players2: "لاعبان", players_few: "{n} لاعبين", players: "{n} لاعبًا",
    ed_t: "تعديل الأوامر", ed_gone_t: "انتهى رابط التعديل هذا", ed_gone_d: "انتهت مدته، أو أُلغي، أو استُبدل برابط جديد. اطلب من صاحب القناة رابطًا وكلمة مرور جديدين.",
    ed_in_t: "سجّل الدخول للتعديل", ed_in_d: "أعطاك صاحب القناة هذا الرابط وكلمة مرور. يظهر اسمك لصاحب القناة بجانب كل تعديل.",
    ed_name: "اسمك", ed_pw: "كلمة المرور", ed_go: "افتح المحرّر", ed_wrong: "كلمة مرور خاطئة. بقيت {n} محاولات.", ed_locked: "كلمات مرور خاطئة كثيرة: هذا الرابط مقفل. اطلب رابطًا جديدًا من صاحب القناة.",
    ed_need_name: "اكتب اسمك.", ed_net: "لا يمكن الوصول إلى الموقع. حاول مرة أخرى.",
    ed_left_h: "ينتهي الرابط بعد {h} س {m} د", ed_left_m: "ينتهي الرابط بعد {m} د",
    ed_how: "تعديلاتك تذهب إلى تطبيق صاحب القناة، الذي يتحقق منها ويطبّقها خلال ثوانٍ ما دام يعمل (أو حالما يُفتح).",
    ed_add: "إضافة أمر", ed_add_t: "أمر جديد", ed_edit_t: "تعديل {n}", ed_cmd: "الأمر", ed_resp: "الرد", ed_who: "من يستطيع استخدامه", ed_cd: "الانتظار بين الاستخدامات (ثوانٍ)",
    ed_al: "أسماء إضافية (افصل بينها بفواصل)", ed_on: "مفعّل", ed_save: "أرسل التعديل", ed_cancel: "إلغاء", ed_edit: "تعديل", ed_del: "حذف",
    ed_del_q: "حذف {n}؟", ed_sent: "أُرسل: يطبّقه التطبيق خلال ثوانٍ", ed_cd_s: "{n} ث", ed_offl: "متوقف", ed_locked_cmd: "يُعدَّل من التطبيق",
    ed_empty: "لا توجد أوامر بعد. أضف أول أمر.", ed_recent: "تعديلاتك", ed_no_recent: "لم يتغير شيء بعد.",
    ed_st_wait: "بانتظار التطبيق", ed_st_ok: "طُبّق", ed_st_bad: "رُفض", ed_op_set: "حُفظ", ed_op_del: "حُذف",
    miss_d0: "هذه الصفحة غير موجودة.",
    h_title: "بوت شات وإشراف لتويتش", h_lead: "أوامر ومؤقتات وترحيب وردود على أحداث تويتش وإشراف على الشات وألعاب، كلها تُضبط من تطبيق بالعربي والإنجليزي. مجاني.",
    dl: "تحميل لويندوز", dl_users: "ستريمر يستخدمونه", dl_meta: "الإصدار {v} · {d} · {s} ميغابايت", dl_down: "احصل على أحدث إصدار من GitHub", dl_req: "ويندوز 10 أو 11 · يُثبَّت لحسابك فقط، بدون صلاحيات المسؤول",
    dl_all: "كل الإصدارات وما تغيّر فيها",
    f_t: "ماذا يفعل",
    f1_t: "الأوامر", f1_d: "بأسماء بديلة ومستويات للمستخدمين وفترات انتظار ومتغيرات مثل \\u2066$(user)\\u2069 و\\u2066$(followage)\\u2069 و\\u2066$(weather city)\\u2069 و\\u2066$(accountage)\\u2069.",
    f2_t: "المؤقتات", f2_d: "رسائل بجدول زمني أثناء البث، مثل تذكير بالمتابعة أو بالانضمام للديسكورد.",
    f3_t: "أحداث تويتش", f3_d: "ردود على المتابعة والاشتراكات والإهداءات والغارات وقطار الحماس والـ Bits وسلاسل المشاهدة والتبرعات، مع المجموع.",
    f4_t: "التحيات", f4_d: "ترحيب بمن تختارهم، مرة في كل بث، بكلماتك.",
    f5_t: "قائمة الحظر", f5_d: "أشخاص يتجاهلهم البوت: لا رد على أوامرهم.",
    f6_t: "الإشراف", f6_d: "فلاتر للكلمات السيئة بالعربية والإنجليزية والروابط والأحرف الكبيرة والإيموجي والرموز والسبام، وسجل لما حدث.",
    f7_t: "الألعاب", f7_d: "خمس ألعاب: «حروف» و«رتب» و«ايموجي» و«عكس» و«احسب»، و«لعبه؟» للعبة عشوائية، مع لوحة الأوائل.",
    f8_t: "تجربة الدردشة", f8_d: "جرّب كل أمر ولعبة ورد حدث كأي مشاهد، بدون تويتش. مع وصفات أوامر جاهزة.",
    f9_t: "السحوبات", f9_d: "اسحب أحد المتفاعلين، أو دع المشاهدين يشاركون بكلمة، أو يخمّنون رقمًا. حظ للمشتركين وإعادة السحب.",
    f10_t: "قائمة الأوامر العامة", f10_d: "رابط واحد لصفحة فيها كل أوامرك، ومثال على ما يقوله كل أمر، ولوحة أوائل الألعاب.",
    f11_t: "رابط التعديل", f11_d: "اسمح لشخص تثق به بتعديل أوامرك من الموقع، برابط وكلمة مرور لمرة واحدة.",
    f12_t: "العربية والإنجليزية", f12_d: "التطبيق كله باللغتين، من اليمين لليسار بالعربية، بالوضع الداكن والفاتح.",
    s_t: "التثبيت في دقيقة",
    s1: "حمّل المثبّت من الأعلى.",
    s2: "شغّله. إذا ظهرت رسالة «Windows protected your PC» فاضغط More info ثم Run anyway.",
    s3: "افتح FQPN's Chat Bot واربط تويتش: اكتب الرمز القصير في تويتش واضغط Authorize.",
    s4: "انتهيت. التطبيق يحدّث نفسه عند صدور إصدار جديد، وإعداداتك تبقى دائمًا.",
    w_t: "لماذا يحذّرني ويندوز؟", w_d: "المثبّت غير موقّع رقميًا بعد: طلب التوقيع المجاني قيد الانتظار. التطبيق مفتوح المصدر، وكل مثبّت يُبنى على GitHub من الكود العام.",
    q_t: "أسئلة",
    q1: "هل هو مجاني؟", a1: "نعم. مجاني ومفتوح المصدر (رخصة MIT).",
    q2: "هل يعمل البوت وجهازي مطفأ؟", a2: "لا. يعمل على جهازك، فيكون في الشات ما دام التطبيق مفتوحًا. يمكن أن يبدأ مع ويندوز وينتظر في شريط المهام.",
    q3: "هل تسجيل دخولي في تويتش آمن؟", a3: "تسجيل دخولك يبقى على جهازك في \u2066%APPDATA%\\TwitchChatBot\u2069 ولا يُرفع أبدًا.",
    q4: "ماذا يرسل التطبيق؟", a4: "مرة في اليوم: اسم قناتك في تويتش ورقم إصدار التطبيق، ليعرف المطوّرون من يستخدمه. أبدًا ليس ردود أوامرك أو الشات أو المشاهدين أو الإعدادات أو كلمات المرور. ولقائمة الأوامر العامة (مفعّلة من البداية ويمكنك إيقافها): أسماء أوامرك ومن يمكنه استخدامها. وما ترسله من صفحة الدعم عندما تضغط إرسال.",
    q5: "ويندوز يقول «An Application Control policy has blocked this file».", a5: "هذا Smart App Control، ويمنع البرامج غير الموقّعة بعد. يمكنك إيقافه من Windows Security > App & browser control، أو الانتظار حتى يُوقَّع المثبّت.",
    q6: "كيف أحدّث التطبيق؟", a6: "التطبيق يجد الإصدارات الجديدة بنفسه ويعرض «إعادة التشغيل والتحديث». ويمكنك أيضًا تشغيل أحدث مثبّت من هذه الصفحة: يحدّث التطبيق في مكانه.",
    l_t: "قوائم الأوامر العامة",
    c_t: "ما الذي يميّزه", c_lead: "مقارنة بـ Nightbot وStreamElements وWizeBot، وهي تعمل على خوادم شركاتها.",
    c_us: "FQPN's Chat Bot", c_yes: "نعم", c_no: "لا",
    c1: "أين يعمل", c1a: "على جهازك", c1b: "على خوادمهم",
    c2: "يعمل محليًا 100%", c2a: "yes", c2b: "no",
    c10: "بدون إنشاء حساب", c10a: "yes", c10b: "no",
    c11: "بدون اشتراك", c11a: "yes", c11b: "yes", c11b2: "مزايا مدفوعة",
    c5: "مجاني", c5a: "yes", c5b: "yes",
    c7: "يكتب باسمك أو باسم بوتك", c7a: "yes", c7b: "no",
    c8: "الإشراف على الشات (فلاتر، قائمة حظر)", c8a: "yes", c8b: "yes",
    c9: "يرد في الشات على أحداث تويتش (المتابعة، الاشتراكات، الهدايا، الغارات، البيتس)", c9a: "yes", c9b: "yes", c9b0: "no",
    c6: "يعمل وجهازك مطفأ", c6a: "no", c6b: "yes",
    c_note: "تلك البوتات تبقى في الشات وجهازك مطفأ، أما FQPN's Chat Bot فيعمل ما دام التطبيق مفتوحًا، وهو غالبًا الجهاز الذي تبث منه. وهي تكتب افتراضيًا باسم حسابها الخاص، وبعضها يتيح اسم بوت مخصصًا. Nightbot وStreamElements وWizeBot ملك لأصحابها، وطريقة عملها قد تتغير.",
    by: "من صنع",
  },
};

const ICONS = {   // small line icons for the feature cards (inline SVG: nothing extra to load)
  f1: '<path d="M4 17l6-6-6-6M12 19h8"/>', f2: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  f3: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
  f4: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  f5: '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
  f6: '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
  f7: '<rect x="2.5" y="7" width="19" height="11" rx="5"/><path d="M7.5 10.5v4M5.5 12.5h4M15.5 11.5h.01M17.5 13.5h.01"/>',
  f8: '<path d="M4 5h16v11H9l-5 4z"/><path d="m10 8.5 4 2-4 2z"/>',
  f9: '<rect x="3.5" y="9" width="17" height="11.5" rx="1.5"/><path d="M2.5 9h19v-3h-19zM12 6v14.5"/>',
  f10: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  f11: '<path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>',
  f12: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 3.7 5.7 3.7 9s-1.2 6.3-3.7 9c-2.5-2.7-3.7-5.7-3.7-9S9.5 5.7 12 3z"/>',
};
const T = (k) => esc(TEXT.en[k]);
const BOTS = ["Nightbot", "StreamElements", "WizeBot"];     // the comparison's columns (names only: nothing loaded from them)
function cell(v, key, us) {         // "yes" / "no" -> a mark and the word; anything else is a text
  const cls = us ? ' class="us"' : "";
  if (v === "yes" || v === "no") return `<td${cls}><span class="mk ${v}" aria-hidden="true">${v === "yes" ? "✓" : "✗"}</span> <span data-t="c_${v}">${T("c_" + v)}</span></td>`;
  return `<td${cls} data-t="${key}">${T(key)}</td>`;
}

// 1.14.0: how many channels use the app (the ones it has heard from, banned ones left out), next to the Download button
async function userCount(env) {
  try {
    await setup(env.DB);
    const r = await env.DB.prepare("SELECT COUNT(*) AS n FROM seen s WHERE NOT EXISTS (SELECT 1 FROM bans b WHERE b.user_id = s.user_id)").first();
    return Number((r && r.n) || 0);
  } catch (e) {
    return 0;
  }
}

function homeBody(origin, rel, users = 0) {
  const meta = rel ? `<p class="dlmeta" data-t="dl_meta" data-v="${esc(rel.version)}" data-d="${rel.date}" data-s="${(rel.size / 1048576).toFixed(1)}" dir="auto">${
    esc(TEXT.en.dl_meta.replace("{v}", rel.version).replace("{d}", new Date(rel.date * 1000).toISOString().slice(0, 10)).replace("{s}", (rel.size / 1048576).toFixed(1)))}</p>`
    : `<p class="dlmeta" data-t="dl_down">${T("dl_down")}</p>`;
  const icon = (k) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[k]}</svg>`;
  const feats = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((n) => `<div class="feat">${icon("f" + n)}<h3 data-t="f${n}_t">${T("f" + n + "_t")}</h3><p data-t="f${n}_d">${T("f" + n + "_d")}</p></div>`).join("");
  const steps = [1, 2, 3, 4].map((n) => `<li><span class="num" aria-hidden="true">${n}</span><span data-t="s${n}">${T("s" + n)}</span></li>`).join("");
  const faq = [1, 2, 3, 4, 5, 6].map((n) => `<details><summary data-t="q${n}">${T("q" + n)}</summary><p data-t="a${n}">${T("a" + n)}</p></details>`).join("");
  return `<header class="top"><div class="who"><img class="logo" src="${LOGO}" alt="" width="48" height="48"><div><b class="brand">FQPN's Chat Bot</b></div></div>${langBtn()}</header>
<section class="hero">
<h1 data-t="h_title">${T("h_title")}</h1>
<p class="lead" data-t="h_lead">${T("h_lead")}</p>
<div class="dlbox"><div class="dlrow"><a class="dl" id="dl" href="/download/windows"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5M4 20h16"/></svg><span data-t="dl">${T("dl")}</span></a>${users >= 2 ? `<span class="dlusers"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5"/><path d="M15.5 4.8a3.5 3.5 0 0 1 0 6.4M18 14.8c1.9.8 3.1 2.6 3.5 5.2"/></svg><b>${users}</b> <span data-t="dl_users">${T("dl_users")}</span></span>` : ""}</div>
${meta}<p class="req" data-t="dl_req">${T("dl_req")}</p><p class="req"><a href="${esc(rel ? rel.notes : RELEASES)}" rel="noopener" data-t="dl_all">${T("dl_all")}</a></p></div>
</section>
<section><h2 data-t="f_t">${T("f_t")}</h2><div class="feats">${feats}</div></section>
<section><h2 data-t="c_t">${T("c_t")}</h2><p class="lead small" data-t="c_lead">${T("c_lead")}</p>
<div class="cmpwrap"><table class="cmp"><thead><tr><th></th><th class="us" data-t="c_us">${T("c_us")}</th>${BOTS.map((b) => `<th>${b}</th>`).join("")}</tr></thead><tbody>${
  [1, 2, 10, 11, 7, 9, 8, 5, 6].map((n) => `<tr${n === 6 ? ' class="con"' : ""}><th scope="row" data-t="c${n}">${T("c" + n)}</th>${cell(TEXT.en["c" + n + "a"], "c" + n + "a", true)}${
    BOTS.map((_, i) => { const k = TEXT.en["c" + n + "b" + i] !== undefined ? "c" + n + "b" + i : "c" + n + "b"; return cell(TEXT.en[k], k, false); }).join("")}</tr>`).join("")
}</tbody></table></div>
<p class="cmpnote" data-t="c_note">${T("c_note")}</p></section>
<section><h2 data-t="s_t">${T("s_t")}</h2><ol class="steps">${steps}</ol>
<div class="note"><b data-t="w_t">${T("w_t")}</b><p data-t="w_d">${T("w_d")}</p></div></section>
<section><h2 data-t="q_t">${T("q_t")}</h2><div class="faq">${faq}</div></section>
<section><h2 data-t="l_t">${T("l_t")}</h2><p class="lead small" data-t="home_d" data-u="${esc(origin)}/fqpn_">${esc(TEXT.en.home_d.replace("{u}", origin + "/fqpn_"))}</p></section>
<footer class="foot"><span><span data-t="by">${T("by")}</span> <a href="https://www.twitch.tv/fqpn_" rel="noopener">FQPN_</a> &amp; <a href="https://www.twitch.tv/1asoom" rel="noopener">1asoom</a></span></footer>`;
}

function missingBody(login) {
  return `<header class="top"><div class="who"><div class="mark" aria-hidden="true"></div><div><h1 data-t="miss_t">${esc(TEXT.en.miss_t)}</h1></div></div>${langBtn()}</header>
<p class="lead" data-t="${login ? "miss_d" : "miss_d0"}" data-c="${esc(login)}">${esc(login ? TEXT.en.miss_d.replace("{c}", login) : TEXT.en.miss_d0)}</p>
<footer class="foot"><span data-t="made">${esc(TEXT.en.made)}</span></footer>`;
}

function listBody(view) {
  const avatar = view.avatar ? `<img class="av" src="${esc(view.avatar)}" alt="" width="56" height="56">` : `<div class="av mark" aria-hidden="true"></div>`;
  const tw = "https://www.twitch.tv/" + esc(view.login);       // 1.12.0: the name and the picture open the channel on Twitch
  return `<header class="top"><div class="who">${avatar}<div><h1><a class="chname" href="${tw}" target="_blank" rel="noopener"><bdi>${esc(view.display)}</bdi></a></h1><p class="meta" id="count"></p></div></div>${langBtn()}</header>
${view.leaderboard ? `<nav class="tabs" id="tabs"><button type="button" class="tab on" data-tab="cmds" data-t="commands">${esc(TEXT.en.commands)}</button><button type="button" class="tab" data-tab="lb" data-t="lb_tab">${esc(TEXT.en.lb_tab)}</button></nav>` : ""}
<div id="pane-cmds"><div class="searchbox"><input id="q" type="search" autocomplete="off" spellcheck="false" dir="auto" data-ph="search" aria-label="${esc(TEXT.en.search)}" placeholder="${esc(TEXT.en.search)}"></div>
<p class="hint" data-t="copy">${esc(TEXT.en.copy)}</p>
<div id="groups"></div>
<p class="empty" id="none" hidden></p></div>
${view.leaderboard ? `<div id="pane-lb" hidden><div class="subtabs"><button type="button" class="sub-tab on" data-sub="all" data-t="lb_all">${esc(TEXT.en.lb_all)}</button><button type="button" class="sub-tab" data-sub="l">حروف</button><button type="button" class="sub-tab" data-sub="u">رتب</button><button type="button" class="sub-tab" data-sub="e">ايموجي</button><button type="button" class="sub-tab" data-sub="r">عكس</button><button type="button" class="sub-tab" data-sub="m">احسب</button><button type="button" class="sub-tab" data-sub="s">سلم</button><button type="button" class="sub-tab" data-sub="q">سؤال</button></div><div class="lb" id="lbrows"></div></div>` : ""}
<footer class="foot"><span id="updated"></span><span data-t="made">${esc(TEXT.en.made)}</span></footer>
<div class="toast" id="toast" role="status" aria-live="polite"></div>`;
}

function langBtn() {
  return `<button class="lang" id="lang" type="button" lang="ar">${TEXT.en.lang}</button>`;
}

const CSS = `
:root{--glow1:rgba(200,24,36,.42);--glow2:rgba(163,18,26,.24);--pat:url("data:image/png;base64,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");--red:#7d0b0f;--red2:#a3121a;--bg:#0b0b0c;--panel:#101011;--line:#222224;--text:#f2f2f2;--mute:#9b9ba1;--soft:#cfcfd4;--chip:#161618;--ok:#3fb871}
@media (prefers-color-scheme:light){:root{--glow1:rgba(200,24,36,.16);--glow2:rgba(163,18,26,.09);--pat:url("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAQQAAAEECAYAAADOCEoKAAAQ90lEQVR42u3d227buBqG4Y+UZGd7EoIgDAjoybr/K5qTAAZSDUcLKDDdxRK5DiS5SjrTKKt2E6fvAxQoEExje8xPP3+SkgQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIDXy/ARvBg7fv5ZUuLjwGv5UuLXKiStJK03m816/HvF/wvg91NK786891fe+ytJVyGES0mXktZjWABMGX6Tz3odQihSaozkZa3NTdMY770kKcb4VdKOjwpMGX6Pz9oOA38IgJSS8X4IhpSSGSoIQhoEwm9RIYQQzBACD3/QNI0pyzLVdU3VBgLhF5XrZny/xUu9b2ttjvHff77dbrOGVQfgRbz1JpbV0MVfhRBWHz9+rCSVm82mdM4VHz58MLOwOPZAtH//fV14n/YVQIzS9bXNFxcX5s8//5SkTlLP1xIveeV8s0HgvS9TSsZam6d5et/31pj/Zmt9nq7a1tq8Wq3S7e1tr2FPwKH3BtjNRmcpBTM1Ea21WZK6rrFlGVLTNJ2GhiJ7EkAgHFDpvT9LKZm2bbP3XjHG7L3fB8PdXTLOdTbnbCTJGJOnAXqEgCgknTnnbFmWaewZdMNnXxupyNJtP1YGhAEIhANPgc6cc7ZtWznn1LbtP115x45/XUhbI8k4544REKWklXOuGPoHMUm6H6cG86kKfQMQCEdwHkKw4xLeknX9ebNxajgeKiBWIYQqpWRSSubq6mp3e3t7TxUAAuEXTRWcc+fjlViS/p9NPosCQpKKokj/EhBZUuGcW00hEmPcja8HIBCOyM7K7bObm5uqKIoUY+wkfTnQ57MoIKYqYrbJSOMUYSd2H+JUrqonHATl8OddGpty1hgzhUN3oN+TH00H9gHRtu13AdH30cbocghl6rrOamgUEgYgEI6oklR5721KyaxW97q704P5/RHn6T8MiM1mU3rf2ZSSGVcUSrG3ADiaQtK5c+5a0pWky7quzyWdee+nk4PnL1y5VBpOL1557682m82F2I6MExpgJ1XRhBBKSbq8vNT19bVWq1W6vr4279+/txcXF+bTp08veUWeqofsnKv++usvrddr+/nz50yVgFOZi5/c6x1XEWStzVVV5b7v90eIF04X7JHfe9e27c45Z8YpTEWVAALhwK+1rms7HRmem7r6C/oHVtKqruv1OLWojvh6v7ZtmyTp5uamEDc/AYFw2Nfa9/3sYJDNRVHk3W5npvMKTdOkHwSCkVSFEKqvX78WzjkrhdURQyHXdZ2kYUlSHDUHgXBQZqoEJCkEabstct/3JsZ9lfCjebrdbDZFSsnEGNW2ZfK+MdK74ljl/Ha7TbMVB6YMIBAO+VqbZjgy/G16UOXttp/fcOSH04UpUIYpRzLWhizdPuccQanhOPXS5do8n9IABMKBqgOpttL3dxuSFvcPHgzK2b+z5HBRIekshLB2zq3HacaSnoCd7VzkABMIhAMW4HIuzY4wF1naGe8X9w/+7b0+tSphNJyTqJqmMW3bphDCtFPSPvHfFbOwmj5vegl4tU5lp2KW1Ftri6ZpTAjK0rssDU3GBf2DYrPZ2K7rHlQJVVWlBVduM13pQwjzKUChH2+RHhuXMcc4/Y7NmbRKEqceQSD8rC7GWDjnSqnM0u1sGuAX9w9mtXzebrdpYYVgHvYCoqQ6S9v8VPU13GG5zNLKOndbWOvtGBD3TCPAlOH/lyTdn5+fd02zv7Lvn2/w1MCeVheGQbq4f2Ck/5Te+0efk5d09lR1UVhrs/dSXRe5rnvTtj7HGDXutiz5+oEK4ef02+12uq9A5Zyz1tr0RP9AklJZlsl7b6212bnGNk1YcgjKSDszVATfupAx2iz98aNAeNCzKIoif/nypfBesjZMTUZ6CaBCOFCl8Hhd/6lzAunu7q6P0eaUGjPcYLVZcubBSLd2Hgbjx/ZUmIz9g28NxWm6MZu6MF0AFcLB02HZkt54o5JrxdhIis85ALVf1vw2mIunphp23qt4/MPxxik0FUGFcNA0K8s0DtIlG3+S9Me9hmbe4jDw3psYo4ZNUTYP04cnA6GYgqAoht2Uj37OjVVBIBy6OGiaxlprc13XSw8OPXcg9jHG3jlnvE/G+2SGFYLb7jn9g91uZwkEMGU4rt45pxjjdHDIHqEMz5Lu27Ydq5A6adh7sGD/gfLj/sGjKQyBAALhkIHQtm3vnCskqW3bM0mfjvF7tL9j8nbJysTS/gGBAKYMB3Y/bWUe9wqcH+k9PefJSnZ6qOu8fzALB6YLIBCOpBufeSBJ8t4Xks40HD56ife2P7/gfdR2O/QPYrS5aZr5ciMrDHiVzBt5D+tp+uOcM+MUopP0+VdPwWYPi8mSOu99Nd0TYdxA9ZxVDoAewjNlDQ9lWYUQqqZpxvsdfDfojL6dUJzK/0NfqeerHUlSijFOr6MTD3QFgfDL9E3TVDc3N3Z8clM3G6SV976MMU5hUc2OTM/DIf3kZ1nONjBND2np6RuAQHiZqYMZ71/Yj5XAKoRQdF1nxxLepJT2uw7HnsP+ngU/ERB2s9msUkpqmkYhhDQLJCoC0EN4AWvn3Gq8f6GapjHee003YJWk9Xrdj0eerST7+LzBgxG+PCBW3vtVjNF473/mQbMAgXDA93HmnCvbtk3e+/1BorGZ140DdD6g5w9wfU5A7B/jFkKYbtpqvPc86RkEwithx0DYl//jBqApCPLCf2NRQPR9b4uiSGNIWOecJKlt23vCAATCyyskXTrn8rjcON2iLP9kyPxjQEyHqmYVSD/7nQCB8AreRzVWBMcalFNAzE9XTj0GVhAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA4AQZPgLgRdlxHGZJ6TW8GAC/XiFpJWm92WzW498rxiTw+ymld2fe+yvv/ZWkqxDCpaRLSesxLJgyAL/JNH0dQihSaozkZa3NTdMY770kKcb4VdKOKQPwe/QM7DDwhwBIKRnvh2BIKZmhgniZizWBAPziCiGEYIYQePiDpmlMWZaprmsRCMCvKdfN+L0vXur7b63NMf77z7fbbdaw6vDLFXxH8JuU6StJqxDC6uPHj5WkcrPZlM654sOHD2YWFsceiPbvv68L79O+AohRur62+eLiwvz555+S1EnqXyoxgTcdBN77MqVkrLV5mqf3fW+N+W+21ufpqm2tzavVKt3e3vYa9gQcem+A3Wx0llIwUxPRWpslqesaW5YhNU3TaWgoJgIBOJzSe3+WUjJt22bvvWKM2Xu/D4a7u2Sc62zO2UiSMSZPA/QIAVFIOnPO2bIs09gz6IYxWBupyNJtP1YGL7ZBiUDAW7QffG3byjmntm3/6co7dvzrQtoaScY5d4yAKCWtnHPF0D+ISdL9ODWYT1XyS39wBALeovMQgh2X8Jas68+bjVPD8VABsQohVCklk1IyV1dXu9vb23u9gm3KBAJ+i6mCc+58vBJL0v+zyWdRQEhSURTpXwIiSyqcc6spRGKMu/H1vFoEAt4COyu3z25ubqqiKFKMsZP05UDjZFFATFXEbJORxinCTi+0+/BZacp3CSceBOXw510am3LWGDOFQ3eg35MfTQf2AdG27XcB0ffRxuhyCGXqus5qaBTuTuEDJRBwqipJlffeppTManWvuzs9mN8fcZ7+w4DYbDal951NKZlxRaHUC+4tAN66QtK5c+5a0pWky7quzyWdee+nk4PnL1y5VBpOL1557682m83FKUzR2amIU1SGEEpJury81PX1tVarVbq+vjbv37+3FxcX5tOnTy95RZ6qh+ycq/766y+t12v7+fPn/NqrBM4y4FR7BxpXEWStzVVV5b7v90eIF04X7JHHQNe27c45Z8YpTPXaqwQCAScXBnVd2+nI8NzU1V/QP7CSVnVdr8epRXXE1/u1bdskSTc3N8Vrr8oJBJxcIPR9PzsYZHNRFHm325npvELTNOkHgWAkVSGE6uvXr4VzzkphdcRQyHVdJ2lYknztY45AwKkxUyUgSSFI222R+743Me6rhB/N0+1msylSSibGqLYtk/eNkd4Vxyrnt9ttmq04MGUADvmdbZrhyPC36UGVt9t+fsORH04XpkAZphzJWBuydPuccwSlhuPUS5ft83xKQyAAB6oOpNpK399tSFrcP3gwKGf/zpLDRYWksxDC2jm3HqcZS3oCdrZzMRMIwOEKcDmXZkeYiyztjPeL+wf/9p1/alXCaDgnUTVNY9q2TSGEaaekfeK/K2ZhNY27Vzn22KmIU5Il9dbaomkaE4Ky9C5LQ5NxQf+g2Gw2tuu6B1VCVVVpwZXbTFf6EMJ8ClDox1ukx8ZlzDFOv2NzJq2S9PpOPRIIODVdjLFwzpVSmaXb2TTAL+4fzGr5vN1u08IKwTzsBURJdZa2+akqfLjDcpmllXXutrDW2zEg7l/TNIIpA05NknR/fn7eNc3+yr5/vsFTA3taXRgG6eL+gZH+U3rvH40XL+nsqeqisNZm76W6LnJd96ZtfY4xatxt+aouylQIOEX9drud7itQOeestTY90T+QpFSWZfLeW2ttdq6xTROWHIIy0s4MFcG3LmSMNkt//CgQHvQsiqLIX758KbyXrA1Tk/FVXZSpEHDKlcLjdf2nzgmku7u7PkabU2rMcIPVZsmZByPd2nkYjMPnqTAZ+wffGorTdGM2dXlVqw5UCHgb6bBsSW+8Ucm1YmwkxeccgNova34bzMVTUw0771U8/uF445RX1VSkQsDJK8syjYN0ycafJP1xr6GZtzgMvPcmxqhhU5TNw/ThyUAopiAoimE35aOfv4obqxIIeFPFQdM01lqb67peenDouQOxjzH2zjnjfTLeJzOsENx2z+kf7HY7+9oDgSkDTl3vnFOMcTo4ZI9QhmdJ923bjlVInTTsPViw/0D5cf/g0RSGQAAOGQht2/bOuUKS2rY9k/TpGL9H+zsmb5esTCztHzBlAA7sftrKPO4VOD/Sd/s5T1ay00Nd5/2DWTi8uukCgYC3ohufeSBJ8t4Xks40HD56ie/4/vyC91Hb7dA/iNHmpmnmy42v7mEtPJcBb4WRtJ6mwc45M04hOkmff/VUfPawmCyp895X0z0Rxg1Uz1nloIcAPFPW8FCWVQihappmvN/Bd4PO6NsJxan8P/SVer7akSSlGOP0Ojq98ANdCQT8Tvqmaaqbmxs7Prmpmw3SyntfxhinsKhmR6bn4ZB+ckyVsw1M00Na+tfaNyAQ8NanDma8f2E/VgKrEELRdZ0dS3iTUtrvOhx7Dvt7FvxEQNjNZrNKKalpGoUQ0iyQ0ql8eMBbsnbOrcb7F6ppGuO913QDVklar9f9eOTZSrKPzxs8GOHLA2LlvV/FGI33/mceNEsgAAf8Pp8558q2bZP3fn+QaGzmdeMAnQ/o+QNcnxMQ+8e4hRCmm7Ya7/3JPOmZQMBbZ8dA2Jf/4wagKQjywn9jUUD0fW+LokhjSFjnnCSpbdv7UwwDAgFvTSHp0jmXx+XG6RZl+SdD5h8DYjpUNatA+tnvFIEAvPz3uRorgmMNyikg5qcrpx5D5n8BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAvvc/h/bJVp2P0AQAAAAASUVORK5CYII=");--bg:#f4f4f6;--panel:#fff;--line:#e2e2e7;--text:#17171a;--mute:#6b6b73;--soft:#44444a;--chip:#f7f7f9}}
*{box-sizing:border-box}
html{background:var(--bg);color:var(--text);font:16px/1.5 'Outfit','Tajawal',system-ui,sans-serif;-webkit-text-size-adjust:100%}
body{margin:0;min-height:100vh;background:radial-gradient(1100px 560px at 82% -90px,var(--glow1),transparent 64%),radial-gradient(900px 480px at 8% -110px,var(--glow2),transparent 62%),var(--pat) 0 0/260px 260px repeat,var(--bg)}   /* red glow at the top (1.12.0: stronger, both sides; in px from the top, so a long page shows it too) + the app icon as a faint pattern */
[dir=rtl] body,[dir=rtl] html{font-family:'Tajawal','Outfit',system-ui,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:max(28px,env(safe-area-inset-top)) 20px max(40px,env(safe-area-inset-bottom))}
.top{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:22px}
.who{display:flex;align-items:center;gap:14px;min-width:0}
.av{width:56px;height:56px;border-radius:50%;flex:none;border:2px solid var(--red2);object-fit:cover;background:var(--panel)}
.mark{width:44px;height:44px;border-radius:12px;flex:none;background:var(--red2);box-shadow:0 0 22px -6px var(--red2)}
.av.mark{border-radius:50%;width:56px;height:56px}
h1{margin:0;font-size:28px;font-weight:600;line-height:1.2;overflow-wrap:anywhere}
h1 .sub{color:var(--mute);font-weight:500}
.meta{margin:2px 0 0;color:var(--mute);font-size:15px}
.lead{color:var(--soft);font-size:17px;max-width:680px;overflow-wrap:anywhere}
.lang{background:none;border:1px solid var(--line);color:var(--soft);padding:8px 14px;border-radius:8px;font:500 15px 'Tajawal','Outfit',sans-serif;cursor:pointer}
.lang:hover,.lang:focus-visible{border-color:var(--red2);color:var(--text)}
.searchbox input{width:100%;border:1px solid var(--line);background:var(--panel);color:var(--text);padding:12px 16px;border-radius:10px;font:16px 'Outfit','Tajawal',sans-serif}
.searchbox input:focus{outline:none;border-color:var(--red2);box-shadow:0 0 0 3px color-mix(in srgb,var(--red2) 25%,transparent)}
.hint{color:var(--mute);font-size:14px;margin:10px 2px 18px}
.group{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:14px}
.group h2{margin:0 0 12px;font-size:15px;font-weight:600;color:var(--soft);display:flex;align-items:center;gap:8px}
.group h2 .n{color:var(--mute);font-weight:500}
.group h2::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--red2)}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{border:1px solid var(--line);background:var(--chip);color:var(--text);padding:7px 12px;border-radius:8px;font:500 15px 'Outfit','Tajawal',system-ui,sans-serif;cursor:pointer;max-width:100%;overflow-wrap:anywhere;text-align:start}
.chip:hover,.chip:focus-visible{border-color:var(--red2);outline:none}
.empty{color:var(--mute);text-align:center;padding:30px 0}
.foot{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;color:var(--mute);font-size:13px;margin-top:28px;padding-top:14px;border-top:1px solid var(--line)}
.toast{position:fixed;left:50%;bottom:max(24px,env(safe-area-inset-bottom));transform:translate(-50%,20px);background:var(--red2);color:#fff;padding:10px 18px;border-radius:8px;font-size:15px;opacity:0;pointer-events:none;transition:opacity .2s,transform .2s;max-width:calc(100% - 40px);overflow-wrap:anywhere}
.toast.show{opacity:1;transform:translate(-50%,0)}
@media (prefers-reduced-motion:reduce){.toast{transition:none}}
.adm-login{max-width:420px}.adm-login label{display:block;color:var(--soft);margin-bottom:6px}
.adm-row{display:flex;gap:8px}.adm-row input{flex:1;min-width:0;border:1px solid var(--line);background:var(--panel);color:var(--text);padding:10px 14px;border-radius:8px;font:16px 'Outfit',sans-serif}
.adm-totals{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}.adm-totals div{flex:1 1 150px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.adm-totals b{display:block;font-size:28px;font-weight:600}.adm-totals span{color:var(--mute);font-size:14px}
.adm-wrap{overflow-x:auto;margin-top:14px;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
table.adm{width:100%;border-collapse:collapse;font-size:15px}.adm th,.adm td{text-align:start;padding:10px 14px;border-bottom:1px solid var(--line);white-space:nowrap}
.adm th{color:var(--mute);font-weight:500;font-size:13px}.adm tr:last-child td{border-bottom:0}.adm a{color:var(--text);text-decoration:none;font-weight:600}.adm a:hover{color:var(--red2);text-decoration:underline}
#err{color:#e5484d}
/* the editor page (1.13.0) */
.sub2{font-weight:500;color:var(--mute)}
.edlogin,.edform{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;display:flex;flex-direction:column;gap:8px;margin:18px 0;max-width:620px}
.edlogin h2,.edform h2,.edh{margin:0 0 4px;font-size:19px}
.edh{margin-top:26px}
.edlogin label,.edform label{font-size:14px;font-weight:600;color:var(--soft);margin-top:6px}
.edlogin input,.edform input,.edform textarea,.edform select,#q{background:var(--bg);border:1px solid var(--line);border-radius:10px;color:var(--text);font:inherit;font-size:15px;padding:10px 12px}
.edform textarea{resize:vertical;line-height:1.5}
.edlogin input:focus,.edform input:focus,.edform textarea:focus,.edform select:focus{outline:none;border-color:var(--red2)}
.edbtn{background:var(--red2);color:#fff;border:0;border-radius:10px;padding:10px 16px;font:inherit;font-weight:600;cursor:pointer;align-self:flex-start}
.edbtn.ghost{background:var(--panel2,var(--panel));color:var(--text);border:1px solid var(--line)}
.edbtn.sm{padding:6px 10px;font-size:13px}
.edbtn.danger{color:#e5484d}
.edbtn:focus-visible{outline:2px solid var(--text);outline-offset:2px}
.ederr{color:#e5484d;margin:4px 0 0;font-size:14px}
.ednote{color:var(--mute);font-size:14px}
.edbar{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
.edbar #q{flex:1;min-width:200px}
.edrow{display:flex;gap:12px;flex-wrap:wrap}.edrow>div{display:flex;flex-direction:column;gap:6px;flex:1;min-width:160px}.edrow.end{justify-content:flex-end;margin-top:8px}
.edcount{align-self:flex-end;color:var(--mute);font-size:12px}.edcount.over{color:#e5484d}
.edcheck{display:flex!important;align-items:center;gap:8px;font-weight:500!important}
.edlist{display:flex;flex-direction:column;gap:10px}
.edcmd{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.edcmd.off{opacity:.65}
.edtop{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.edname{font-weight:600;font-size:16px}
.edmeta{color:var(--mute);font-size:13px;flex:1;min-width:0}
.edbtns{display:flex;gap:6px}
.edlock{font-size:12px;color:var(--mute);border:1px dashed var(--line);border-radius:999px;padding:2px 8px}
.edresp{margin:6px 0 0;color:var(--soft);font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}
.edrecent{display:flex;flex-direction:column;gap:6px}
.edch{display:flex;align-items:center;gap:8px;font-size:14px;color:var(--soft)}
.edch>span:nth-child(2){flex:1;min-width:0}
.edot{width:8px;height:8px;border-radius:50%;flex:none;background:var(--mute)}.edot.ok{background:#2fbf71}.edot.wait{background:#f5b850}.edot.bad{background:#e5484d}
.edst.ok{color:#2fbf71}.edst.wait{color:#f5b850}.edst.bad{color:#e5484d}
.group.builtin h2{color:var(--soft)}
.chip small{font-size:11px;color:var(--mute);margin-inline-start:6px}
.chip.has-ex{display:inline-flex;flex-direction:column;align-items:flex-start;gap:3px;max-width:min(100%,420px)}
.chip .ct{display:inline-flex;align-items:baseline;gap:0}
.chip .ex{font:400 13px 'Outfit','Tajawal',system-ui,sans-serif;color:var(--mute);line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;text-align:start;unicode-bidi:plaintext}
.group.games h2{color:var(--soft)}
.avlink{display:block;flex:none;border-radius:50%;transition:box-shadow .15s}
.avlink:hover{box-shadow:0 0 0 3px var(--red2)}
a.chname{color:inherit;text-decoration:none;border-bottom:2px solid transparent;transition:border-color .15s}
a.chname:hover,a.chname:focus-visible{border-bottom-color:var(--red2);outline:none}
.logo{width:48px;height:48px;border-radius:14px;background:#141416;padding:6px;flex:none;box-shadow:0 0 24px -8px var(--red2)}
.brand{font-size:19px;font-weight:600}
.hero{padding:26px 0 8px}
.hero h1{font-size:40px;line-height:1.15;max-width:720px}
.hero .lead{margin:14px 0 22px}
.lead.small{font-size:15px}
.dlbox{display:flex;flex-direction:column;align-items:flex-start;gap:6px}
.dl{display:inline-flex;align-items:center;gap:10px;background:var(--red2);color:#fff;text-decoration:none;font-weight:600;font-size:18px;padding:14px 26px;border-radius:12px;box-shadow:0 10px 30px -12px var(--red2)}
.dlrow{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.dlusers{display:inline-flex;align-items:center;gap:8px;padding:10px 14px;border:1px solid var(--line);border-radius:12px;color:var(--mute);font-size:15px}
.dlusers b{color:var(--text);font-size:17px}.dlusers svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.dl:hover,.dl:focus-visible{filter:brightness(1.15);outline:none}
.dl:focus-visible{box-shadow:0 0 0 3px color-mix(in srgb,var(--red2) 45%,transparent)}
.dl svg,.feat svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
.dlmeta{margin:6px 0 0;color:var(--soft);font-size:15px}
.req{margin:0;color:var(--mute);font-size:14px}
.req a,.foot a{color:var(--soft)}
.req a:hover,.foot a:hover{color:var(--text)}
section{margin-top:40px}
h2{font-size:22px;font-weight:600;margin:0 0 16px}
.feats{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.feat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px}
.feat svg{color:var(--red2)}
.feat h3{margin:10px 0 6px;font-size:17px;font-weight:600}
.feat p{margin:0;color:var(--soft);font-size:15px;overflow-wrap:anywhere}
.steps{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:12px}
.steps li{display:flex;gap:14px;align-items:flex-start;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;font-size:16px}
.num{width:28px;height:28px;border-radius:50%;background:var(--red2);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:15px;flex:none}
.note{margin-top:14px;border:1px solid var(--line);border-inline-start:3px solid var(--red2);border-radius:12px;padding:14px 16px;background:var(--panel)}
.note p{margin:6px 0 0;color:var(--soft);font-size:15px}
.faq details{background:var(--panel);border:1px solid var(--line);border-radius:12px;margin-bottom:10px}
.faq summary{cursor:pointer;padding:14px 16px;font-weight:600;list-style-position:inside}
.faq summary:focus-visible{outline:2px solid var(--red2);outline-offset:-2px;border-radius:12px}
.faq p{margin:0;padding:0 16px 14px;color:var(--soft);font-size:15px;overflow-wrap:anywhere}
.cmpwrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
table.cmp{width:100%;border-collapse:collapse;font-size:15px;min-width:680px}
.cmp .mk{display:inline-block;width:1.2em;font-weight:700}.cmp .mk.yes{color:var(--ok)}.cmp .mk.no{color:var(--mute)}
.cmp th,.cmp td{text-align:start;padding:12px 16px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
.cmp tbody tr:last-child th,.cmp tbody tr:last-child td{border-bottom:0}
.cmp thead th{font-size:14px;color:var(--mute);font-weight:600}
.cmp thead th.us{color:var(--red2)}
.cmp tbody th{font-weight:600;width:28%}
.cmp td{color:var(--soft)}
.cmp td.us{color:var(--text);background:color-mix(in srgb,var(--red2) 7%,transparent)}
.cmp tr.con td.us{color:var(--soft)}
.cmpnote{color:var(--mute);font-size:14px;margin:10px 2px 0}
@media (max-width:520px){.hero h1{font-size:30px}.dl{width:100%;justify-content:center}.dlbox{align-items:stretch}.dlrow{flex-direction:column;align-items:stretch}.dlusers{justify-content:center}}
@media (max-width:520px){h1{font-size:23px}.wrap{padding-left:14px;padding-right:14px}}
[hidden]{display:none!important}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-bottom:18px;overflow-x:auto;overflow-y:hidden;padding-bottom:1px}
.tab{background:none;border:0;border-bottom:2px solid transparent;color:var(--mute);padding:10px 16px;font:600 16px 'Outfit','Tajawal',sans-serif;cursor:pointer;margin-bottom:-1px;white-space:nowrap}
.tab:hover,.tab:focus-visible{color:var(--text);outline:none}
.tab.on{color:var(--text);border-bottom-color:var(--red2)}
.subtabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.sub-tab{border:1px solid var(--line);background:var(--chip);color:var(--soft);padding:7px 14px;border-radius:8px;font:500 15px 'Outfit','Tajawal',sans-serif;cursor:pointer}
.sub-tab:hover,.sub-tab:focus-visible{border-color:var(--red2);outline:none}
.sub-tab.on{border-color:var(--red2);color:var(--text);background:color-mix(in srgb,var(--red2) 15%,transparent)}
.lb{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.lbrow{display:flex;align-items:center;gap:14px;padding:12px 18px;border-bottom:1px solid var(--line);border-inline-start:3px solid transparent}
.lbrow:last-child{border-bottom:0}
.rk{width:28px;flex:none;text-align:center;font-weight:600;color:var(--mute)}
.nm{flex:1;min-width:0;overflow-wrap:anywhere;font-weight:500;color:var(--soft)}
.nm small{display:block;color:var(--mute);font-size:13px;font-weight:400}
.wn{font-weight:600;white-space:nowrap;color:var(--soft)}
:root{--gold:#e5b74b;--silver:#c5cad3;--bronze:#d18a4a}
@media (prefers-color-scheme:light){:root{--gold:#b8860b;--silver:#7f8792;--bronze:#a35a1f}}
.lbrow:nth-child(1){--c:var(--gold)}.lbrow:nth-child(2){--c:var(--silver)}.lbrow:nth-child(3){--c:var(--bronze)}
.lbrow:nth-child(-n+3){border-inline-start-color:var(--c)}
.lbrow:nth-child(-n+3) .rk,.lbrow:nth-child(-n+3) .nm,.lbrow:nth-child(-n+3) .wn{color:var(--c);font-weight:700}
`;

// The page script: picks the language, draws the groups, search and copy. All text goes in with textContent (never as HTML).
const CLIENT = `(function(){
var T=${JSON.stringify(TEXT)},ORDER=${JSON.stringify(PERMS)};
var el=document.getElementById("data"),D=el?JSON.parse(el.textContent):null,lang="en";
try{lang=localStorage.getItem("lang")||""}catch(e){}
if(lang!=="en"&&lang!=="ar")lang=/^ar\\b/i.test(navigator.language||"")?"ar":"en";
function t(k,p){var s=(T[lang]||T.en)[k]||T.en[k]||k;if(p)for(var x in p)s=s.split("{"+x+"}").join(p[x]);return s}
function $(id){return document.getElementById(id)}
function when(sec,day){var d=new Date(sec*1000);try{return day?d.toLocaleDateString(lang==="ar"?"ar":"en",{dateStyle:"medium"}):d.toLocaleString(lang==="ar"?"ar":"en",{dateStyle:"medium",timeStyle:"short"})}catch(e){return d.toISOString().slice(0,day?10:16).replace("T"," ")}}
var toastT=null;
function toast(msg){var b=$("toast");if(!b)return;b.textContent=msg;b.classList.add("show");clearTimeout(toastT);toastT=setTimeout(function(){b.classList.remove("show")},1600)}
function copy(txt){function done(){toast(t("copied",{c:txt}))}
  try{navigator.clipboard.writeText(txt).then(done,function(){fallback()})}catch(e){fallback()}
  function fallback(){var a=document.createElement("textarea");a.value=txt;a.setAttribute("readonly","");a.style.position="fixed";a.style.opacity="0";document.body.appendChild(a);a.select();try{document.execCommand("copy");done()}catch(e){}a.remove()}}
var cur="cmds",shownPlayers=0,sub="all";
function ownCount(){return D.commands.filter(function(c){return !c.builtin&&!c.game}).length}
function setCount(){
  if(!$("count")||!D)return;
  var lb=cur==="lb",k=lb?shownPlayers:ownCount(),p=lb?"players":"count",m=k%100;
  $("count").textContent=k===1?t(p+"1"):k===2?t(p+"2"):(m>=3&&m<=10)?t(p+"_few",{n:k}):t(p,{n:k})}
function drawLb(){
  var box=$("lbrows");if(!box||!D||!D.leaderboard)return;box.textContent="";
  var rows=(D.leaderboard[sub]||[]).filter(function(r){return r&&r.w>0}).slice(0,10);
  shownPlayers=rows.length;setCount();
  if(!rows.length){var e=document.createElement("p");e.className="empty";e.textContent=t("lb_empty");box.appendChild(e);return}
  rows.forEach(function(r,i){
    var row=document.createElement("div");row.className="lbrow";
    var rk=document.createElement("span");rk.className="rk";rk.textContent=String(i+1);
    var nm=document.createElement("div");nm.className="nm";var b=document.createElement("bdi");b.textContent=r.n;nm.appendChild(b);
    if(sub==="all"){var s=document.createElement("small");s.textContent=[["l","حروف"],["u","رتب"],["e","ايموجي"],["r","عكس"],["m","احسب"],["s","سلم"],["q","سؤال"]].filter(function(g){return r[g[0]]}).map(function(g){return g[1]+" "+r[g[0]]}).join(" · ");nm.appendChild(s)}
    var w=document.createElement("span");w.className="wn";w.textContent=r.w===1?t("win1"):t("wins",{n:r.w});
    row.appendChild(rk);row.appendChild(nm);row.appendChild(w);box.appendChild(row)})}
function showTab(tab){
  if(!$("tabs"))return;cur=tab;
  document.querySelectorAll(".tab").forEach(function(x){x.classList.toggle("on",x.getAttribute("data-tab")===tab)});
  $("pane-cmds").hidden=tab==="lb";$("pane-lb").hidden=tab!=="lb";setCount();
  try{var base=location.pathname.replace(/\\/leaderboard\\/?$/,"");history.replaceState(null,"",tab==="lb"?base+"/leaderboard":base)}catch(e){}}
function chip(c,sub,small){   // 1.13.0: a command with a short example (or what it does) under its name
  var b=document.createElement("button"),i=document.createElement("bdi");b.type="button";b.className="chip"+(sub?" has-ex":"");i.textContent=c.name;
  var top=document.createElement("span");top.className="ct";top.appendChild(i);
  if(small){var s=document.createElement("small");s.textContent=small;top.appendChild(s)}
  b.appendChild(top);
  if(sub){var e=document.createElement("span");e.className="ex";e.dir="auto";e.textContent=sub;b.appendChild(e);b.title=c.name+"  →  "+sub}
  b.addEventListener("click",function(){copy(c.name)});return b}
function group(title,list,cls,make){var g=document.createElement("section");g.className="group"+(cls?" "+cls:"");var h=document.createElement("h2");h.textContent=title+" ";
  var n=document.createElement("span");n.className="n";n.textContent="("+list.length+")";h.appendChild(n);g.appendChild(h);
  var w=document.createElement("div");w.className="chips";list.forEach(function(c){w.appendChild(make(c))});g.appendChild(w);return g}
function biText(c){return c.key?t("bd_"+c.key):""}
function gmText(c){return t("gd_"+c.game+"_"+c.what)}
function hit(c,q,extra){return !q||c.name.toLowerCase().indexOf(q)>=0||(extra||"").toLowerCase().indexOf(q)>=0}
function draw(){
  if(!D)return;var q=($("q").value||"").trim().toLowerCase(),box=$("groups"),shown=0;box.textContent="";
  ORDER.forEach(function(p){
    var cs=D.commands.filter(function(c){return !c.builtin&&!c.game&&c.perm===p&&hit(c,q,c.ex)});if(!cs.length)return;shown+=cs.length;
    box.appendChild(group(t("g_"+p),cs,"",function(c){return chip(c,c.ex||"","")}))});
  var gm=D.commands.filter(function(c){return c.game&&hit(c,q,gmText(c))});      // 1.13.0: the mini games' commands
  if(gm.length){shown+=gm.length;box.appendChild(group(t("g_games"),gm,"games",function(c){var b=chip(c,gmText(c),t("g_"+c.perm));return b}))}
  var bi=D.commands.filter(function(c){return c.builtin&&hit(c,q,biText(c))});    // the app's built-in commands
  if(bi.length){shown+=bi.length;box.appendChild(group(t("g_builtin"),bi,"builtin",function(c){var b=chip(c,biText(c),t("g_"+c.perm));if(!biText(c))b.title=t("bi_who",{w:t("g_"+c.perm)});return b}))}
  var none=$("none");none.hidden=shown>0;var own=D.commands.filter(function(c){return !c.builtin&&!c.game});none.textContent=own.length||bi.length||gm.length?t("none"):t("empty");
  setCount();   // Arabic: 2 = dual, 3-10 = plural
  $("updated").textContent=t("updated",{t:when(D.updated)})}
function apply(){
  document.documentElement.lang=lang;document.documentElement.dir=lang==="ar"?"rtl":"ltr";
  document.querySelectorAll("[data-t]").forEach(function(x){var p={};for(var k in x.dataset)p[k]=x.dataset[k];if(p.d)p.d=when(+p.d,true);x.textContent=t(x.getAttribute("data-t"),p)});
  var q=$("q");if(q){q.placeholder=t("search");q.setAttribute("aria-label",t("search"))}
  var b=$("lang");b.textContent=t("lang");b.lang=lang==="ar"?"en":"ar";draw();drawLb()}
$("lang").addEventListener("click",function(){lang=lang==="ar"?"en":"ar";try{localStorage.setItem("lang",lang)}catch(e){}apply()});
if($("q"))$("q").addEventListener("input",draw);
document.querySelectorAll("img.av").forEach(function(im){function swap(){var m=document.createElement("div");m.className="av mark";im.replaceWith(m)}if(im.complete&&!im.naturalWidth)swap();else im.addEventListener("error",swap)});   // no picture: the red mark instead
if($("tabs")){
  document.querySelectorAll(".tab").forEach(function(x){x.addEventListener("click",function(){showTab(x.getAttribute("data-tab"))})});
  document.querySelectorAll(".sub-tab").forEach(function(x){x.addEventListener("click",function(){sub=x.getAttribute("data-sub");document.querySelectorAll(".sub-tab").forEach(function(y){y.classList.toggle("on",y===x)});drawLb()})});
  if(D&&D.tab==="lb")showTab("lb");
}
apply();
})();`;
