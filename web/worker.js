// FQPN's Chat Bot: public command lists.
//
// One Cloudflare Worker with one D1 database (bound as DB). The app sends a channel's public commands here and viewers open
// SITE/<channel> to see them. Setup steps: web/SETUP.md.
//
//   GET    /                    a short page about the lists
//   GET    /<channel>           the channel's command list (English / Arabic)
//   GET    /api/list/<channel>  the same list as JSON
//   PUT    /api/list            save your list    (Authorization: OAuth <your Twitch login token from the app>)
//   DELETE /api/list            remove your list  (same)
//   PUT    /api/seen            "this channel uses the app, version X" (once a day from every app; same login check)
//   GET    /admin               the developer's private users list (asks for ADMIN_KEY, a secret set in Cloudflare)
//   GET    /api/admin/users     the same list as JSON (Authorization: Bearer <ADMIN_KEY>)
//
// The Twitch token is only used to ask Twitch whose channel it is. It is never stored or logged.

const FORMAT = 1;              // the newest data format the app sends; older formats keep working
const MAX_COMMANDS = 500;
const MAX_NAME = 60;
const MAX_BODY = 64 * 1024;    // bytes
const MIN_GAP = 5;             // seconds between two saves of the same channel
const PERMS = ["everyone", "subscriber", "vip", "moderator", "broadcaster"];
const LOGIN_RE = /^[a-z0-9_]{1,25}$/;
const VERSION_RE = /^[0-9A-Za-z.+-]{1,32}$/;
const SEEN_GAP = 3600;         // one report per channel per hour is plenty (the app sends once a day)
const AVATAR_RE = /^https:\/\/static-cdn\.jtvnw\.net\/[A-Za-z0-9._\/-]+$/;

let tablesReady = false;
async function setup(db) {
  if (tablesReady) return;
  await db.batch([
    db.prepare("CREATE TABLE IF NOT EXISTS lists (login TEXT PRIMARY KEY, user_id TEXT NOT NULL, display TEXT, avatar TEXT, data TEXT NOT NULL, updated INTEGER NOT NULL)"),
    db.prepare("CREATE INDEX IF NOT EXISTS lists_user ON lists(user_id)"),
    db.prepare("CREATE TABLE IF NOT EXISTS blocked (who TEXT PRIMARY KEY, note TEXT)"),
    db.prepare("CREATE TABLE IF NOT EXISTS seen (user_id TEXT PRIMARY KEY, login TEXT NOT NULL, display TEXT, version TEXT, first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL)"),
  ]);
  tablesReady = true;
}

export default {
  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (e) {
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
  if (path === "/api/admin/users") {
    if (req.method !== "GET") return json({ error: "Method not allowed." }, 405, { Allow: "GET" });
    return adminUsers(req, env);
  }
  if (req.method !== "GET" && req.method !== "HEAD") return json({ error: "Method not allowed." }, 405, { Allow: "GET" });
  if (path === "/admin" || path === "/admin/") return page(adminBody(), "Users · FQPN's Chat Bot", 200, 0, null, ADMIN_JS, "connect-src 'self'; ");
  if (path === "/") return page(homeBody(url.origin), "FQPN's Chat Bot · command lists", 200, 3600);
  if (path === "/robots.txt") return new Response("User-agent: *\nAllow: /\n", { headers: { "Content-Type": "text/plain; charset=utf-8" } });
  if (path === "/favicon.ico") return new Response(null, { status: 204 });

  let m = path.match(/^\/api\/list\/([^/]+)$/);
  if (m) {
    const login = cleanLogin(m[1]);
    if (!login) return json({ error: "Not found." }, 404, CORS);
    await setup(env.DB);
    const row = await env.DB.prepare("SELECT * FROM lists WHERE login = ?").bind(login).first();
    if (!row) return json({ error: "Not found." }, 404, CORS);
    return json(publicView(row), 200, { ...CORS, "Cache-Control": "public, max-age=30" });
  }
  m = path.match(/^\/@?([^/]+)\/?$/);
  if (m) {
    let raw;
    try { raw = decodeURIComponent(m[1]); } catch { raw = ""; }
    const login = cleanLogin(raw);
    if (!login) return page(missingBody(""), "Not found", 404, 60);
    if (path !== "/" + login) return Response.redirect(url.origin + "/" + login, 301);
    await setup(env.DB);
    const row = await env.DB.prepare("SELECT * FROM lists WHERE login = ?").bind(login).first();
    if (!row) return page(missingBody(login), "Not found", 404, 30);
    const view = publicView(row);
    return page(listBody(view), (view.display || login) + " · commands", 200, 30, view);
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
           updated: row.updated, commands: Array.isArray(data.commands) ? data.commands : [] };
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
    commands.push({ name, perm: PERMS.includes(c.perm) ? c.perm : "everyone" });
  }
  return { list: { v: FORMAT, commands } };
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
  return json({ ok: true, login: who.login, count: clean.list.commands.length, url: url.origin + "/" + who.login });
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
  const row = await env.DB.prepare("SELECT last_seen FROM seen WHERE user_id = ?").bind(who.userId).first();
  if (row && now - row.last_seen < SEEN_GAP) return json({ ok: true, counted: false }, 429, { "Retry-After": String(SEEN_GAP) });
  const p = await profile(who);
  await env.DB.prepare("INSERT INTO seen (user_id, login, display, version, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?) " +
                       "ON CONFLICT(user_id) DO UPDATE SET login = excluded.login, display = excluded.display, version = excluded.version, last_seen = excluded.last_seen")
    .bind(who.userId, who.login, p.display || who.login, version, now, now).run();
  return json({ ok: true, counted: true });
}

