/* FQPN Leaderboard: a Twitch panel extension. Shows the channel's leaderboards, sent to fqpnbot.com by the streamer's
   FQPN's Chat Bot app. It reads only https://fqpnbot.com/api/panel/<channel ID>; it sends nothing about viewers anywhere.
   "Show my place": Twitch tells the panel the viewer's user ID (only if they agree); it's compared here, in the browser. */
(function () {
  "use strict";
  var SITE = "https://fqpnbot.com";
  var REFRESH = 90000;           // ms between refreshes (plus a random bit, so every viewer doesn't ask at once)
  var T = {
    en: { ttl: "Leaderboard", tabs: { t: "Watch", m: "Messages", g: "Games", f: "First" },
      sub: { t: "Watch time", m: "Messages", g: "Mini games", f: "First in chat" },
      per: { week: "Week", month: "Month", all: "All-time", peak: "Longest streak", count: "Most firsts" },
      perSub: { week: "this week", month: "this month", all: "all time", peak: "longest streak", count: "most firsts" },
      col: { t: "Watch time", m: "Messages", g: "Wins", f: "Streak", fc: "Firsts" }, name: "Name",
      you: "You", ask: "Show my place", out: "You're not in the top 100 yet. Keep watching!", outSmall: "You're not in the top 10 yet.",
      empty: "Nobody here yet.", none: "This channel hasn't connected the leaderboard yet.",
      noneB: "Streamer? Get FQPN's Chat Bot (free) and switch on the Twitch panel.", get: "fqpnbot.com",
      err: "Couldn't load the leaderboard. Trying again soon.", upd: "Updated", now: "🔥 Streak now: {n} · {v}",
      noteT: "Counted while live", noteM: "Counted from chat", noteG: "Letters · Scramble · Reverse · Math", noteF: "Type «first» when the stream starts" },
    ar: { ttl: "المتصدرين", tabs: { t: "المشاهدة", m: "الرسائل", g: "الألعاب", f: "أول" },
      sub: { t: "وقت المشاهدة", m: "الرسائل", g: "الألعاب", f: "أول في الشات" },
      per: { week: "هالأسبوع", month: "هالشهر", all: "الكل", peak: "أطول ستريك", count: "أكثر أول" },
      perSub: { week: "هالأسبوع", month: "هالشهر", all: "الكل", peak: "أطول ستريك", count: "أكثر أول" },
      col: { t: "وقت المشاهدة", m: "الرسائل", g: "الفوز", f: "الستريك", fc: "عدد المرات" }, name: "الاسم",
      you: "أنت", ask: "اعرض مكاني", out: "أنت مو في أول 100 للحين. كمّل!", outSmall: "أنت مو في أول 10 للحين.",
      empty: "ما فيه أحد للحين.", none: "هالقناة ما ربطت الترتيب للحين.",
      noneB: "ستريمر؟ حمّل FQPN's Chat Bot مجاناً وشغّل بانل تويتش.", get: "fqpnbot.com",
      err: "ما قدرنا نجيب الترتيب. بنحاول بعد شوي.", upd: "تحديث", now: "🔥 الستريك الحين: {n} · {v}",
      noteT: "ينحسب وقت اللايف", noteM: "من الشات مباشرة", noteG: "حروف · رتب · عكس · احسب", noteF: "اكتب «اول» أول ما يبدأ البث" }
  };
  var ICON = { t: '<path d="M12 7v5l3 2"/><circle cx="12" cy="12" r="9"/>', m: '<path d="M4 5h16v11H8l-4 4z"/>',
    g: '<rect x="2.5" y="7" width="19" height="11" rx="4"/><path d="M7 11v3M5.5 12.5h3M15 12h.01M17.5 13.5h.01"/>',
    f: '<path d="M12 3c1 3 4 4.5 4 8.5a4 4 0 0 1-8 0c0-1.5.7-2.6 1.5-3.5.2 1.6 1 2.5 2 2.5-.5-2.5-.2-5 .5-7.5z"/>' };
  var COLORS = ["#7bc96f", "#c084fc", "#38bdf8", "#f59e0b", "#fb7185", "#a3e635", "#5eead4", "#f472b6", "#60a5fa", "#facc15"];
  var S = { data: null, channel: "", viewer: "", tab: "t", per: { t: "week", m: "week", g: "all", f: "peak" }, lang: "", state: "loading", timer: 0 };
  var $ = function (id) { return document.getElementById(id); };

  function L() { return T[S.lang] || T.en; }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function initial(name) { var m = String(name || "?").match(/[^\s\d_\W]|\p{L}/u); return (m ? m[0] : String(name || "?")[0] || "?").toUpperCase(); }
  function colorOf(s) { var h = 0; s = String(s || ""); for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return COLORS[h % COLORS.length]; }
  function arCount(n, one, two, few, many) {   // Arabic counting: 1, 2, 3-10, 11+
    var r = n % 100;
    if (n === 1) return one; if (n === 2) return two;
    return n + " " + (r >= 3 && r <= 10 ? few : many);
  }
  function fmt(kind, v) {
    var ar = S.lang === "ar";
    if (kind === "t") {
      var h = Math.floor(v / 3600), m = Math.floor((v % 3600) / 60);
      if (ar) return h ? h + ":" + (m < 10 ? "0" : "") + m + " س" : m + " د";
      return h ? h + "h " + (m < 10 ? "0" : "") + m + "m" : m + "m";
    }
    if (kind === "m") return v.toLocaleString("en-US");
    if (kind === "g") return ar ? arCount(v, "فوز واحد", "فوزتين", "فوزات", "فوز") : v + (v === 1 ? " win" : " wins");
    if (kind === "f") return ar ? "🔥 " + arCount(v, "بث", "بثين", "بثوث", "بث") : "🔥 " + v + (v === 1 ? " stream" : " streams");
    if (kind === "fc") return ar ? arCount(v, "مرة", "مرتين", "مرات", "مرة") : v + (v === 1 ? " time" : " times");
    return String(v);
  }
  function lighter(hex, f) {        // the streamer's accent, brighter so it glows on black
    var m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || ""); if (!m) return null;
    var c = [1, 2, 3].map(function (i) { var x = parseInt(m[i], 16); return Math.round(x + (255 - x) * f); });
    return c;
  }
  function applyAccent(hex) {
    var c = lighter(hex, 0.35), d = lighter(hex, 0.1); if (!c) return;
    var r = document.documentElement.style;
    r.setProperty("--neon", "rgb(" + c.join(",") + ")"); r.setProperty("--neon2", "rgb(" + d.join(",") + ")");
    r.setProperty("--neonA", "rgba(" + c.join(",") + ",.55)"); r.setProperty("--neonB", "rgba(" + c.join(",") + ",.12)");
  }
  function avatar(key, name, cls) {
    var a = el("span", "av" + (cls ? " " + cls : ""));
    var url = S.data && S.data.av && S.data.av[key];
    if (url && /^https:\/\/static-cdn\.jtvnw\.net\//.test(url)) {
      var img = el("img"); img.alt = ""; img.loading = "lazy"; img.referrerPolicy = "no-referrer"; img.src = url;
      img.addEventListener("error", function () { a.textContent = initial(name); });
      a.appendChild(img);
    } else a.textContent = initial(name);
    return a;
  }
  function kindOf() { return S.tab === "f" && S.per.f === "count" ? "fc" : S.tab; }
  function rowsNow() {
    var b = S.data && S.data.b && S.data.b[S.tab]; if (!b) return [];
    var r = b[S.per[S.tab]]; return Array.isArray(r) ? r : [];
  }

  function drawTabs() {
    var tb = $("tabs"); tb.textContent = "";
    ["t", "m", "g", "f"].forEach(function (k) {
      var b = el("button"); b.type = "button"; b.setAttribute("role", "tab"); b.setAttribute("aria-selected", String(S.tab === k));
      b.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + ICON[k] + "</svg>";
      b.appendChild(el("span", "", L().tabs[k]));
      b.addEventListener("click", function () { S.tab = k; draw(); });
      tb.appendChild(b);
    });
    var pr = $("per"); pr.textContent = "";
    (S.tab === "f" ? ["peak", "count"] : ["week", "month", "all"]).forEach(function (p) {
      var b = el("button", "", L().per[p]); b.type = "button"; b.setAttribute("aria-pressed", String(S.per[S.tab] === p));
      b.addEventListener("click", function () { S.per[S.tab] = p; draw(); });
      pr.appendChild(b);
    });
  }

  function draw() {
    var t = L(), ar = S.lang === "ar";
    document.documentElement.lang = ar ? "ar" : "en"; document.body.dir = ar ? "rtl" : "ltr";
    $("ttl").textContent = t.ttl; $("lng").textContent = ar ? "EN" : "ع";
    $("sub").textContent = t.sub[S.tab] + " · " + t.perSub[S.per[S.tab]];
    drawTabs();
    var login = S.data && S.data.login;
    $("link").href = SITE + (login ? "/" + encodeURIComponent(login) + "/leaderboard" : "");
    $("link").textContent = "fqpnbot.com" + (login ? "/" + login : "") + " ↗";
    var main = $("main"), msg = $("msg");
    if (S.state !== "ok") {
      main.hidden = true; msg.hidden = false; msg.textContent = ""; $("per").hidden = true;
      if (S.state === "none") {
        msg.appendChild(el("b", "", t.none)); msg.appendChild(el("span", "", t.noneB));
        var a = el("a", "", t.get); a.href = SITE; a.target = "_blank"; a.rel = "noopener"; msg.appendChild(a);
      } else msg.appendChild(el("span", S.state === "loading" ? "skel" : "", S.state === "loading" ? "…" : t.err));
      $("note").textContent = ""; return;
    }
    main.hidden = false; msg.hidden = true; $("per").hidden = false;
    var kind = kindOf(), rows = rowsNow();
    $("thn").textContent = t.name; $("thv").textContent = kind === "fc" ? t.col.fc : t.col[S.tab];
    // podium: 2nd, 1st, 3rd
    var pod = $("pod"); pod.textContent = "";
    [1, 0, 2].forEach(function (i) {
      var r = rows[i], d = el("div", "pd p" + (i + 1) + (r ? "" : " empty"));
      if (i === 0) d.appendChild(el("div", "crown", "👑"));
      var nm = el("div", "nm"); nm.appendChild(el("bdi", "", r ? r[1] : "—")); d.appendChild(nm);
      var ring = el("div", "ring"); ring.appendChild(r ? avatar(r[0], r[1]) : el("span", "av", "?"));
      ring.appendChild(el("span", "med", String(i + 1))); d.appendChild(ring);
      d.appendChild(el("div", "val", r ? fmt(kind, r[2]) : "—"));
      pod.appendChild(d);
    });
    var ls = $("ls"); ls.textContent = "";
    rows.slice(3).forEach(function (r, j) { ls.appendChild(row(j + 4, r, kind, false)); });
    if (!rows.length) ls.appendChild(el("div", "me out", t.empty));
    // the viewer's own row
    var me = $("me"); me.textContent = "";
    if (S.tab !== "f" && !(S.viewer && S.viewer === S.channel)) {      // (the streamer never has their own row)
      if (!S.viewer) {
        var ask = el("button", "ask", "👤 " + t.ask); ask.type = "button";
        ask.addEventListener("click", function () { try { window.Twitch.ext.actions.requestIdShare(); } catch (e) {} });
        me.appendChild(ask);
      } else {
        var at = -1; for (var i = 0; i < rows.length; i++) if (rows[i][0] === S.viewer) { at = i; break; }
        if (at >= 0) { var mr = row(at + 1, rows[at], kind, true); me.appendChild(mr); }
        else me.appendChild(el("div", "out", S.tab === "g" ? t.outSmall : t.out));
      }
    }
    var note = { t: t.noteT, m: t.noteM, g: t.noteG, f: t.noteF }[S.tab];
    var now = S.data.b && S.data.b.f && S.data.b.f.now;
    if (S.tab === "f" && now) note = t.now.replace("{n}", now[1]).replace("{v}", fmt("f", now[2]).replace("🔥 ", ""));
    $("note").textContent = note;
  }
  function row(rank, r, kind, mine) {
    var d = el("div", "r"), c = colorOf(r[1]);
    d.style.setProperty("--c", c);
    d.appendChild(el("span", "k", String(rank)));
    d.appendChild(avatar(r[0], r[1]));
    var n = el("span", "n"); n.appendChild(el("bdi", "", mine ? L().you : r[1])); d.appendChild(n);
    d.appendChild(el("span", "v", fmt(kind, r[2])));
    return d;
  }

  function load() {
    if (!S.channel) return;
    clearTimeout(S.timer);
    fetch(SITE + "/api/panel/" + encodeURIComponent(S.channel), { credentials: "omit" })
      .then(function (r) { if (r.status === 404) return null; if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(function (d) {
        if (!d || !d.b) { S.state = "none"; S.data = null; }
        else { S.state = "ok"; S.data = d; if (!S.lang) S.lang = d.lang === "ar" ? "ar" : "en"; if (d.accent) applyAccent(d.accent); }
        draw();
      })
      .catch(function () { if (S.state !== "ok") { S.state = "error"; draw(); } })
      .then(function () { S.timer = setTimeout(load, REFRESH + Math.random() * 30000); });
  }

  $("lng").addEventListener("click", function () { S.lang = S.lang === "ar" ? "en" : "ar"; draw(); });
  document.addEventListener("visibilitychange", function () { if (!document.hidden && S.channel) load(); });
  var q = new URLSearchParams(location.search);
  if (/^ar/i.test(q.get("language") || "")) S.lang = "ar";       // the viewer's Twitch language, until the streamer's arrives
  draw();
  if (window.Twitch && window.Twitch.ext) {
    window.Twitch.ext.onAuthorized(function (auth) {
      var first = !S.channel;
      S.channel = String(auth.channelId || "");
      var v = window.Twitch.ext.viewer && window.Twitch.ext.viewer.id;
      S.viewer = v && /^\d+$/.test(String(v)) ? String(v) : "";
      if (first) load(); else draw();
    });
  }
})();
