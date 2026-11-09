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
.first{position:relative;overflow:hidden;display:flex;align-items:center;gap:calc(10px*var(--s));height:calc(46px*var(--s));
 padding:0 calc(18px*var(--s)) 0 calc(5px*var(--s));border-radius:999px;background:rgba(16,16,19,.96);border:1px solid color-mix(in srgb,var(--acc2) 45%,transparent);
 box-shadow:0 6px 18px rgba(0,0,0,.4),inset 0 0 calc(14px*var(--s)) color-mix(in srgb,var(--acc) 18%,transparent)}
[dir=rtl] .first{padding:0 calc(5px*var(--s)) 0 calc(18px*var(--s))}
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
if(q.get("column"))document.body.classList.add("col");if(EDIT)document.body.classList.add("edit");
var SIZE=parseFloat(q.get("size")||"1");if(!(SIZE>=0.5&&SIZE<=3))SIZE=1;
function scale(){document.body.style.setProperty("--s0",Math.max(0.35,(innerWidth||1920)/1920)*SIZE)}scale();addEventListener("resize",scale);
var showC=q.get("first")!="only",showF=q.get("first")!="0";
var COL={"☠":"#e0263a","🏆":"#f5a524","🎯":"#1f9cf0","💔":"#e84393","😡":"#f08a24","🤦":"#a371f7","🔥":"#f08a24"};
var TX={en:{who:"Who's first today?",type:"Type",first:"First today",row:"in a row",fic:"First in chat",picked:"{n} selected"},ar:{who:"مين أول واحد اليوم؟",type:"اكتب",first:"أول واحد اليوم",row:"ورا بعض",fic:"أول واحد في الشات",picked:"{n} محددة"}};
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
  if(!showF||!f){if(cur)cur.remove();firstKey=null;return}
  var key=f.won?"w:"+f.login+":"+f.streak+":"+(f.avatar?1:0):"wait:"+f.words.join(",")+lang;
  if(key!==firstKey){var wasWait=firstKey===null||String(firstKey).indexOf("wait")==0;firstKey=key;
    var d=document.createElement("div");d.dataset.key="first";d.dataset.label=tx("fic");
    if(!f.won){d.className="first";d.innerHTML='<div class="av"><div class="ph">?</div></div><div class="ft"><small>'+esc(tx("who"))+'</small><b style="font-weight:600">'+esc(tx("type"))+' '+f.words.map(function(w){return '<bdi class="kw">'+esc(w)+'</bdi>'}).join(" ")+'</b></div>'}
    else{var pic=f.avatar?'<img src="'+esc(f.avatar)+'" alt="">':'<div class="ph ini">'+esc(String(f.user).charAt(0).toUpperCase())+'</div>';
      d.className="first"+(wasWait?" won":"");d.innerHTML='<div class="shine"></div><div class="av">'+pic+'<span class="badge">1</span></div><div class="ft"><small>'+esc(tx("first"))+'</small><b><bdi>'+esc(f.user)+'</bdi></b>'+(f.streak>1?' <bdi class="st">🔥 '+f.streak+' '+esc(tx("row"))+'</bdi>':'')+'</div>'}
    if(cur){if(cur.classList.contains("abs")){d.classList.add("abs");d.style.left=cur.style.left;d.style.top=cur.style.top}setSize(d,cur.dataset.k);var i=SEL.indexOf(cur);if(i>=0){SEL[i]=d;d.classList.add("pick")}cur.replaceWith(d)}
    else{document.getElementById("z").appendChild(d);fresh(d)}cur=d;
    if(f.won&&wasWait)setTimeout(function(){sparks(d)},60)}
  setPlace(cur,f.pos)}
/* the Overlays page (?edit=1): click one to select it (Ctrl / Shift + click, or draw a box, for more), drag to move,
   drag a corner to make them bigger or smaller. They're solid: one can't go into another. */
var GAP=8;
function all(){return [].slice.call(document.querySelectorAll(".ctr,.first"))}
function rectOf(el){var r=el.getBoundingClientRect();return {l:r.left,t:r.top,r:r.right,b:r.bottom}}
function hits(a,b){return a.l<b.r+GAP&&a.r+GAP>b.l&&a.t<b.b+GAP&&a.b+GAP>b.t}
function blocked(els,move){var others=all().filter(function(o){return els.indexOf(o)<0}).map(rectOf);   // would any of them touch another?
  return els.some(function(el){var r=move(el);return r.l<0||r.t<0||r.r>innerWidth||r.b>innerHeight||others.some(function(o){return hits(r,o)})})}
