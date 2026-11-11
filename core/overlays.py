"""1.17.0: overlays for OBS (or any streaming app that has a "Browser Source").

The app serves them on this PC only (http://127.0.0.1:<port>/overlay/...), like the dashboard itself. The page is see-through,
asks the app for the numbers about once a second, and animates when one changes. Nothing goes to the internet.

/overlay        the counters switched on in Commands > Custom > Counters ("Show on stream"), in that order, and under them
                First in chat (who wrote first this stream, with their Twitch picture and streak), in the "slim pill" look
  ?only=deaths,wins   just these counters (one Browser Source per counter, to place each one anywhere)
  ?first=0            without First in chat;  ?first=only  only First in chat
  ?column=1           counters one under another instead of side by side
  ?size=1.5           bigger (0.5 to 3)
"""
import re

ICONS = [  # a counter's name -> its little picture (anything else gets none)
    (r"death|dead|die|موت|موتات|مات|وفيات", "☠"),
    (r"win|فوز|انتصار|فزت", "🏆"),
    (r"kill|كيل|قتل|قتلات", "🎯"),
    (r"loss|lose|خساره|خسارة|خسرت|هزيمه|هزيمة", "💔"),
    (r"rage|غضب|عصب|زعل", "😡"),
    (r"fail|فشل", "🤦"),
    (r"head|هيد", "🎯"),
    (r"clutch|كلتش", "🔥"),
]


def icon_for(name: str) -> str:
    n = str(name or "").lower()
    for rx, ic in ICONS:
        if re.search(rx, n):
            return ic
    return ""


OVERLAY_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Overlay · FQPN's Chat Bot</title>
<style>
html,body{margin:0;background:transparent;overflow:hidden;width:100%;height:100%}
body{font-family:'Outfit','Tajawal','Segoe UI',system-ui,sans-serif;color:#fff;--s0:1;--ui:1;--gold:#f5c451;--acc:#9a1118;position:relative;user-select:none;
 --acc2:color-mix(in srgb,var(--acc) 70%,#fff)}   /* --acc: the app's accent color (Settings > Look); --acc2: a lighter one for text on dark */
/* overlays without a place sit together in the top-left corner (top-right in Arabic); the others where they were put */
#z,.ctr,.first{--s:var(--s0)}   /* each overlay's size: the screen's scale times its own (set when it's resized on the Overlays page) */
#z{position:absolute;top:calc(18px*var(--s));inset-inline-start:calc(16px*var(--s));display:flex;flex-direction:column;gap:calc(10px*var(--s));align-items:flex-start}

.abs{position:absolute!important;width:max-content;right:auto;inset-inline-end:auto;margin:0}
/* Overlays page preview (?edit=1): drag them */
body.edit .ctr,body.edit .first{cursor:grab;outline:calc(1.5px*var(--ui)) dashed transparent;outline-offset:calc(5px*var(--ui))}
body.edit .ctr:hover,body.edit .first:hover{outline-color:rgba(255,255,255,.45)}
body.edit .drag{cursor:grabbing;z-index:9;transition:none;animation:none}
body.edit .pick{outline:calc(2px*var(--ui)) dashed var(--acc2)!important;outline-offset:calc(5px*var(--ui))}
#band{position:absolute;display:none;z-index:21;pointer-events:none;border:calc(1.5px*var(--ui)) solid var(--acc2);background:color-mix(in srgb,var(--acc) 18%,transparent);border-radius:calc(3px*var(--ui))}
#sel{position:absolute;display:none;pointer-events:none;z-index:20;border:calc(2px*var(--ui)) dashed var(--acc2);border-radius:calc(8px*var(--ui))}
#sel .tag{position:absolute;bottom:100%;inset-inline-start:calc(-2px*var(--ui));margin-bottom:calc(5px*var(--ui));background:var(--acc);color:#fff;
 font:600 calc(13px*var(--ui))/1.6 'Outfit','Tajawal','Segoe UI',sans-serif;padding:0 calc(8px*var(--ui));border-radius:calc(5px*var(--ui));white-space:nowrap}
#sel .h{position:absolute;width:calc(14px*var(--ui));height:calc(14px*var(--ui));background:var(--acc2);border:calc(2px*var(--ui)) solid #111;
 border-radius:calc(3px*var(--ui));pointer-events:auto;cursor:nwse-resize;right:calc(-9px*var(--ui));bottom:calc(-9px*var(--ui))}
#sel .h.tr{bottom:auto;top:calc(-9px*var(--ui));cursor:nesw-resize}
body.edit .ctr,body.edit .first,body.edit .abs{touch-action:none}
/* a counter: one slim pill */
.ctr{--h:calc(26px*var(--s));position:relative;display:flex;align-items:center;gap:calc(9px*var(--s));height:calc(40px*var(--s));
 padding:0 calc(16px*var(--s)) 0 calc(6px*var(--s));border-radius:999px;background:rgba(16,16,19,.96);border:1px solid color-mix(in srgb,var(--acc2) 45%,transparent);
 box-shadow:0 6px 18px rgba(0,0,0,.4),inset 0 0 calc(14px*var(--s)) color-mix(in srgb,var(--acc) 18%,transparent)}
.new{animation:in .45s cubic-bezier(.2,.9,.3,1.2)}   /* only when it first shows (not on every refresh) */
[dir=rtl] .ctr{padding:0 calc(6px*var(--s)) 0 calc(16px*var(--s))}
.ico{width:calc(30px*var(--s));height:calc(30px*var(--s));border-radius:50%;background:color-mix(in srgb,var(--acc) 45%,transparent);
 display:flex;align-items:center;justify-content:center;font-size:calc(16px*var(--s))}