// The admin key is compared in constant time, and every wrong try waits a second, so it can't be guessed quickly.
async function adminOk(req, env) {
  const key = String(env.ADMIN_KEY || "");
  const m = (req.headers.get("Authorization") || "").match(/^Bearer (.+)$/);
  const given = m ? m[1] : "";
  if (key.length < 12 || !given) return false;
  const a = new TextEncoder().encode(await sha256(key)), b = new TextEncoder().encode(await sha256(given));
  let diff = a.length ^ b.length;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}
async function sha256(s) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function adminUsers(req, env) {
  if (!env.ADMIN_KEY || String(env.ADMIN_KEY).length < 12) return json({ error: "Set the ADMIN_KEY secret in Cloudflare first (at least 12 characters)." }, 503);
  if (!(await adminOk(req, env))) {
    await new Promise((r) => setTimeout(r, 1000));
    return json({ error: "Wrong password." }, 401);
  }
  await setup(env.DB);
  const rows = (await env.DB.prepare("SELECT login, display, version, first_seen, last_seen FROM seen ORDER BY last_seen DESC").all()).results || [];
  return json({ now: Math.floor(Date.now() / 1000), users: rows });
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
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600&family=Tajawal:wght@400;500;700&display=swap">
<style nonce="${nonce}">${CSS}</style>
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
        "font-src https://fonts.gstatic.com; img-src https://static-cdn.jtvnw.net; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
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
    g_everyone: "Everyone", g_subscriber: "Subscribers", g_vip: "VIPs", g_moderator: "Moderators", g_broadcaster: "Broadcaster",
    updated: "Updated {t}", made: "Made with FQPN's Chat Bot", lang: "العربية",
    home_t: "Public command lists", home_d: "Streamers who use FQPN's Chat Bot can share their chat commands here. Open a link like {u} to see a channel's list.",
    miss_t: "No list here", miss_d: "There is no public command list for {c}. The streamer can switch it on in FQPN's Chat Bot, on the Commands page.",
    miss_d0: "This page doesn't exist.",
  },
  ar: {
    commands: "الأوامر", count: "{n} أمر", count1: "أمر واحد", count2: "أمران", count_few: "{n} أوامر", search: "ابحث في الأوامر", none: "لا توجد أوامر تطابق بحثك.",
    empty: "لا توجد أوامر عامة لهذه القناة بعد.", copy: "اضغط على أمر لنسخه.", copied: "تم نسخ {c}",
    g_everyone: "الجميع", g_subscriber: "المشتركون", g_vip: "VIP", g_moderator: "المشرفون", g_broadcaster: "صاحب القناة",
    updated: "آخر تحديث {t}", made: "صُنعت باستخدام FQPN's Chat Bot", lang: "English",
    home_t: "قوائم الأوامر العامة", home_d: "يمكن لصنّاع المحتوى الذين يستخدمون FQPN's Chat Bot مشاركة أوامر الشات هنا. افتح رابطًا مثل {u} لرؤية قائمة القناة.",
    miss_t: "لا توجد قائمة هنا", miss_d: "لا توجد قائمة أوامر عامة لـ {c}. يمكن لصاحب القناة تفعيلها في FQPN's Chat Bot من صفحة الأوامر.",
    miss_d0: "هذه الصفحة غير موجودة.",
  },
};