function toAbs(el){if(el.classList.contains("abs")&&el.parentNode===document.getElementById("abs"))return;
  var r=el.getBoundingClientRect();el.classList.add("abs");el.style.left=r.left+"px";el.style.top=r.top+"px";document.getElementById("abs").appendChild(el)}
function L(el){var v=el.style.left;return v.slice(-1)=="%"?parseFloat(v)/100*innerWidth:parseFloat(v)}      // its place in px (saved ones are in %)
function T(el){var v=el.style.top;return v.slice(-1)=="%"?parseFloat(v)/100*innerHeight:parseFloat(v)}
function pct(el){return [+(L(el)/innerWidth*100).toFixed(2),+(T(el)/innerHeight*100).toFixed(2),+(+el.dataset.k||1).toFixed(2)]}
function save(els){var list=els.map(function(el){var p=pct(el);POS[el.dataset.key]={p:p,until:Date.now()+3000};el.style.left=p[0]+"%";el.style.top=p[1]+"%";return {key:el.dataset.key,x:p[0],y:p[1],k:p[2]}});
  try{parent.postMessage({fqpn:"overlay-pos",list:list},location.origin)}catch(_){}}
/* the first time one is touched, all of them get pinned where they are (so taking one out doesn't make the others slide up) */
function pinAll(){var flow=all().filter(function(el){return !el.classList.contains("abs")});if(!flow.length)return;
  var rs=flow.map(function(el){return el.getBoundingClientRect()});flow.forEach(function(el,i){el.classList.add("abs");el.style.left=rs[i].left+"px";el.style.top=rs[i].top+"px";document.getElementById("abs").appendChild(el)});save(flow)}
function pickOnly(list){SEL.forEach(function(el){el.classList.remove("pick")});SEL=list.filter(Boolean);SEL.forEach(function(el){el.classList.add("pick")})}
addEventListener("pointerdown",function(e){if(!EDIT)return;var h=e.target.closest("[data-h]");e.preventDefault();
  if(h&&SEL.length){pinAll();var box=union(SEL);RES={els:SEL.slice(),box:box,x:e.clientX,y:e.clientY,top:h.dataset.h=="tr",
      start:SEL.map(function(el){return {el:el,k:+el.dataset.k||1,l:L(el),t:T(el)}})};
    try{h.setPointerCapture(e.pointerId)}catch(_){}return}
  var el=e.target.closest(".ctr,.first");
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
  if(RES){var B=RES.box,w=B.r-B.l,hh=B.b-B.t,dx=e.clientX-RES.x,dy=RES.top?RES.y-e.clientY:e.clientY-RES.y,g=Math.max((w+dx)/w,(hh+dy)/hh);
    g=Math.max(0.5/Math.min.apply(null,RES.start.map(function(s){return s.k})),Math.min(3/Math.max.apply(null,RES.start.map(function(s){return s.k})),g));
    var prev=RES.start.map(function(s){return [s.el.dataset.k,s.el.style.left,s.el.style.top]});
    RES.start.forEach(function(s){setSize(s.el,(s.k*g).toFixed(3));s.el.style.left=(B.l+(s.l-B.l)*g)+"px";     // the group grows from its left edge,
      s.el.style.top=(RES.top?B.b-(B.b-s.t)*g:B.t+(s.t-B.t)*g)+"px"});                                    // and from its bottom (top handle) or top (bottom handle)
    if(blocked(RES.els,rectOf))RES.start.forEach(function(s,i){setSize(s.el,prev[i][0]);s.el.style.left=prev[i][1];s.el.style.top=prev[i][2]});   // it would touch another: stop growing
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
async function tick(){try{var r=await fetch("/api/overlay"+(q.get("only")?"?only="+encodeURIComponent(q.get("only")):""),{cache:"no-store"});
    if(r.ok){var d=await r.json();lang=d.lang=="ar"?"ar":"en";document.documentElement.dir=lang=="ar"?"rtl":"ltr";
      if(/^#[0-9a-f]{6}$/i.test(d.accent||""))document.body.style.setProperty("--acc",d.accent);
      if(d.v){if(VER&&VER!==d.v){location.reload();return}VER=d.v}
      ORDER=d.order||[];drawCounters(d.counters||[]);drawFirst(d.first);arrange();unstack()}}catch(e){}
  setTimeout(tick,EDIT?600:800)}
tick();
</script></body></html>"""


import hashlib as _h
VERSION = _h.sha1(OVERLAY_HTML.encode("utf-8")).hexdigest()[:10]   # changes with the app: an open overlay (OBS) reloads itself