.lab{font-size:calc(11.5px*var(--s));text-transform:uppercase;letter-spacing:1.4px;font-weight:600;color:color-mix(in srgb,var(--acc2) 45%,#fff 40%)}
[dir=rtl] .lab{letter-spacing:0;font-size:calc(13px*var(--s))}
.num{display:flex;overflow:hidden;font-weight:800;font-variant-numeric:tabular-nums;direction:ltr;height:var(--h);line-height:var(--h);font-size:calc(var(--h)*.9)}
.dig{display:flex;flex-direction:column;transition:transform .55s cubic-bezier(.2,.9,.25,1.15)}.dig span{height:var(--h)}
.plus{position:absolute;top:calc(-10px*var(--s));inset-inline-end:calc(6px*var(--s));font-weight:800;font-size:calc(12px*var(--s));color:#fff;
 background:var(--acc);border-radius:999px;padding:0 calc(7px*var(--s));opacity:0;pointer-events:none}
.plus.go{animation:plus .9s ease-out}
.hit{animation:hit .45s ease}.zero .num{animation:spin .6s ease}
/* First in chat: a slim pill too */
.first.over{opacity:.4}   /* 1.18.0: (only on the Overlays page) time's up: not on stream */
.first{position:relative;overflow:hidden;display:flex;align-items:center;gap:calc(10px*var(--s));height:calc(46px*var(--s));
 padding:0 calc(18px*var(--s)) 0 calc(5px*var(--s));border-radius:999px;background:rgba(16,16,19,.96);border:1px solid color-mix(in srgb,var(--acc2) 45%,transparent);
 box-shadow:0 6px 18px rgba(0,0,0,.4),inset 0 0 calc(14px*var(--s)) color-mix(in srgb,var(--acc) 18%,transparent)}
[dir=rtl] .first{padding:0 calc(5px*var(--s)) 0 calc(18px*var(--s))}
.first::before{content:"";position:absolute;left:calc(-30px*var(--s));top:50%;width:calc(120px*var(--s));height:calc(120px*var(--s));transform:translateY(-50%);border-radius:50%;
 background:radial-gradient(closest-side,color-mix(in srgb,var(--acc) 55%,transparent),color-mix(in srgb,var(--acc) 18%,transparent) 55%,transparent);pointer-events:none;filter:blur(calc(4px*var(--s)))}   /* 1.18.0: a soft glow behind the picture */
[dir=rtl] .first::before{left:auto;right:calc(-30px*var(--s))}
.first .ft{position:relative}
.first .ft b.fw{color:var(--acc2);text-shadow:0 0 calc(6px*var(--s)) var(--acc),0 0 calc(16px*var(--s)) color-mix(in srgb,var(--acc) 70%,transparent)}   /* the winner's name: the accent color, glowing */
.av{position:relative;flex:none;width:calc(36px*var(--s));height:calc(36px*var(--s))}
.av img,.av .ph{width:100%;height:100%;border-radius:50%;display:block;object-fit:cover;box-sizing:border-box;border:2px solid var(--acc2)}
.av .ph{display:flex;align-items:center;justify-content:center;background:#26262b;color:#888;font-weight:700;border-color:#3a3a40;font-size:calc(15px*var(--s));animation:breath 2s ease-in-out infinite}
.av .ini{background:linear-gradient(135deg,var(--acc),#111);color:#fff;border-color:var(--acc2);animation:none}
.badge{position:absolute;bottom:-3px;inset-inline-end:-3px;width:calc(16px*var(--s));height:calc(16px*var(--s));border-radius:50%;
 background:radial-gradient(circle at 35% 30%,#fff3c4,#f5c451 50%,#b8860b);color:#4a3200;font-weight:900;font-size:calc(9px*var(--s));
 display:flex;align-items:center;justify-content:center;border:1.5px solid #121214}
.ft{display:flex;align-items:baseline;gap:calc(8px*var(--s));font-size:calc(13px*var(--s));white-space:nowrap}
.ft small{color:rgba(255,255,255,.6);font-size:inherit}.ft b{font-size:calc(16px*var(--s))}
.st{font-size:calc(12px*var(--s));color:var(--acc2);font-weight:700}
.kw{display:inline-block;background:rgba(255,255,255,.12);border-radius:5px;padding:0 calc(6px*var(--s));margin:0 1px;font-weight:700;font-size:calc(13px*var(--s))}
.shine{position:absolute;inset:0;pointer-events:none;background:linear-gradient(105deg,transparent 35%,rgba(255,240,200,.35) 50%,transparent 65%);transform:translateX(-120%)}
.won{animation:pop .55s cubic-bezier(.2,1.5,.4,1)}.won .shine{animation:shine 1s .2s ease}
.spark{position:absolute;width:5px;height:5px;border-radius:50%;background:var(--acc2);pointer-events:none;animation:sp .9s ease-out forwards}
/* 1.18.0: the Chat box (core/chatbox.py): your chat on stream, view only. Sizes follow the screen (--s0) and its Text size. */
.cbox{position:absolute;box-sizing:border-box;--cbsize:22;--lh:1.5;--es:1.5;--lines:3;font-size:calc(var(--cbsize)*1px*var(--s0));line-height:var(--lh);
 font-family:var(--cbfont),'Segoe UI',system-ui,sans-serif;font-weight:500;color:#fff}
.cbin{position:absolute;inset:0;padding:.3em .4em;box-sizing:border-box;overflow:hidden;display:flex;flex-direction:column;justify-content:flex-end;gap:.3em}
.cbox.top .cbin{flex-direction:column-reverse;justify-content:flex-end}
.cm{position:relative;flex:none;max-width:100%;box-sizing:border-box;align-self:flex-start;text-align:start;overflow-wrap:anywhere}
.cbox .cm{direction:ltr;text-align:left}.cbox:not(.line) .cbin{direction:ltr}   /* 1.18.0: badges and name always on the left, an Arabic message still reads right to left after them */
.cm .body{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:var(--lines);overflow:hidden}
.cbox.lines0 .cm .body{display:block}
.cm .nm{font-weight:700}.cm .head{display:inline}
.cm .bd{display:inline-block;font-size:.62em;font-weight:700;padding:0 .4em;border-radius:.35em;margin-inline-end:.3em;vertical-align:.14em;line-height:1.55;
 -webkit-text-stroke:0;background:rgba(255,255,255,.18);color:#fff}
.cm .bd.mod{background:#1f8a3b}.cm .bd.vip{background:#e005b9}.cm .bd.sub{background:var(--acc)}.cm .bd.g{background:rgba(245,196,81,.24);color:#f5c451}
.cm .tb{height:1.05em;width:auto;vertical-align:-.17em;margin-inline-end:.28em;border-radius:.15em}
.cm .em{height:calc(var(--es)*.9em);vertical-align:middle;margin:0 .06em}.cm.big .em{height:calc(var(--es)*1.9em)}
.cm .mn{font-weight:700}
.cm .lk{color:#9fd3ff;text-decoration:underline}.cm .lkw{font-size:.8em;background:rgba(255,255,255,.16);border-radius:.3em;padding:0 .35em;-webkit-text-stroke:0}
.cm .rpl{font-size:.72em;opacity:.85;-webkit-text-stroke:0}
.cm .ans{font-size:.86em;margin-top:.12em;padding-inline-start:.7em;border-inline-start:.12em solid var(--acc2);color:#ffe0e3}
.cm .cnt{display:inline-block;font-size:.7em;background:var(--acc);border-radius:999px;padding:0 .5em;margin-inline-start:.4em;vertical-align:.12em;-webkit-text-stroke:0}
.cm .sh{display:inline-block;width:1.15em;height:1.15em;line-height:1.15em;text-align:center;font-size:.62em;border-radius:50%;background:linear-gradient(135deg,#6d5bd0,#2bb3c0);margin-inline-end:.3em;vertical-align:.18em;-webkit-text-stroke:0}
.cm .pic{width:1.3em;height:1.3em;border-radius:50%;vertical-align:-.3em;margin-inline-end:.35em;object-fit:cover;background:#333}
.cm .pi{display:inline-block;box-sizing:border-box;font-size:.62em;width:2.1em;height:2.1em;line-height:2.1em;text-align:center;font-weight:700;vertical-align:.05em;
 background:linear-gradient(135deg,var(--acc),#222);color:#fff;-webkit-text-stroke:0}
.cm .spk{-webkit-text-stroke:0;margin-inline-end:.15em}
.cm.fold{align-self:center!important;font-size:.85em;color:#f5c451;text-align:center}
.cm .dl{font-style:italic;opacity:.6}
.cm.cfirst .nm{text-decoration:underline .09em #4ade80;text-underline-offset:.22em}
.cm.mention{background:color-mix(in srgb,var(--acc) 38%,transparent)!important;border-radius:.4em;padding-left:.35em;padding-right:.35em}
.g-soft .cm .nm{text-shadow:0 0 .3em currentColor}.g-strong .cm .nm{text-shadow:0 0 .25em currentColor,0 0 .75em currentColor}
.o-thin .cm{-webkit-text-stroke:.15em rgba(0,0,0,.85);paint-order:stroke fill}.o-thick .cm{-webkit-text-stroke:.25em rgba(0,0,0,.9);paint-order:stroke fill}
.o-thin .cm .em,.o-thick .cm .em{-webkit-text-stroke:0}
.s-soft .cm{filter:drop-shadow(0 .08em .12em rgba(0,0,0,.7))}.s-strong .cm{filter:drop-shadow(0 .1em .2em rgba(0,0,0,.95)) drop-shadow(0 0 .1em rgba(0,0,0,.8))}
.st-neon.b-soft .cm{background:rgba(0,0,0,.38);border-radius:.4em;padding:.08em .45em}.st-neon.b-dark .cm{background:rgba(8,8,12,.8);border-radius:.4em;padding:.08em .45em}
.st-classic .cm{background:rgba(10,10,14,.66);border-radius:.4em;padding:.22em .55em}.st-classic.b-dark .cm{background:rgba(6,6,9,.88)}.st-classic.b-soft .cm{background:rgba(10,10,14,.45)}
.st-bubbles .cm{background:rgba(32,32,40,.88);border-radius:.85em;padding:.3em .7em;max-width:86%}
.st-bubbles .cm .head{display:block;font-size:.8em}.st-bubbles .cm .sep{display:none}
.st-bubbles .cm{border-end-start-radius:.2em}
.st-bubbles .cm.fold{background:rgba(0,0,0,.45)}
.st-glass .cm{background:rgba(255,255,255,.09);backdrop-filter:blur(.5em);border:1px solid rgba(255,255,255,.15);border-radius:.6em;padding:.3em .65em;align-self:stretch!important}
.st-glass .cm .head{display:block;font-size:.85em}.st-glass .cm .sep{display:none}.st-glass .cm.fold{border:0}
.st-cards .cm{background:rgba(14,14,18,.86);border-radius:.5em;padding:.35em .7em;border-inline-start:.2em solid var(--nc,#888);align-self:stretch!important}
.st-cards .cm .head{display:block;font-size:.8em;margin-bottom:.08em}.st-cards .cm .sep{display:none}
.st-cards .cm .ans{background:rgba(255,255,255,.06);border-radius:.35em;padding:.2em .5em;border:0;margin-top:.3em}.st-cards .cm.fold{border:0;background:rgba(0,0,0,.45)}
.st-cards.b-soft .cm{background:rgba(14,14,18,.6)}.st-cards.b-dark .cm{background:rgba(6,6,9,.94)}
.st-fade .cbin{gap:.12em}.st-fade .cm{align-self:stretch!important;padding:.22em .65em;background:linear-gradient(90deg,rgba(0,0,0,.75),rgba(0,0,0,0))}
.st-fade.b-dark .cm{background:linear-gradient(90deg,rgba(0,0,0,.9),rgba(0,0,0,.15))}
.st-fade .cm.fold{background:none}
.cbox.line.st-cards .cm,.cbox.line.st-fade .cm{align-self:center!important}
.cbox.a-slide .cm.cnew{animation:cbslide .35s ease-out}.cbox.a-fade .cm.cnew{animation:cbfade .4s ease-out}.cbox.a-pop .cm.cnew{animation:cbpop .35s cubic-bezier(.2,1.4,.4,1)}
.cm.bye{transition:opacity .45s;opacity:0!important}
/* one line: messages side by side, the newest at the end, the oldest slide off the start */
.cbox.line .cbin{flex-direction:row;align-items:center;justify-content:flex-end;flex-wrap:nowrap;gap:1.2em}
.cbox.line .cm{white-space:nowrap;align-self:center!important;max-width:none;flex:none}
.cbox.line .cm .body{display:inline}.cbox.line .cm .head{display:inline!important}.cbox.line .cm .sep{display:inline!important}
.cbox.line .cm .rpl{display:inline;margin-inline-end:.45em}.cbox.line .cm .ans{display:inline;margin:0;margin-inline-start:.55em;padding-inline-start:.5em}
.cbox.line.a-slide .cm.cnew{animation:cbslidex .35s ease-out}html[dir=rtl] .cbox.line.a-slide .cm.cnew{animation-name:cbslidexr}
@keyframes cbslidex{from{opacity:0;transform:translateX(1.5em)}}@keyframes cbslidexr{from{opacity:0;transform:translateX(-1.5em)}}
@keyframes cbslide{from{opacity:0;transform:translateY(.7em)}}@keyframes cbfade{from{opacity:0}}@keyframes cbpop{from{opacity:0;transform:scale(.85)}}
body.edit .cbox{cursor:grab;outline:calc(1.5px*var(--ui)) dashed rgba(255,255,255,.28);outline-offset:calc(4px*var(--ui))}
body.edit .cbox.offair .cbin,body.cbonly .cbox.offair .cbin{opacity:.4}
body.cbonly .cbox .off{position:absolute;top:6px;inset-inline-end:6px;font:600 12px/1.6 'Outfit','Tajawal',sans-serif;background:#222;color:#ddd;border-radius:4px;padding:0 7px;-webkit-text-stroke:0}
body.edit .cbox.pick{outline-color:transparent!important}
body.edit .cbox .off{position:absolute;top:calc(6px*var(--ui));inset-inline-end:calc(6px*var(--ui));font:600 calc(12px*var(--ui))/1.6 'Outfit','Tajawal',sans-serif;
 background:#222;color:#ddd;border-radius:calc(4px*var(--ui));padding:0 calc(7px*var(--ui));-webkit-text-stroke:0}
@keyframes in{from{opacity:0;transform:translateY(-8px) scale(.96)}}
@keyframes plus{0%{opacity:0;transform:translateY(6px) scale(.6)}20%{opacity:1;transform:none}100%{opacity:0;transform:translateY(-18px)}}
@keyframes hit{35%{transform:scale(1.07)}}
@keyframes spin{50%{transform:rotateX(90deg);color:var(--acc2)}}
@keyframes breath{50%{transform:scale(.9);opacity:.7}}
@keyframes pop{0%{transform:scale(.9);opacity:0}}
@keyframes shine{to{transform:translateX(120%)}}
@keyframes sp{to{transform:translate(var(--x),var(--y)) scale(.2);opacity:0}}
</style></head><body><div id="z"></div><div id="abs"></div><div id="band"></div><div id="sel"><span class="tag"></span><span class="h tr" data-h="tr"></span><span class="h" data-h="br"></span></div>
<script>
var q=new URLSearchParams(location.search),old={},firstKey=null,lang="en",EDIT=!!q.get("edit"),DRAG=null,RES=null,BAND=null,SEL=[],POS={},VER=null;
if(q.get("column"))document.body.classList.add("col");if(EDIT)document.body.classList.add("edit");if(q.get("cbonly"))document.body.classList.add("cbonly");
var SIZE=parseFloat(q.get("size")||"1");if(!(SIZE>=0.5&&SIZE<=3))SIZE=1;
var CBONLY=!!q.get("cbonly");    // 1.18.0: the Chat box's own preview next to its settings (only the chat box, filling the frame)
var CHATONLY=location.pathname=="/chat";   // 1.18.0: the Chat box's own link: only the chat box, filling the Browser Source (any scene, any size)
var PREVIEW_W=450;               // the preview shows it as if the Browser Source were this wide (the size the Overlays page suggests)
function scale(){if(CBONLY||CHATONLY)return;document.body.style.setProperty("--s0",Math.max(0.35,(innerWidth||1920)/1920)*SIZE)}scale();addEventListener("resize",scale);
var showC=q.get("first")!="only"&&!CBONLY&&!CHATONLY,showF=q.get("first")!="0"&&!CBONLY&&!CHATONLY;
var COL={"☠":"#e0263a","🏆":"#f5a524","🎯":"#1f9cf0","💔":"#e84393","😡":"#f08a24","🤦":"#a371f7","🔥":"#f08a24"};
var TX={en:{who:"Who's first today?",type:"Type",first:"First today",row:"in a row",fic:"First in chat",picked:"{n} selected",chat:"Chat box",off:"Hidden on stream",
  del:"Message deleted",link:"link",guess:"{n} guesses…",won:"{w} won 🏆"},
  ar:{who:"مين أول واحد اليوم؟",type:"اكتب",first:"أول واحد اليوم",row:"ورا بعض",fic:"أول واحد في الشات",picked:"{n} محددة",chat:"صندوق الشات",off:"مخفي عن البث",
  del:"رسالة محذوفة",link:"رابط",guess:"{n} تخمين…",won:"فاز {w} 🏆"}};
function tx(k){return TX[lang][k]}
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function digHtml(v){return String(v).split("").map(function(d){return '<div class="dig" style="transform:translateY(calc(var(--h)*-'+d+'))">'+[0,1,2,3,4,5,6,7,8,9].map(function(n){return '<span>'+n+'</span>'}).join("")+'</div>'}).join("")}
function setDigits(box,v){var ds=String(v).split("");
  while(box.children.length<ds.length)box.insertAdjacentHTML("afterbegin",digHtml(0));while(box.children.length>ds.length)box.firstChild.remove();
  requestAnimationFrame(function(){ds.forEach(function(d,i){box.children[i].style.transform="translateY(calc(var(--h)*-"+d+"))"})})}
function again(el,cls){el.classList.remove(cls);void el.offsetWidth;el.classList.add(cls)}
/* where each overlay goes: its saved place, or the column in the corner (in the order they were switched on) */
var ORDER=[];
function setSize(el,k){k=+k||1;el.dataset.k=k;if(k!=1)el.style.setProperty("--s","calc(var(--s0) * "+k+")");else el.style.removeProperty("--s")}
function busy(el){return (DRAG&&DRAG.els.indexOf(el)>=0)||(RES&&RES.els.indexOf(el)>=0)}
function setPlace(el,pos){if(busy(el))return;var key=el.dataset.key,just=POS[key];
  if(just&&Date.now()<just.until)pos=just.p;      // just dropped: stay there while the app saves it
  var abs=document.getElementById("abs"),z=document.getElementById("z");setSize(el,pos&&pos[2]);
  if(pos){el.classList.add("abs");el.style.left=pos[0]+"%";el.style.top=pos[1]+"%";if(el.parentNode!==abs)abs.appendChild(el)}
  else{if(el.classList.contains("abs")){el.classList.remove("abs");el.style.left=el.style.top=""}if(el.parentNode!==z)z.appendChild(el)}}
function arrange(){var z=document.getElementById("z"),want=ORDER.map(function(k){return z.querySelector(':scope>[data-key="'+CSS.escape(k)+'"]')}).filter(Boolean);
  [].forEach.call(z.children,function(el){if(want.indexOf(el)<0)want.push(el)});
  var same=want.length===z.children.length&&want.every(function(el,i){return z.children[i]===el});
  if(!same)want.forEach(function(el){z.appendChild(el)})}     // only when the order changed: moving one restarts its animation
function fresh(el){el.classList.add("new");el.addEventListener("animationend",function f(e){if(e.target===el&&e.animationName=="in"){el.classList.remove("new");el.removeEventListener("animationend",f)}})}
function counterEl(c){var el=document.querySelector('.ctr[data-key="c:'+CSS.escape(c.name)+'"]');if(el)return el;
  var d=document.createElement("div");d.className="ctr";d.dataset.key="c:"+c.name;d.dataset.label=c.name;
  d.innerHTML='<span class="ico">'+(c.icon||"#")+'</span><span class="lab"><bdi>'+esc(c.name)+'</bdi></span><div class="num">'+digHtml(c.value)+'</div><span class="plus"></span>';
  old[c.name]=c.value;fresh(d);return d}
function drawCounters(list){if(!showC)list=[];var keep={};
  list.forEach(function(c){var el=counterEl(c),was=old[c.name];keep["c:"+c.name]=1;setPlace(el,c.pos);
    if(was!==undefined&&was!==c.value){setDigits(el.querySelector(".num"),c.value);
      if(c.value>was){again(el,"hit");var p=el.querySelector(".plus");p.textContent="+"+(c.value-was);again(p,"go")}
      else if(c.value==0)again(el,"zero")}
    old[c.name]=c.value});
  document.querySelectorAll(".ctr").forEach(function(el){if(!keep[el.dataset.key])el.remove()})}
function sparks(card){var av=card.querySelector(".av");if(!av)return;var a=av.getBoundingClientRect(),f=card.getBoundingClientRect();
  for(var i=0;i<12;i++){var s=document.createElement("span");s.className="spark";var t=Math.random()*6.28,r=26+Math.random()*30;
    s.style.left=(a.left-f.left+a.width/2)+"px";s.style.top=(a.top-f.top+a.height/2)+"px";s.style.setProperty("--x",Math.cos(t)*r+"px");s.style.setProperty("--y",Math.sin(t)*r+"px");
    card.appendChild(s);setTimeout(function(x){x.remove()}.bind(null,s),950)}}
function drawFirst(f){var cur=document.querySelector(".first");
  if(!showF||!f||(f.over&&!EDIT)){if(cur)cur.remove();firstKey=null;return}   /* 1.18.0: time's up and nobody was first: gone */
  var key=f.won?"w:"+f.login+":"+f.streak+":"+(f.avatar?1:0):"wait:"+f.words.join(",")+lang+(f.over?":over":"");
  if(key!==firstKey){var wasWait=firstKey===null||String(firstKey).indexOf("wait")==0;firstKey=key;
    var d=document.createElement("div");d.dataset.key="first";d.dataset.label=tx("fic");
    if(!f.won){d.className="first"+(f.over?" over":"");d.innerHTML='<div class="av"><div class="ph">?</div></div><div class="ft"><small>'+esc(tx("who"))+'</small><b style="font-weight:600">'+esc(tx("type"))+' '+f.words.map(function(w){return '<bdi class="kw">'+esc(w)+'</bdi>'}).join(" ")+'</b></div>'}
    else{var pic=f.avatar?'<img src="'+esc(f.avatar)+'" alt="">':'<div class="ph ini">'+esc(String(f.user).charAt(0).toUpperCase())+'</div>';
      d.className="first"+(wasWait?" won":"");d.innerHTML='<div class="shine"></div><div class="av">'+pic+'<span class="badge">1</span></div><div class="ft"><small>'+esc(tx("first"))+'</small><b class="fw"><bdi>'+esc(f.user)+'</bdi></b>'+(f.streak>1?' <bdi class="st">🔥 '+f.streak+' '+esc(tx("row"))+'</bdi>':'')+'</div>'}
    if(cur){if(cur.classList.contains("abs")){d.classList.add("abs");d.style.left=cur.style.left;d.style.top=cur.style.top}setSize(d,cur.dataset.k);var i=SEL.indexOf(cur);if(i>=0){SEL[i]=d;d.classList.add("pick")}cur.replaceWith(d)}
    else{document.getElementById("z").appendChild(d);fresh(d)}cur=d;
    if(f.won&&wasWait)setTimeout(function(){sparks(d)},60)}
  setPlace(cur,f.pos)}
/* the Overlays page (?edit=1): click one to select it (Ctrl / Shift + click, or draw a box, for more), drag to move,
   drag a corner to make them bigger or smaller. They're solid: one can't go into another. */
var GAP=8;
function all(){return [].slice.call(document.querySelectorAll(".ctr,.first,.cbox"))}
function rectOf(el){var r=el.getBoundingClientRect();return {l:r.left,t:r.top,r:r.right,b:r.bottom}}
function hits(a,b){return a.l<b.r+GAP&&a.r+GAP>b.l&&a.t<b.b+GAP&&a.b+GAP>b.t}
function blocked(els,move){var others=all().filter(function(o){return els.indexOf(o)<0}).map(rectOf);   // would any of them touch another?
  return els.some(function(el){var r=move(el);return r.l<0||r.t<0||r.r>innerWidth||r.b>innerHeight||others.some(function(o){return hits(r,o)})})}
function toAbs(el){if(el.classList.contains("abs")&&el.parentNode===document.getElementById("abs"))return;
  var r=el.getBoundingClientRect();el.classList.add("abs");el.style.left=r.left+"px";el.style.top=r.top+"px";document.getElementById("abs").appendChild(el)}
function L(el){var v=el.style.left;return v.slice(-1)=="%"?parseFloat(v)/100*innerWidth:parseFloat(v)}      // its place in px (saved ones are in %)
function T(el){var v=el.style.top;return v.slice(-1)=="%"?parseFloat(v)/100*innerHeight:parseFloat(v)}
function pct(el){if(el.dataset.key=="chat")return [+(L(el)/innerWidth*100).toFixed(2),+(T(el)/innerHeight*100).toFixed(2),+(el.offsetWidth/innerWidth*100).toFixed(2),+(el.offsetHeight/innerHeight*100).toFixed(2)];
  return [+(L(el)/innerWidth*100).toFixed(2),+(T(el)/innerHeight*100).toFixed(2),+(+el.dataset.k||1).toFixed(2)]}
function save(els){var list=els.map(function(el){var p=pct(el);POS[el.dataset.key]={p:p,until:Date.now()+3000};el.style.left=p[0]+"%";el.style.top=p[1]+"%";
    if(el.dataset.key=="chat"){el.style.width=p[2]+"%";el.style.height=p[3]+"%";return {key:"chat",x:p[0],y:p[1],w:p[2],h:p[3]}}
    return {key:el.dataset.key,x:p[0],y:p[1],k:p[2]}});
  try{parent.postMessage({fqpn:"overlay-pos",list:list},location.origin)}catch(_){}}
/* the first time one is touched, all of them get pinned where they are (so taking one out doesn't make the others slide up) */
function pinAll(){var flow=all().filter(function(el){return !el.classList.contains("abs")});if(!flow.length)return;
  var rs=flow.map(function(el){return el.getBoundingClientRect()});flow.forEach(function(el,i){el.classList.add("abs");el.style.left=rs[i].left+"px";el.style.top=rs[i].top+"px";document.getElementById("abs").appendChild(el)});save(flow)}
function pickOnly(list){SEL.forEach(function(el){el.classList.remove("pick")});SEL=list.filter(Boolean);SEL.forEach(function(el){el.classList.add("pick")})}
addEventListener("pointerdown",function(e){if(!EDIT)return;var h=e.target.closest("[data-h]");e.preventDefault();
  if(h&&SEL.length){pinAll();var box=union(SEL);RES={els:SEL.slice(),box:box,x:e.clientX,y:e.clientY,top:h.dataset.h=="tr",
      start:SEL.map(function(el){return {el:el,k:+el.dataset.k||1,l:L(el),t:T(el),w:el.offsetWidth,h:el.offsetHeight}})};
    try{h.setPointerCapture(e.pointerId)}catch(_){}return}
  var el=e.target.closest(".ctr,.first,.cbox");
  if(!el){if(!(e.ctrlKey||e.shiftKey||e.metaKey))pickOnly([]);BAND={x:e.clientX,y:e.clientY,add:SEL.slice()};return}
  if(e.ctrlKey||e.shiftKey||e.metaKey){pickOnly(SEL.indexOf(el)>=0?SEL.filter(function(x){return x!==el}):SEL.concat([el]));return}
  if(SEL.indexOf(el)<0)pickOnly([el]);
  pinAll();DRAG={els:SEL.slice(),x:e.clientX,y:e.clientY,start:SEL.map(function(x){return [L(x),T(x)]}),dx:0,dy:0};
  DRAG.els.forEach(function(x){x.classList.add("drag")});try{el.setPointerCapture(e.pointerId)}catch(_){}});
function union(els){var u=null;els.forEach(function(el){var r=rectOf(el);u=u?{l:Math.min(u.l,r.l),t:Math.min(u.t,r.t),r:Math.max(u.r,r.r),b:Math.max(u.b,r.b)}:r});return u}
addEventListener("pointermove",function(e){
  if(BAND){var b=document.getElementById("band"),l=Math.min(BAND.x,e.clientX),t=Math.min(BAND.y,e.clientY),r=Math.max(BAND.x,e.clientX),bt=Math.max(BAND.y,e.clientY);
    b.style.display="block";b.style.left=l+"px";b.style.top=t+"px";b.style.width=(r-l)+"px";b.style.height=(bt-t)+"px";
    var box={l:l,t:t,r:r,b:bt};pickOnly(BAND.add.concat(all().filter(function(el){var x=rectOf(el);return x.l<box.r&&x.r>box.l&&x.t<box.b&&x.b>box.t&&BAND.add.indexOf(el)<0})));return}
  if(RES&&RES.els.length==1&&RES.els[0].dataset.key=="chat"){var c=RES.start[0],cx=e.clientX-RES.x,cy=RES.top?RES.y-e.clientY:e.clientY-RES.y,
      pw=c.el.style.width,ph=c.el.style.height,pt=c.el.style.top,nw=Math.max(120*SC(),c.w+cx),nh=Math.max(90*SC(),c.h+cy);    // the Chat box alone: any width and height
    c.el.style.width=nw+"px";c.el.style.height=nh+"px";if(RES.top)c.el.style.top=(c.t+c.h-nh)+"px";
    if(blocked(RES.els,rectOf)){c.el.style.width=pw;c.el.style.height=ph;c.el.style.top=pt}
    return}
  if(RES){var B=RES.box,w=B.r-B.l,hh=B.b-B.t,dx=e.clientX-RES.x,dy=RES.top?RES.y-e.clientY:e.clientY-RES.y,g=Math.max((w+dx)/w,(hh+dy)/hh);
    g=Math.max(0.5/Math.min.apply(null,RES.start.map(function(s){return s.k})),Math.min(3/Math.max.apply(null,RES.start.map(function(s){return s.k})),g));
    var prev=RES.start.map(function(s){return [s.el.dataset.k,s.el.style.left,s.el.style.top,s.el.style.width,s.el.style.height]});
    RES.start.forEach(function(s){if(s.el.dataset.key=="chat"){s.el.style.width=s.w*g+"px";s.el.style.height=s.h*g+"px"}else setSize(s.el,(s.k*g).toFixed(3));
      s.el.style.left=(B.l+(s.l-B.l)*g)+"px";     // the group grows from its left edge,
      s.el.style.top=(RES.top?B.b-(B.b-s.t)*g:B.t+(s.t-B.t)*g)+"px"});                                    // and from its bottom (top handle) or top (bottom handle)
    if(blocked(RES.els,rectOf))RES.start.forEach(function(s,i){if(s.el.dataset.key=="chat"){s.el.style.width=prev[i][3];s.el.style.height=prev[i][4]}else setSize(s.el,prev[i][0]);
      s.el.style.left=prev[i][1];s.el.style.top=prev[i][2]});   // it would touch another: stop growing
    return}
  if(!DRAG)return;var tx=e.clientX-DRAG.x,ty=e.clientY-DRAG.y;
  var at=function(dx,dy){return function(el){var i=DRAG.els.indexOf(el),r=el.getBoundingClientRect();var l=DRAG.start[i][0]+dx,t=DRAG.start[i][1]+dy;return {l:l,t:t,r:l+r.width,b:t+r.height}}};
  // move as far as it can: both ways, else only sideways or only up/down (so it slides along another one instead of going in)
  var nx=DRAG.dx,ny=DRAG.dy;
  if(!blocked(DRAG.els,at(tx,ty))){nx=tx;ny=ty}else if(!blocked(DRAG.els,at(tx,DRAG.dy)))nx=tx;else if(!blocked(DRAG.els,at(DRAG.dx,ty)))ny=ty;
  DRAG.dx=nx;DRAG.dy=ny;DRAG.els.forEach(function(el,i){el.style.left=(DRAG.start[i][0]+nx)+"px";el.style.top=(DRAG.start[i][1]+ny)+"px"})});
addEventListener("pointerup",function(){
  if(BAND){BAND=null;document.getElementById("band").style.display="none";return}
  if(RES){var els=RES.els;RES=null;save(els);return}
  if(!DRAG)return;var els=DRAG.els,moved=DRAG.dx||DRAG.dy;DRAG=null;els.forEach(function(el){el.classList.remove("drag")});if(moved)save(els)});
addEventListener("keydown",function(e){if(!EDIT||!SEL.length)return;
  if(e.key=="Escape"){pickOnly([]);return}
  var d={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];if(!d)return;e.preventDefault();pinAll();
  var st=e.shiftKey?10:2,els=SEL.slice(),mv=function(el){var r=rectOf(el);return {l:r.l+d[0]*st,t:r.t+d[1]*st,r:r.r+d[0]*st,b:r.b+d[1]*st}};
  if(blocked(els,mv))return;els.forEach(function(el){el.style.left=(el.getBoundingClientRect().left+d[0]*st)+"px";el.style.top=(el.getBoundingClientRect().top+d[1]*st)+"px"});save(els)});
addEventListener("message",function(e){if(e.origin===location.origin&&e.data&&e.data.fqpn=="pscale"&&e.data.k>0)document.body.style.setProperty("--ui",1/e.data.k)});
/* a newly switched-on one that lands on top of another (in the corner) finds a free spot by itself */
function unstack(){if(!EDIT||DRAG||RES)return;var placed=all().filter(function(el){return el.classList.contains("abs")});if(!placed.length)return;
  all().filter(function(el){return !el.classList.contains("abs")}).forEach(function(el){var r=el.getBoundingClientRect(),w=r.width,h=r.height;
    var free=function(l,t){var x={l:l,t:t,r:l+w,b:t+h};return !all().some(function(o){return o!==el&&o.classList.contains("abs")&&hits(x,rectOf(o))})};
    if(free(r.left,r.top))return;
    for(var t=16;t+h<innerHeight;t+=12)for(var l=16;l+w<innerWidth;l+=24)if(free(l,t)){el.classList.add("abs");el.style.left=l+"px";el.style.top=t+"px";document.getElementById("abs").appendChild(el);save([el]);return}})}
(function selLoop(){var b=document.getElementById("sel");SEL=SEL.filter(function(el){return el.isConnected});
  if(EDIT&&SEL.length&&!BAND){var u=union(SEL),k=parseFloat(getComputedStyle(document.body).getPropertyValue("--ui"))||1,pad=6*k;
    b.style.display="block";b.style.left=(u.l-pad)+"px";b.style.top=(u.t-pad)+"px";b.style.width=(u.r-u.l+pad*2)+"px";b.style.height=(u.b-u.t+pad*2)+"px";
    b.firstChild.textContent=SEL.length>1?TX[lang].picked.replace("{n}",SEL.length):(SEL[0].dataset.label||"")}
  else b.style.display="none";
  requestAnimationFrame(selLoop)})();
/* 1.18.0: the Chat box. Its place and size come from the app ([x, y, width, height] in %); the lines from core/chatbox.py */
function SC(){return Math.max(0.35,(innerWidth||1920)/1920)}
var CB={sig:"",font:"",off:0},FONTS={tajawal:["family=Tajawal:wght@400;500;700&family=Outfit:wght@400;500;600;700","'Tajawal','Outfit'"],
  cairo:["family=Cairo:wght@400;600;700","'Cairo'"],plex:["family=IBM+Plex+Sans+Arabic:wght@400;500;600","'IBM Plex Sans Arabic'"],kufi:["family=Noto+Kufi+Arabic:wght@400;500;600","'Noto Kufi Arabic'"],almarai:["family=Almarai:wght@400;700;800","'Almarai'"],readex:["family=Readex+Pro:wght@400;500;600;700","'Readex Pro'"],rubik:["family=Rubik:wght@400;500;600;700","'Rubik'"],changa:["family=Changa:wght@400;500;600;700","'Changa'"],messiri:["family=El+Messiri:wght@400;500;600;700","'El Messiri'"],baloo:["family=Baloo+Bhaijaan+2:wght@400;500;600;700","'Baloo Bhaijaan 2'"],lalezar:["family=Lalezar","'Lalezar'"],noto:["family=Noto+Sans+Arabic:wght@400;500;600;700&family=Noto+Sans:wght@400;500;600;700","'Noto Sans Arabic','Noto Sans'"]};
var FONTS_EN={outfit:["family=Outfit:wght@400;500;600;700","'Outfit'"],inter:["family=Inter:wght@400;500;600;700","'Inter'"],poppins:["family=Poppins:wght@400;500;600;700","'Poppins'"],
  montserrat:["family=Montserrat:wght@400;500;600;700","'Montserrat'"],nunito:["family=Nunito:wght@400;600;700;800","'Nunito'"],lexend:["family=Lexend:wght@400;500;600;700","'Lexend'"],fredoka:["family=Fredoka:wght@400;500;600;700","'Fredoka'"]};   /* 1.18.0: English letters in one font, Arabic in another (even in the same message) */
var PAL=["#FF4D4D","#5B8CFF","#3CC46A","#FF6B4A","#FF7F50","#9ACD32","#FF8C3A","#3DBE8B","#E3B341","#E08A3C","#5FB7C0","#3FA9FF","#FF69B4","#A77BFF","#2EE89A"];
function lighten(hex){var m=/^#?([0-9a-f]{6})$/i.exec(hex||"");if(!m)return "";var n=parseInt(m[1],16),r=n>>16,g=n>>8&255,b=n&255,l=(.299*r+.587*g+.114*b)/255;
  if(l>=.42)return "#"+m[1];var k=(.42-l)/.42*.75;r=Math.round(r+(255-r)*k);g=Math.round(g+(255-g)*k);b=Math.round(b+(255-b)*k);return "rgb("+r+","+g+","+b+")"}
function nameColor(row,cfg){if(cfg.name_color=="white")return "#fff";if(cfg.name_color=="accent")return "var(--acc2)";
  return lighten(row.color)||PAL[[].reduce.call(String(row.login||row.name),function(a,c){return (a*31+c.charCodeAt(0))>>>0},7)%PAL.length]}
function isRtl(txt){var m=/[A-Za-zÀ-ɏ֐-ࣿיִ-﷿ﹰ-﻿]/.exec(txt||"");return !!m&&/[֐-ࣿיִ-﷿ﹰ-﻿]/.test(m[0])}
var TWB={mod:"https://static-cdn.jtvnw.net/badges/v1/3267646d-33f0-4b17-b3df-f923a41db1d0/2",vip:"https://static-cdn.jtvnw.net/badges/v1/b817aba4-fad8-49e2-b88a-7cc744dfa6ec/2",
  streamer:"https://static-cdn.jtvnw.net/badges/v1/5527c58c-fb7d-422d-b71b-f309dcb85cc1/2",sub:"https://static-cdn.jtvnw.net/badges/v1/5d9f2208-5dd8-11e7-8513-2ff4adfae661/2"};
var SET2CODE={moderator:"mod",lead_moderator:"mod",vip:"vip",subscriber:"sub",founder:"sub",broadcaster:"streamer",partner:"partner",premium:"prime",turbo:"turbo",staff:"staff","artist-badge":"artist"};
function tbFail(){var t=this;if(t.dataset.fb){var sp=document.createElement("span");sp.className="bd "+(t.dataset.fc||"");sp.textContent=t.dataset.fb;t.replaceWith(sp)}else t.remove()}   // a badge picture that didn't load: its short name instead
var BADGE={mod:["MOD","mod"],vip:["VIP","vip"],sub:["SUB","sub"],streamer:["👑",""],partner:["✔",""],prime:["PRIME",""],turbo:["TURBO",""],staff:["STAFF",""],artist:["🎨",""]};
function cbParts(row,cfg){var left=cfg.max_chars,h="",plain="",onlyEm=true,any=false;
  (row.parts||[]).forEach(function(p){if(left<=0)return;var k=p[0];
    if(k=="e"&&(cfg.emotes||[]).indexOf(p[3])>=0){h+='<img class="em" src="'+esc(p[2])+'" alt="'+esc(p[1])+'">';left-=2;any=true;return}
    var txt=k=="e"?p[1]:String(p[1]);
    if(k=="l"){if(cfg.links=="hide")return;onlyEm=false;any=true;if(cfg.links=="word"){h+='<span class="lkw">'+esc(tx("link"))+'</span>';return}
      h+='<span class="lk">'+esc(txt.slice(0,left))+'</span>';left-=txt.length;plain+=txt;return}
    if(txt.trim())onlyEm=false;if(txt.trim())any=true;
    var cut=txt.length>left?txt.slice(0,left)+"…":txt;left-=txt.length;plain+=cut;
    h+=k=="m"?'<span class="mn">'+esc(cut)+'</span>':esc(cut)});
  return {h:h,plain:plain,emOnly:onlyEm&&any}}
function cbRow(row,cfg){var d=document.createElement("div");d.dataset.id=row.id;
  if(row.k=="fold"){d.className="cm fold";d.innerHTML="🎮 "+(row.game?'<bdi>'+esc(row.game)+'</bdi>: ':"")+'<bdi>'+esc(tx("guess").replace("{n}",row.n))+'</bdi>'+(row.winner?" "+esc(tx("won")).replace("{w}",'<bdi>'+esc(row.winner)+'</bdi>'):"");return d}
  var pr=row.k=="ans"?{h:"",plain:(row.answers||[]).join(" "),emOnly:false}:cbParts(row,cfg),rtl=isRtl(pr.plain||row.name);
  d.className="cm "+(rtl?"rtl":"ltr")+(row.first&&(cfg.app_badges||[]).indexOf("first")>=0?" cfirst":"")+(row.mention&&cfg.mention?" mention":"")+(pr.emOnly&&cfg.big_emotes?" big":"");
  d.removeAttribute("dir");   /* 1.18.0: badges and name always on the left, then the message */
  var app=row.app||{},b="",bw=cfg.badges||[];
  var tb=row.tb||(row.badges||[]).map(function(k){return [k,(CB.burls&&CB.burls[k])||TWB[k]||""]});     // the real Twitch badge pictures (made-up ones: Twitch's own)
  tb.forEach(function(x){var code=SET2CODE[x[0]]||x[0],grp=(code=="mod"||code=="vip"||code=="sub")?code:"other",f=BADGE[code];if(bw.indexOf(grp)<0)return;
    if(x[1])b+='<img class="tb" src="'+esc(x[1])+'" alt="" data-fb="'+esc(f?f[0]:"")+'" data-fc="'+(f?f[1]:"")+'">';
    else if(f)b+='<span class="bd '+f[1]+'">'+esc(f[0])+'</span>'});
  if(app.wins)b+='<span class="bd g">🏆 '+app.wins+'</span>';if(app.streak)b+='<span class="bd g">🥇 '+app.streak+'</span>';if(app.anniv)b+='<span class="bd g">🎂</span>';
  var nm=cfg.names=="login"?row.login:(cfg.names=="both"&&row.login&&String(row.name).toLowerCase()!=row.login?row.name+" ("+row.login+")":row.name);
  var head=(cfg.pics?(row.pic?'<img class="pic" src="'+esc(row.pic)+'" alt="">':'<span class="pic pi">'+esc(String(row.name||row.login||"?").charAt(0).toUpperCase())+'</span>'):"")+(row.shared?'<span class="sh">⇄</span>':"")+b+
    (row.first&&(cfg.app_badges||[]).indexOf("first")>=0?'<span class="spk">✨</span>':"")+'<span class="nm" style="color:'+nameColor(row,cfg)+'"><bdi>'+esc(nm)+'</bdi></span>';
  var h=row.reply?'<div class="rpl">↩ <bdi>'+esc(row.reply)+'</bdi></div>':"";
  if(row.k=="ans")h+=(row.answers||[]).map(function(a){return '<div class="body">🤖 '+esc(a)+'</div>'}).join("");
  else h+='<div class="body"><span class="head">'+head+'</span><span class="sep">: </span><span class="tx" dir="auto">'+(row.deleted?'<span class="dl">'+esc(tx("del"))+'</span>':pr.h)+'</span>'+(row.n>1?'<span class="cnt">×'+row.n+'</span>':"")+'</div>'+
    (row.answers||[]).map(function(a){return '<div class="ans">🤖 '+esc(a)+'</div>'}).join("");
  d.style.setProperty("--nc",nameColor(row,cfg));d.innerHTML=h;[].forEach.call(d.querySelectorAll("img.tb"),function(i){i.onerror=tbFail});return d}
function cbSamples(chat){var now=chat.now,rows=(chat.samples||[]).map(function(s,i){return {k:"msg",id:"s"+i,rev:1,t:now,name:s.name,login:s.login,color:s.color,badges:s.badges||[],
    parts:s.parts,first:!!s.first,reply:s.reply_to||"",app:{}}});
  rows.forEach(function(r){if(r.login=="sara_gg")r.app.wins=8;if(r.login=="fqpn_")r.app.streak=12;if(r.login=="auk78")r.answers=["discord.gg/fqpn"]});
  if(rows.length>3)rows.splice(3,0,{k:"fold",id:"sg",rev:1,t:now,game:"رتب",n:12,winner:"محمد"});
  if(!chat.cfg.replies)rows.forEach(function(r){r.reply=""});if(chat.cfg.commands=="hide")rows=rows.filter(function(r){return r.login!="auk78"});
  else if(chat.cfg.commands=="answer")rows.forEach(function(r){if(r.login=="auk78")r.k="ans"});if(!chat.cfg.attach)rows.forEach(function(r){if(r.k=="msg")delete r.answers});
  if(!chat.cfg.fold_games)rows=rows.filter(function(r){return r.k!="fold"});return rows}
/* the Chat box's own preview (?cbonly=1): made-up chat, one message every 2 seconds, so every setting can be seen moving */
var FEED={rows:[],i:0,seq:0};
var LONG={en:"ok so here's the whole story: yesterday I queued ranked for six hours straight, lost the first five games because my team kept rushing B with no utility, then we finally got a duo that actually talked, won seven in a row, climbed back to where I started and honestly that felt better than ranking up. anyway this stream is the best part of my day, keep going and don't tilt!!",
  ar:"طيب خلني أقول لكم القصة كاملة: أمس لعبت رانكد ست ساعات ورا بعض، خسرت أول خمس قيمات لأن الفريق كل مرة يدخل بي بدون أي أدوات، وبعدين أخيرا جانا دو يتكلمون ويتفاهمون، فزنا سبع قيمات ورا بعض ورجعت لنفس الرانك اللي بديت فيه، وصدقوني هالشي كان أحلى من إني أرتفع رانك. المهم هالبث أحلى شي في يومي، كمّل ولا تعصب أبد وخلك رايق مثل ما أنت دايم يا فقبن والله"};
function feedPool(){var ar=lang=="ar",kap="https://static-cdn.jtvnw.net/emoticons/v2/25/default/dark/3.0";return [
  {login:"fqpn_",name:"فقبن",color:"#FF6B6B",badges:["streamer"],parts:[["t","عيش حياتك برغبتك ومباديك"]],app:{streak:12}},
  {login:"sara_gg",name:"sara_gg",color:"#7CC4FF",badges:["sub"],parts:[["t","gg that clutch was insane 🔥"]],app:{wins:8}},
  {login:"auk78",name:"auk78",color:"#C39BFF",badges:["vip"],cmd:1,parts:[["t","!discord"]],answers:["discord.gg/fqpn"]},
  {login:"newguy",name:"newguy",color:"#9BE59B",first:1,parts:[["t",ar?"أول مرة أدخل، وش اللعبة؟":"first time here, what game is this?"]]},
  {login:"mod_ali",name:"mod_ali",color:"#5BD38A",badges:["mod"],reply:"newguy",parts:[["t",ar?"حياك الله، فالورانت":"welcome! it's Valorant"]]},
  {login:"abood",name:"عبود",color:"#FFB86B",parts:[["t",ar?"كل الأوامر هنا ":"all the commands are here "],["l","fqpnbot.com/fqpn_"]]},
  {spam:"W",login:"v1",name:"v1"},{spam:"W",login:"v2",name:"v2"},{spam:"W",login:"v3",name:"v3"},
  {login:"long_writer",name:"long_writer",color:"#A77BFF",badges:["sub"],parts:[["t",LONG[ar?"ar":"en"]]]},
  {login:"nightbot",name:"Nightbot",bot:1,color:"#7C7CFF",parts:[["t",ar?"تابعوا الحسابات!":"Follow the socials!"]]},
  {fold:1,game:"رتب",n:12,winner:"محمد"},
  {login:"rami",name:"رامي",color:"#FF69B4",mention:1,parts:[["t","@fqpn_ "+(ar?"متى البث الجاي؟":"when's the next stream?")]]},
  {login:"emote_fan",name:"emote_fan",color:"#3FA9FF",parts:[["e","Kappa",kap,"twitch"],["t"," "],["e","Kappa",kap,"twitch"]]},
  {login:"lina",name:"لينا",color:"#E3B341",badges:["vip"],app:{anniv:true},parts:[["t",ar?"صار لي سنة أتابعك اليوم 🎂":"one year following you today 🎂"]]}]}
function feedAdd(){var pool=feedPool(),m=pool[FEED.i%pool.length];FEED.i++;FEED.seq++;var now=Date.now()/1000;
  if(m.spam){var last=FEED.rows[FEED.rows.length-1];if(last&&last.spam==m.spam){last.n=(last.n||1)+1;last.rev++;last.t=now;return}
    FEED.rows.push({k:"msg",id:"f"+FEED.seq,rev:1,t:now,name:m.name,login:m.login,color:"#9ACD32",badges:[],parts:[["t",m.spam]],spam:m.spam,n:1,app:{}})}
  else if(m.fold)FEED.rows.push({k:"fold",id:"f"+FEED.seq,rev:1,t:now,game:m.game,n:m.n,winner:m.winner});
  else FEED.rows.push({k:"msg",id:"f"+FEED.seq,rev:1,t:now,name:m.name,login:m.login,color:m.color,badges:m.badges||[],parts:m.parts,first:!!m.first,reply:m.reply||"",
    mention:!!m.mention,app:m.app||{},answers:m.answers,cmd:!!m.cmd,bot:!!m.bot});
  if(FEED.rows.length>40)FEED.rows.shift()}
function feedRows(cfg){var out=[];FEED.rows.forEach(function(r){r=Object.assign({},r);
    if(r.bot&&cfg.hide_bots)return;if(r.k=="fold"&&!cfg.fold_games)return;
    if(r.spam&&!cfg.spam){for(var i=0;i<(r.n||1);i++)out.push(Object.assign({},r,{id:r.id+"_"+i,n:1}));return}
    if(r.cmd){if(cfg.commands=="hide")return;if(cfg.commands=="answer"){r.k="ans";r.parts=[]}else if(!cfg.attach)delete r.answers}
    if(!cfg.replies)r.reply="";out.push(r)});return out}
function cbPlace(el,box){if(busy(el))return;var just=POS.chat;if(just&&Date.now()<just.until&&just.p.length==4)box=just.p;
  el.style.left=box[0]+"%";el.style.top=box[1]+"%";el.style.width=box[2]+"%";el.style.height=box[3]+"%"}
function drawChat(chat){var el=document.querySelector(".cbox");
  if(!chat||q.get("chat")=="0"){if(el)el.remove();return}
  var cfg=chat.cfg;if(chat.burls){CB.burls=CB.burls||{};for(var bk in chat.burls)if(chat.burls[bk])CB.burls[bk]=chat.burls[bk]}
  if(!el){el=document.createElement("div");el.className="cbox";el.dataset.key="chat";el.innerHTML='<div class="cbin"></div>';document.getElementById("abs").appendChild(el)}
  el.dataset.label=tx("chat");
  el.style.left=el.style.top="0";el.style.width=el.style.height="100%";       // it fills its page: OBS decides where it goes and how big
  document.body.style.setProperty("--s0",CBONLY?innerWidth/(cfg.shape=="line"?650:PREVIEW_W):1);   // (one line: as if 650 wide, so a few messages fit and stay readable)       // (its text size is in pixels of the Browser Source)
  var fa=FONTS[cfg.font]||FONTS.tajawal,fe=FONTS_EN[cfg.font_en],f=fe?[fe[0]+"&"+fa[0],fe[1]+","+fa[1]]:fa,fk=cfg.font+"|"+(fe?cfg.font_en:"");
  if(CB.font!==fk){CB.font=fk;var lk=document.getElementById("cbfont");if(!lk){lk=document.createElement("link");lk.id="cbfont";lk.rel="stylesheet";document.head.appendChild(lk)}
    lk.href="https://fonts.googleapis.com/css2?"+f[0]+"&display=swap"}
  el.className="cbox abs st-"+cfg.style+" g-"+cfg.glow+" o-"+cfg.outline+" s-"+cfg.shadow+" b-"+cfg.bg+" a-"+cfg.anim+(cfg.shape=="line"?" line":cfg.flow=="top"?" top":"")+(cfg.lines?"":" lines0")+
    (cfg.hidden?" offair":"")+(SEL.indexOf(el)>=0?" pick":"")+(el.classList.contains("drag")?" drag":"");
  el.style.setProperty("--cbsize",cfg.size);el.style.setProperty("--lh",cfg.spacing);el.style.setProperty("--es",cfg.emote_size);el.style.setProperty("--lines",cfg.lines||99);el.style.setProperty("--cbfont",f[1]);
  el.style.display=(cfg.hidden&&!EDIT&&!CBONLY)?"none":"";
  var tag=el.querySelector(".off");if((EDIT||CBONLY)&&cfg.hidden){if(!tag){tag=document.createElement("span");tag.className="off";el.appendChild(tag)}tag.textContent=tx("off")}else if(tag)tag.remove();
  var sig=JSON.stringify(cfg)+lang,box=el.querySelector(".cbin");if(sig!==CB.sig){CB.sig=sig;box.innerHTML=""}
  var off=Date.now()/1000-chat.now,now=Date.now()/1000-off,rows=chat.items||[];
  if(CBONLY&&!FEED.on){FEED.on=1;for(var fi=0;fi<6;fi++)feedAdd();setInterval(feedAdd,2000)}   // (started once the language is known)
  if(CBONLY&&!rows.length)rows=feedRows(cfg);          // its own preview: made-up chat that keeps coming in
  else if(EDIT&&!rows.length)rows=cbSamples(chat);
  if(!EDIT&&!CBONLY)rows=rows.filter(function(r){var age=now-r.t;return age>=cfg.delay&&(!cfg.hide_after||age<cfg.hide_after+cfg.delay)});
  rows=rows.slice(-cfg.max);
  var want={},have={},full=rows.length>=cfg.max;rows.forEach(function(r){want[r.id]=r});
  var was={};if(cfg.anim!="none")[].forEach.call(box.children,function(c){if(!c.classList.contains("bye")){var b=c.getBoundingClientRect();was[c.dataset.id]=[b.left,b.top]}});
  [].slice.call(box.children).forEach(function(c){var r=want[c.dataset.id];
    if(!r){if(full)c.remove();                                  // pushed out by a new one: gone at once (fading it kept its space: the chat jumped)
      else if(!c.classList.contains("bye")){c.classList.add("bye");c.dataset.id="_"+c.dataset.id;setTimeout(function(){c.remove()},450)}}   // time's up, deleted…: fades out where it is
    else if(c.dataset.rev!=String(r.rev))c.remove();          // changed (an answer, a count…): drawn again in its place
    else have[r.id]=c});
  var prev=null;rows.forEach(function(r,i){var c=have[r.id];
    if(!c){c=cbRow(r,cfg);c.dataset.rev=r.rev;var isNew=!CB.seen||!CB.seen[r.id];if(isNew&&CB.sig0)c.classList.add("cnew");}
    var at=prev?prev.nextSibling:box.firstChild;while(at&&at!==c&&at.classList.contains("bye"))at=at.nextSibling;   // (a fading one keeps its place)
    if(at!==c)box.insertBefore(c,at);
    prev=c;c.style.opacity=cfg.fade_old&&rows.length>3?String(Math.max(.45,1-.55*(rows.length-1-i)/Math.max(1,cfg.max-1))):""});
  rows.forEach(function(r){var c=have[r.id],p=c&&was[r.id];if(!p)return;var b=c.getBoundingClientRect(),dx=p[0]-b.left,dy=p[1]-b.top;   // the others glide to their new place
    if(Math.abs(dx)<1&&Math.abs(dy)<1)return;c.style.transition="none";c.style.transform="translate("+dx+"px,"+dy+"px)";c.offsetWidth;
    c.style.transition="transform .3s ease";c.style.transform=""});
  CB.seen={};rows.forEach(function(r){CB.seen[r.id]=1});CB.sig0=true}
async function tick(){try{var r=await fetch("/api/overlay"+(q.get("only")?"?only="+encodeURIComponent(q.get("only")):(CBONLY?"?edit=1&cb=1":CHATONLY?"?chat=1":EDIT?"?edit=1":"")),{cache:"no-store"});
    if(r.ok){var d=await r.json();lang=d.lang=="ar"?"ar":"en";document.documentElement.dir=lang=="ar"?"rtl":"ltr";
      if(/^#[0-9a-f]{6}$/i.test(d.accent||""))document.body.style.setProperty("--acc",d.accent);
      if(d.v){if(VER&&VER!==d.v){location.reload();return}VER=d.v}
      ORDER=d.order||[];drawCounters(d.counters||[]);drawFirst(d.first);try{drawChat(d.chat)}catch(e){console.log(e)}arrange();unstack()}}catch(e){}
  setTimeout(tick,EDIT?600:800)}
tick();
</script></body></html>"""


import hashlib as _h
VERSION = _h.sha1(OVERLAY_HTML.encode("utf-8")).hexdigest()[:10]   # changes with the app: an open overlay (OBS) reloads itself