function homeBody(origin) {
  return `<header class="top"><div class="who"><div class="mark" aria-hidden="true"></div><div><h1 data-t="home_t">${esc(TEXT.en.home_t)}</h1></div></div>${langBtn()}</header>
<p class="lead" data-t="home_d" data-u="${esc(origin)}/fqpn_">${esc(TEXT.en.home_d.replace("{u}", origin + "/fqpn_"))}</p>`;
}

function missingBody(login) {
  return `<header class="top"><div class="who"><div class="mark" aria-hidden="true"></div><div><h1 data-t="miss_t">${esc(TEXT.en.miss_t)}</h1></div></div>${langBtn()}</header>
<p class="lead" data-t="${login ? "miss_d" : "miss_d0"}" data-c="${esc(login)}">${esc(login ? TEXT.en.miss_d.replace("{c}", login) : TEXT.en.miss_d0)}</p>
<footer class="foot"><span data-t="made">${esc(TEXT.en.made)}</span></footer>`;
}

function listBody(view) {
  const avatar = view.avatar ? `<img class="av" src="${esc(view.avatar)}" alt="" width="56" height="56">` : `<div class="av mark" aria-hidden="true"></div>`;
  return `<header class="top"><div class="who">${avatar}<div><h1><bdi>${esc(view.display)}</bdi> <span class="sub" data-t="commands">${esc(TEXT.en.commands)}</span></h1><p class="meta" id="count"></p></div></div>${langBtn()}</header>
<div class="searchbox"><input id="q" type="search" autocomplete="off" spellcheck="false" dir="auto" data-ph="search" aria-label="${esc(TEXT.en.search)}" placeholder="${esc(TEXT.en.search)}"></div>
<p class="hint" data-t="copy">${esc(TEXT.en.copy)}</p>
<div id="groups"></div>
<p class="empty" id="none" hidden></p>
<footer class="foot"><span id="updated"></span><span data-t="made">${esc(TEXT.en.made)}</span></footer>
<div class="toast" id="toast" role="status" aria-live="polite"></div>`;
}

function adminBody() {
  return `<header class="top"><div class="who"><div class="mark" aria-hidden="true"></div><div><h1>Users</h1><p class="meta">Channels that use FQPN's Chat Bot</p></div></div></header>
<form id="login" class="adm-login" autocomplete="off"><label for="key">Password</label><div class="adm-row"><input id="key" type="password" autocomplete="current-password" required><button class="lang" type="submit">Open</button></div><p class="hint" id="err" role="alert"></p></form>
<div id="panel" hidden>
<div class="adm-totals"><div><b id="t-all">0</b><span>channels</span></div><div><b id="t-week">0</b><span>active this week</span></div><div><b id="t-day">0</b><span>active today</span></div></div>
<div class="searchbox"><input id="q" type="search" placeholder="Search channels" aria-label="Search channels" autocomplete="off" spellcheck="false"></div>
<div class="adm-wrap"><table class="adm"><thead><tr><th>Channel</th><th>Version</th><th>Last seen</th><th>First seen</th></tr></thead><tbody id="rows"></tbody></table></div>
<p class="empty" id="none" hidden>No channels yet.</p>
<footer class="foot"><button class="lang" id="out" type="button">Lock</button><span>Only you can see this page.</span></footer>
</div>`;
}

// The admin page's script: the password stays in this tab only (sessionStorage) and every name goes in as text, never HTML.
const ADMIN_JS = `(function(){
var $=function(i){return document.getElementById(i)},data=null,key="";
try{key=sessionStorage.getItem("adm")||""}catch(e){}
function ago(sec){var d=Math.max(0,Math.floor(Date.now()/1000)-sec);if(d<60)return "just now";if(d<3600)return Math.floor(d/60)+" min ago";if(d<86400)return Math.floor(d/3600)+" h ago";var n=Math.floor(d/86400);return n+(n===1?" day ago":" days ago")}
function day(sec){return new Date(sec*1000).toLocaleDateString("en",{year:"numeric",month:"short",day:"numeric"})}
function draw(){var q=($("q").value||"").trim().toLowerCase(),tb=$("rows"),now=data.now,shown=0;tb.textContent="";
  $("t-all").textContent=data.users.length;$("t-week").textContent=data.users.filter(function(u){return now-u.last_seen<7*86400}).length;$("t-day").textContent=data.users.filter(function(u){return now-u.last_seen<86400}).length;
  data.users.forEach(function(u){if(q&&u.login.indexOf(q)<0&&String(u.display||"").toLowerCase().indexOf(q)<0)return;shown++;
    var tr=document.createElement("tr"),a=document.createElement("a"),td=document.createElement("td");
    a.href="https://twitch.tv/"+encodeURIComponent(u.login);a.target="_blank";a.rel="noopener noreferrer";a.textContent=(u.display||u.login)+" \u2197";td.appendChild(a);tr.appendChild(td);
    [u.version||"-",ago(u.last_seen),day(u.first_seen)].forEach(function(v,i){var c=document.createElement("td");c.textContent=v;if(i===1)c.title=new Date(u.last_seen*1000).toLocaleString();tr.appendChild(c)});
    tb.appendChild(tr)});
  $("none").hidden=shown>0;$("none").textContent=data.users.length?"No channel matches your search.":"No channels yet."}
function load(){$("err").textContent="";
  fetch("/api/admin/users",{headers:{Authorization:"Bearer "+key},cache:"no-store"}).then(function(r){return r.json().then(function(j){return {s:r.status,j:j}})}).then(function(x){
    if(x.s!==200){$("err").textContent=x.j.error||"Couldn't open the list.";$("login").hidden=false;$("panel").hidden=true;try{sessionStorage.removeItem("adm")}catch(e){}return}
    data=x.j;try{sessionStorage.setItem("adm",key)}catch(e){}$("login").hidden=true;$("panel").hidden=false;draw()}).catch(function(){$("err").textContent="The website can't be reached."})}
$("login").addEventListener("submit",function(e){e.preventDefault();key=$("key").value;load()});
$("q").addEventListener("input",function(){if(data)draw()});
$("out").addEventListener("click",function(){key="";data=null;try{sessionStorage.removeItem("adm")}catch(e){}$("panel").hidden=true;$("login").hidden=false;$("key").value=""});
if(key)load();
})();`;

function langBtn() {
  return `<button class="lang" id="lang" type="button" lang="ar">${TEXT.en.lang}</button>`;
}

const CSS = `
:root{--red:#7d0b0f;--red2:#a3121a;--bg:#0b0b0c;--panel:#101011;--line:#222224;--text:#f2f2f2;--mute:#9b9ba1;--soft:#cfcfd4;--chip:#161618;--ok:#3fb871}
@media (prefers-color-scheme:light){:root{--bg:#f4f4f6;--panel:#fff;--line:#e2e2e7;--text:#17171a;--mute:#6b6b73;--soft:#44444a;--chip:#f7f7f9}}
*{box-sizing:border-box}
html{background:var(--bg);color:var(--text);font:16px/1.5 'Outfit','Tajawal',system-ui,sans-serif;-webkit-text-size-adjust:100%}
body{margin:0;min-height:100vh;background:radial-gradient(1200px 500px at 85% -10%,rgba(163,18,26,.18),transparent 60%),var(--bg)}
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
.searchbox input:focus{outline:none;border-color:var(--red2);box-shadow:0 0 0 3px rgba(163,18,26,.25)}
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
@media (max-width:520px){h1{font-size:23px}.wrap{padding-left:14px;padding-right:14px}}
`;

// The page script: picks the language, draws the groups, search and copy. All text goes in with textContent (never as HTML).
const CLIENT = `(function(){
var T=${JSON.stringify(TEXT)},ORDER=${JSON.stringify(PERMS)};
var el=document.getElementById("data"),D=el?JSON.parse(el.textContent):null,lang="en";
try{lang=localStorage.getItem("lang")||""}catch(e){}
if(lang!=="en"&&lang!=="ar")lang=/^ar\\b/i.test(navigator.language||"")?"ar":"en";
function t(k,p){var s=(T[lang]||T.en)[k]||T.en[k]||k;if(p)for(var x in p)s=s.split("{"+x+"}").join(p[x]);return s}
function $(id){return document.getElementById(id)}
function when(sec){var d=new Date(sec*1000);try{return d.toLocaleString(lang==="ar"?"ar":"en",{dateStyle:"medium",timeStyle:"short"})}catch(e){return d.toISOString().slice(0,16).replace("T"," ")}}
var toastT=null;
function toast(msg){var b=$("toast");if(!b)return;b.textContent=msg;b.classList.add("show");clearTimeout(toastT);toastT=setTimeout(function(){b.classList.remove("show")},1600)}
function copy(txt){function done(){toast(t("copied",{c:txt}))}
  try{navigator.clipboard.writeText(txt).then(done,function(){fallback()})}catch(e){fallback()}
  function fallback(){var a=document.createElement("textarea");a.value=txt;a.setAttribute("readonly","");a.style.position="fixed";a.style.opacity="0";document.body.appendChild(a);a.select();try{document.execCommand("copy");done()}catch(e){}a.remove()}}
function draw(){
  if(!D)return;var q=($("q").value||"").trim().toLowerCase(),box=$("groups"),shown=0;box.textContent="";
  ORDER.forEach(function(p){
    var cs=D.commands.filter(function(c){return c.perm===p&&(!q||c.name.toLowerCase().indexOf(q)>=0)});if(!cs.length)return;shown+=cs.length;
    var g=document.createElement("section");g.className="group";var h=document.createElement("h2");h.textContent=t("g_"+p)+" ";
    var n=document.createElement("span");n.className="n";n.textContent="("+cs.length+")";h.appendChild(n);g.appendChild(h);
    var w=document.createElement("div");w.className="chips";
    cs.forEach(function(c){var b=document.createElement("button"),i=document.createElement("bdi");b.type="button";b.className="chip";i.textContent=c.name;b.appendChild(i);b.addEventListener("click",function(){copy(c.name)});w.appendChild(b)});
    g.appendChild(w);box.appendChild(g)});
  var none=$("none");none.hidden=shown>0;none.textContent=D.commands.length?t("none"):t("empty");
  var k=D.commands.length,m=k%100;$("count").textContent=k===1?t("count1"):k===2?t("count2"):(m>=3&&m<=10)?t("count_few",{n:k}):t("count",{n:k});   // Arabic: 2 = dual, 3-10 = plural
  $("updated").textContent=t("updated",{t:when(D.updated)})}
function apply(){
  document.documentElement.lang=lang;document.documentElement.dir=lang==="ar"?"rtl":"ltr";
  document.querySelectorAll("[data-t]").forEach(function(x){x.textContent=t(x.getAttribute("data-t"),{u:x.getAttribute("data-u")||"",c:x.getAttribute("data-c")||""})});
  var q=$("q");if(q){q.placeholder=t("search");q.setAttribute("aria-label",t("search"))}
  var b=$("lang");b.textContent=t("lang");b.lang=lang==="ar"?"en":"ar";draw()}
$("lang").addEventListener("click",function(){lang=lang==="ar"?"en":"ar";try{localStorage.setItem("lang",lang)}catch(e){}apply()});
if($("q"))$("q").addEventListener("input",draw);
document.querySelectorAll("img.av").forEach(function(im){function swap(){var m=document.createElement("div");m.className="av mark";im.replaceWith(m)}if(im.complete&&!im.naturalWidth)swap();else im.addEventListener("error",swap)});   // no picture: the red mark instead
apply();
})();`;
