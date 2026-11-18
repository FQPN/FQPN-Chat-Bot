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
 padding:0 calc(18px*var(--s)) 0 calc(5px*var(--s))}
[dir=rtl] .first{padding:0 calc(5px*var(--s)) 0 calc(18px*var(--s))}
/* 1.19.0: ten looks (Overlays > First in chat > Style). Everything above is shared; each look below only changes how it looks. */
.fs-pill{border-radius:999px;background:rgba(16,16,19,.96);border:1px solid color-mix(in srgb,var(--acc2) 45%,transparent);
 box-shadow:0 6px 18px rgba(0,0,0,.4),inset 0 0 calc(14px*var(--s)) color-mix(in srgb,var(--acc) 18%,transparent)}
.fs-pill::before{content:"";position:absolute;left:calc(-30px*var(--s));top:50%;width:calc(120px*var(--s));height:calc(120px*var(--s));transform:translateY(-50%);border-radius:50%;
 background:radial-gradient(closest-side,color-mix(in srgb,var(--acc) 55%,transparent),color-mix(in srgb,var(--acc) 18%,transparent) 55%,transparent);pointer-events:none;filter:blur(calc(4px*var(--s)))}   /* 1.18.0: a soft glow behind the picture */
[dir=rtl] .fs-pill::before{left:auto;right:calc(-30px*var(--s))}
/* --- Bow: bows, hearts and a rose frame (the Chat box has a matching one) --- */
.fs-bow{overflow:visible;border-radius:calc(25px*var(--s));padding:0 calc(22px*var(--s)) 0 calc(10px*var(--s));
 background:linear-gradient(170deg,#fffafc,#ffe8f0 70%,#ffdbe7);border:calc(2px*var(--s)) solid #e5536f;
 box-shadow:0 0 0 calc(3.5px*var(--s)) #fff6f8,0 0 0 calc(5px*var(--s)) rgba(229,83,111,.4),0 calc(8px*var(--s)) calc(20px*var(--s)) rgba(180,40,75,.38)}
[dir=rtl] .fs-bow{padding:0 calc(10px*var(--s)) 0 calc(22px*var(--s))}
.fs-bow::after{content:"";position:absolute;top:calc(-20px*var(--s));inset-inline-end:calc(-11px*var(--s));width:calc(42px*var(--s));height:calc(33px*var(--s));
 background:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2064%2050%22%3E%3Cg%20fill%3D%22%23fbbccd%22%20stroke%3D%22%23e5536f%22%20stroke-width%3D%223.2%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M29%2027C26%2034%2022%2041%2018.5%2048L25.5%2046.5C27.5%2040%2030.5%2033.5%2031.5%2028.5Z%22%2F%3E%3Cpath%20d%3D%22M35%2027C38%2034%2042%2041%2045.5%2048L38.5%2046.5C36.5%2040%2033.5%2033.5%2032.5%2028.5Z%22%2F%3E%3Cpath%20fill%3D%22%23f9a8bf%22%20d%3D%22M30.5%2020C19%205.5%204%207.5%206%2020C7.5%2029.5%2020%2030.5%2030.5%2026.5Z%22%2F%3E%3Cpath%20fill%3D%22%23f9a8bf%22%20d%3D%22M33.5%2020C45%205.5%2060%207.5%2058%2020C56.5%2029.5%2044%2030.5%2033.5%2026.5Z%22%2F%3E%3Crect%20fill%3D%22%23fcc9d7%22%20x%3D%2227.6%22%20y%3D%2217.6%22%20width%3D%228.8%22%20height%3D%2211%22%20rx%3D%223.4%22%2F%3E%3C%2Fg%3E%3Cg%20fill%3D%22none%22%20stroke%3D%22%23e5536f%22%20stroke-width%3D%222.1%22%20stroke-linecap%3D%22round%22%20opacity%3D%22.75%22%3E%3Cpath%20d%3D%22M12%2014C16%2013%2022%2016%2026%2021%22%2F%3E%3Cpath%20d%3D%22M52%2014C48%2013%2042%2016%2038%2021%22%2F%3E%3C%2Fg%3E%3C%2Fsvg%3E") no-repeat center/contain;transform:rotate(13deg);z-index:3;pointer-events:none;
 filter:drop-shadow(0 calc(2px*var(--s)) calc(4px*var(--s)) rgba(150,30,60,.45))}
[dir=rtl] .fs-bow::after{transform:rotate(-13deg)}
.fs-bow .av{width:calc(38px*var(--s));height:calc(38px*var(--s))}
.fs-bow .av img,.fs-bow .av .ph{border-color:#e5536f;box-shadow:0 0 0 calc(2px*var(--s)) #fff}
.fs-bow .av .ph{background:#ffd9e4;color:#d98ca3}
.fs-bow .av .ini{background:linear-gradient(140deg,#ff9bb8,#e5536f);color:#fff}
.fs-bow .badge{width:calc(25px*var(--s));height:calc(25px*var(--s));bottom:calc(-9px*var(--s));inset-inline-end:calc(-11px*var(--s));border:0;
 background:radial-gradient(circle at 40% 28%,#ffa8c0,#ff5f87 58%,#e02a55);color:#fff;font-size:calc(12px*var(--s));padding-bottom:calc(3px*var(--s));
 -webkit-mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2022%22%3E%3Cpath%20d%3D%22M12%2021.5C3.6%2015.2.5%2010.6.5%206.9A6.4%206.4%200%200%201%2012%203.6%206.4%206.4%200%200%201%2023.5%206.9C23.5%2010.6%2020.4%2015.2%2012%2021.5Z%22%20fill%3D%22%23000%22%2F%3E%3C%2Fsvg%3E");mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2022%22%3E%3Cpath%20d%3D%22M12%2021.5C3.6%2015.2.5%2010.6.5%206.9A6.4%206.4%200%200%201%2012%203.6%206.4%206.4%200%200%201%2023.5%206.9C23.5%2010.6%2020.4%2015.2%2012%2021.5Z%22%20fill%3D%22%23000%22%2F%3E%3C%2Fsvg%3E");-webkit-mask-size:100% 100%;mask-size:100% 100%}
.fs-bow .ft small{color:#c2577a}
.fs-bow .ft b{color:#b8375a}
.fs-bow .ft b.fw{color:#b8375a;text-shadow:none}
.fs-bow .st{color:#d9557c}
.fs-bow .kw{background:#ffd3e0;color:#b8375a;border:calc(1.5px*var(--s)) solid #f3889f;border-radius:calc(7px*var(--s))}
.fs-bow .shine{background:linear-gradient(105deg,transparent 35%,rgba(255,255,255,.6) 50%,transparent 65%)}
.fs-bow .spark{background:#ff6f9a;width:calc(6px*var(--s));height:calc(6px*var(--s))}
.fs-bow.won::before{content:"";position:absolute;inset-inline-start:42%;bottom:calc(30px*var(--s));width:calc(14px*var(--s));height:calc(13px*var(--s));
 background:#ff6f9a;-webkit-mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2022%22%3E%3Cpath%20d%3D%22M12%2021.5C3.6%2015.2.5%2010.6.5%206.9A6.4%206.4%200%200%201%2012%203.6%206.4%206.4%200%200%201%2023.5%206.9C23.5%2010.6%2020.4%2015.2%2012%2021.5Z%22%20fill%3D%22%23000%22%2F%3E%3C%2Fsvg%3E");mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2022%22%3E%3Cpath%20d%3D%22M12%2021.5C3.6%2015.2.5%2010.6.5%206.9A6.4%206.4%200%200%201%2012%203.6%206.4%206.4%200%200%201%2023.5%206.9C23.5%2010.6%2020.4%2015.2%2012%2021.5Z%22%20fill%3D%22%23000%22%2F%3E%3C%2Fsvg%3E");-webkit-mask-size:100% 100%;mask-size:100% 100%;
 pointer-events:none;animation:heartup 3.2s ease-in-out infinite}
@keyframes heartup{0%{opacity:0;transform:translateY(0) scale(.7) rotate(-8deg)}18%{opacity:1}70%{opacity:.6}
 100%{opacity:0;transform:translateY(calc(-40px*var(--s))) scale(1.1) rotate(12deg)}}

/* --- Neon: glowing tube letters, no picture --- */
.fs-neon{border-radius:calc(10px*var(--s));background:rgba(8,8,12,.82);border:calc(2px*var(--s)) solid var(--acc2);padding:0 calc(22px*var(--s));
 box-shadow:0 0 calc(4px*var(--s)) var(--acc2),0 0 calc(16px*var(--s)) var(--acc),inset 0 0 calc(16px*var(--s)) color-mix(in srgb,var(--acc) 45%,transparent)}
[dir=rtl] .fs-neon{padding:0 calc(22px*var(--s))}
.fs-neon .av{display:none}
.fs-neon .ft small{color:#fff;text-shadow:0 0 calc(7px*var(--s)) var(--acc2),0 0 calc(18px*var(--s)) var(--acc)}
.fs-neon .ft b.fw{color:#fff;text-shadow:0 0 calc(5px*var(--s)) #fff,0 0 calc(14px*var(--s)) var(--acc2),0 0 calc(30px*var(--s)) var(--acc)}
.fs-neon .kw{background:transparent;border:1px solid var(--acc2);box-shadow:0 0 calc(8px*var(--s)) color-mix(in srgb,var(--acc) 60%,transparent)}

/* --- Podium: a gold number 1 plate on the side --- */
.fs-podium{border-radius:calc(10px*var(--s));background:#141418;border:1px solid #2b2b33;box-shadow:0 8px 22px rgba(0,0,0,.45);
 gap:0;padding:0 calc(20px*var(--s)) 0 0}
[dir=rtl] .fs-podium{padding:0 0 0 calc(20px*var(--s))}
.fs-podium::before{content:"1";position:static;flex:none;align-self:stretch;width:calc(46px*var(--s));display:flex;align-items:center;justify-content:center;
 font-weight:900;font-style:italic;font-size:calc(25px*var(--s));color:#3a2a00;margin-inline-end:calc(11px*var(--s));
 background:linear-gradient(160deg,#ffe9a8,var(--gold) 45%,#b8860b);text-shadow:0 1px 0 rgba(255,255,255,.45)}
.fs-podium .av{margin-inline-end:calc(10px*var(--s))}
.fs-podium .av img,.fs-podium .av .ph{border-color:var(--gold)}
.fs-podium .badge{display:none}
.fs-podium .ft b.fw{color:var(--gold);text-shadow:0 0 calc(10px*var(--s)) rgba(245,196,81,.55)}
.fs-podium .st{color:var(--gold)}

/* --- Ticket: a paper ticket with punched sides --- */
.fs-ticket{background:linear-gradient(#f7f3e7,#e7e0cc);color:#2a2419;border-radius:calc(6px*var(--s));box-shadow:0 8px 20px rgba(0,0,0,.45);
 padding:0 calc(22px*var(--s)) 0 calc(14px*var(--s));
 -webkit-mask-image:radial-gradient(circle at 0 50%,transparent calc(8px*var(--s)),#000 calc(8.5px*var(--s))),radial-gradient(circle at 100% 50%,transparent calc(8px*var(--s)),#000 calc(8.5px*var(--s)));
 -webkit-mask-composite:source-in;
 mask-image:radial-gradient(circle at 0 50%,transparent calc(8px*var(--s)),#000 calc(8.5px*var(--s))),radial-gradient(circle at 100% 50%,transparent calc(8px*var(--s)),#000 calc(8.5px*var(--s)));
 mask-composite:intersect}
[dir=rtl] .fs-ticket{padding:0 calc(14px*var(--s)) 0 calc(22px*var(--s))}
.fs-ticket .ft small{color:#7a6f57}
.fs-ticket .ft b{color:#2a2419}
.fs-ticket .ft b.fw{color:#9a1118;text-shadow:none}
.fs-ticket .st{color:#9a1118}
.fs-ticket .av img,.fs-ticket .av .ph{border-color:#2a2419}
.fs-ticket .av .ph{background:#d8d0ba;color:#6d6451}
.fs-ticket .kw{background:rgba(42,36,25,.14);color:#2a2419}
.fs-ticket .shine{background:linear-gradient(105deg,transparent 35%,rgba(255,255,255,.65) 50%,transparent 65%)}

/* --- Terminal: green on black, like a console --- */
.fs-terminal{border-radius:calc(7px*var(--s));background:rgba(4,10,6,.92);border:1px solid #1d3b25;padding:0 calc(16px*var(--s));
 box-shadow:0 8px 20px rgba(0,0,0,.5),inset 0 0 calc(24px*var(--s)) rgba(60,255,140,.07)}
[dir=rtl] .fs-terminal{padding:0 calc(16px*var(--s))}
.fs-terminal .av{display:none}
.fs-terminal .ft small{color:#4ad07a}
.fs-terminal .ft small::before{content:"> ";color:#2e8f52;font-weight:700}
.fs-terminal .ft b{color:#bdffd6}
.fs-terminal .ft b.fw{color:#7dff9f;text-shadow:0 0 calc(10px*var(--s)) rgba(80,255,140,.55)}
.fs-terminal .st{color:#4ad07a}
.fs-terminal .kw{background:rgba(80,255,140,.14);color:#bdffd6;border-radius:calc(3px*var(--s))}

/* --- Royal: red velvet, gold edge, a crown on the winner --- */
.fs-royal{overflow:visible;border-radius:calc(9px*var(--s));background:linear-gradient(145deg,#2a0a10,#15070b 60%,#230910);
 border:1px solid #6b4a16;padding:0 calc(24px*var(--s)) 0 calc(9px*var(--s));
 box-shadow:0 10px 26px rgba(0,0,0,.55),inset 0 0 0 1px rgba(245,196,81,.22),inset 0 0 calc(30px*var(--s)) rgba(154,17,24,.4)}
[dir=rtl] .fs-royal{padding:0 calc(9px*var(--s)) 0 calc(24px*var(--s))}
.fs-royal .av img,.fs-royal .av .ph{border-color:var(--gold);box-shadow:0 0 calc(12px*var(--s)) rgba(245,196,81,.4)}
.fs-royal.won .av::before,.fs-royal.wonl .av::before{content:"\1F451";position:absolute;top:calc(-17px*var(--s));left:50%;z-index:2;line-height:1;
 transform:translateX(-50%) rotate(-8deg);font-size:calc(19px*var(--s));filter:drop-shadow(0 0 calc(7px*var(--s)) rgba(245,196,81,.75))}
.fs-royal .ft small{color:#c9a96a}
.fs-royal .ft b.fw{color:#ffe9a8;text-shadow:0 0 calc(8px*var(--s)) var(--gold),0 0 calc(20px*var(--s)) rgba(245,196,81,.5)}
.fs-royal .st{color:var(--gold)}
.fs-royal .kw{background:rgba(245,196,81,.16);color:#ffe9a8}

/* --- Tape: a strip of tape stuck on the screen, a hair crooked --- */
.fs-tape{background:linear-gradient(#f4e6b8,#e8d79f);color:#3a2f14;border-radius:0;transform:rotate(-1.6deg);padding:0 calc(20px*var(--s));
 box-shadow:0 6px 16px rgba(0,0,0,.4);
 -webkit-mask-image:linear-gradient(90deg,transparent 0,#000 calc(7px*var(--s)),#000 calc(100% - 7px*var(--s)),transparent 100%);
 mask-image:linear-gradient(90deg,transparent 0,#000 calc(7px*var(--s)),#000 calc(100% - 7px*var(--s)),transparent 100%)}
[dir=rtl] .fs-tape{padding:0 calc(20px*var(--s))}
.fs-tape .ft small{color:#6d5a26}
.fs-tape .ft b{color:#3a2f14}
.fs-tape .ft b.fw{color:#9a1118;text-shadow:none}
.fs-tape .st{color:#9a1118}
.fs-tape .av img,.fs-tape .av .ph{border-color:#3a2f14}
.fs-tape .av .ph{background:#d8c893;color:#6d5a26}
.fs-tape .kw{background:rgba(58,47,20,.15);color:#3a2f14}

/* --- Arcade: square, hard shadow, retro --- */
.fs-arcade{background:#0b0b1a;border:calc(3px*var(--s)) solid #fff;border-radius:0;padding:0 calc(18px*var(--s));
 box-shadow:calc(4px*var(--s)) calc(4px*var(--s)) 0 0 var(--acc),0 8px 20px rgba(0,0,0,.45)}
[dir=rtl] .fs-arcade{padding:0 calc(18px*var(--s))}
.fs-arcade .ft small{color:#8fd5ff;text-transform:uppercase;letter-spacing:calc(1.5px*var(--s))}
[dir=rtl] .fs-arcade .ft small{letter-spacing:0;text-transform:none}
.fs-arcade .ft b.fw{color:var(--gold);text-shadow:calc(2px*var(--s)) calc(2px*var(--s)) 0 #6b3a00}
.fs-arcade .st{color:#8fd5ff}
.fs-arcade .av img,.fs-arcade .av .ph{border-radius:0;border-color:#fff;border-width:calc(2px*var(--s))}
.fs-arcade .badge{border-radius:0;border-width:calc(2px*var(--s))}
.fs-arcade .kw{background:var(--acc);color:#fff;border-radius:0}

/* --- Line: no box at all, just text on a line --- */
.fs-line{background:transparent;border:0;border-bottom:calc(2px*var(--s)) solid var(--acc2);border-radius:0;box-shadow:none;
 height:calc(44px*var(--s));padding:0 calc(2px*var(--s))}
[dir=rtl] .fs-line{padding:0 calc(2px*var(--s))}
.fs-line .av{width:calc(30px*var(--s));height:calc(30px*var(--s))}
.fs-line .badge{display:none}
.fs-line .ft small{color:rgba(255,255,255,.8);text-shadow:0 1px calc(3px*var(--s)) rgba(0,0,0,.9)}
.fs-line .ft b{text-shadow:0 1px calc(3px*var(--s)) rgba(0,0,0,.9)}
.fs-line .kw{background:rgba(0,0,0,.45)}
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
/* 1.19.0: Chat box style "Bow": no box at all — a rail of bows and blossoms down the side, a glow, and a dark edge on
   the words so they read over any game. The line between two messages fills in from the top as the next one lands. */
.st-bow .cbin{gap:.3em}
.st-bow{--orn:1.15em;--rail:1.75em}
.st-bow .cm{position:relative;padding-inline-start:var(--rail)}
.st-bow .cm::before{content:"";position:absolute;inset-inline-start:0;top:.18em;width:var(--orn);height:var(--orn);
 -webkit-text-stroke:0;background:url("/art/bow.png") no-repeat center/contain;
 filter:drop-shadow(0 0 .22em rgba(255,120,170,.75));animation:ornpop .5s cubic-bezier(.2,1.5,.4,1) both}
.st-bow .cm[data-orn="1"]::before{background-image:url("/art/flower.png")}
.st-bow .cm[data-orn="2"]::before{background:radial-gradient(circle at 40% 28%,#ffa8c0,#ff5f87 58%,#e02a55);
 -webkit-mask:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2022%22%3E%3Cpath%20d%3D%22M12%2021.5C3.6%2015.2.5%2010.6.5%206.9A6.4%206.4%200%200%201%2012%203.6%206.4%206.4%200%200%201%2023.5%206.9C23.5%2010.6%2020.4%2015.2%2012%2021.5Z%22%20fill%3D%22%23000%22%2F%3E%3C%2Fsvg%3E") no-repeat center/88% 88%;
 mask:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2022%22%3E%3Cpath%20d%3D%22M12%2021.5C3.6%2015.2.5%2010.6.5%206.9A6.4%206.4%200%200%201%2012%203.6%206.4%206.4%200%200%201%2023.5%206.9C23.5%2010.6%2020.4%2015.2%2012%2021.5Z%22%20fill%3D%22%23000%22%2F%3E%3C%2Fsvg%3E") no-repeat center/88% 88%}
.st-bow .cm::after{content:"";position:absolute;inset-inline-start:calc(var(--orn)/2 - .06em);
 top:calc(.18em + var(--orn) + .1em);bottom:calc(-.3em + .06em);width:.13em;border-radius:999px;
 background:linear-gradient(#ffd3e0,#ff6f9a);box-shadow:0 0 .3em rgba(255,120,170,.8);
 transform-origin:top;animation:railfill .85s ease both}
.st-bow .cm:last-child::after{display:none}
.st-bow.top .cm:last-child::after{display:block}.st-bow.top .cm:first-child::after{display:none}
@keyframes railfill{from{transform:scaleY(0);opacity:.35}to{transform:scaleY(1);opacity:1}}
@keyframes ornpop{from{opacity:0;transform:scale(.4) rotate(-20deg)}to{opacity:1;transform:none}}
.st-bow.line .cm{padding-inline-start:0}.st-bow.line .cm::before,.st-bow.line .cm::after{display:none}
.st-bow .cm{text-shadow:0 .06em .14em rgba(40,6,20,.95),0 0 .5em rgba(255,120,165,.3)}
.st-bow .cm .nm{text-shadow:0 0 .35em rgba(255,130,175,.95),0 .06em .14em rgba(40,6,20,.95)}
.st-bow .cm .sep{color:rgba(255,203,221,.8)}
.st-bow .cm .bd{background:rgba(255,143,176,.34);color:#ffe3ec}
.st-bow .cm .bd.mod{background:rgba(74,208,122,.36)}.st-bow .cm .bd.vip{background:rgba(224,5,185,.36)}
.st-bow .cm .bd.sub{background:rgba(255,99,143,.42)}.st-bow .cm .bd.g{background:rgba(245,196,81,.3);color:#ffeec2}
.st-bow .cm .ans{border-inline-start-color:#ff8fb0;color:#ffe3ec}
.st-bow .cm.fold{color:#ffb3cc}
.st-bow .cm.mention{background:transparent!important;padding-left:0!important;padding-right:0!important;
 text-shadow:0 0 .55em rgba(255,110,165,1),0 .06em .14em rgba(60,8,28,.98)}
.st-bow.b-soft .cm{background:rgba(44,10,24,.42);border-radius:.4em;padding:.06em .45em}
.st-bow.b-dark .cm{background:rgba(32,6,18,.82);border-radius:.4em;padding:.06em .45em}
/* 1.19.0: Chat box style "Ribbon": the name rides a flat ribbon banner, drawn in the stylesheet itself. */
/* 1.19.0: a small pattern under every message. "round" is what stops the last wave or heart
   being sliced in half at the edge — the browser stretches the motif a hair so a whole number fits. */
.cbox[class*="dv-"]:not(.st-bow) .cm::after{content:"";display:block;margin:.28em .55em .06em;pointer-events:none}
.cbox.line[class*="dv-"] .cm::after{display:none}   /* Bow keeps its own rail, so it is left out above */
.dv-stitch:not(.st-bow) .cm::after{height:.16em;background-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2212%22%20height%3D%223%22%20viewBox%3D%220%200%2012%203%22%3E%3Crect%20x%3D%220%22%20y%3D%220%22%20width%3D%227%22%20height%3D%223%22%20rx%3D%221.5%22%20fill%3D%22%23ff96b9%22%2F%3E%3C%2Fsvg%3E");
 background-size:.8em .16em;background-position:0 50%;background-repeat:round no-repeat}
.dv-wave:not(.st-bow) .cm::after{height:.44em;background-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2210%22%20viewBox%3D%220%200%2024%2010%22%20preserveAspectRatio%3D%22none%22%3E%3Cpath%20d%3D%22M0%205%20Q3%201.3%206%205%20Q9%208.7%2012%205%20Q15%201.3%2018%205%20Q21%208.7%2024%205%22%20fill%3D%22none%22%20stroke%3D%22%23ff96b9%22%20stroke-width%3D%222%22%20stroke-linecap%3D%22round%22%2F%3E%3C%2Fsvg%3E");
 background-size:1.35em .44em;background-position:0 50%;background-repeat:round no-repeat}
.dv-jewel:not(.st-bow) .cm::after{height:.5em;background:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22200%22%20height%3D%2210%22%20viewBox%3D%220%200%20200%2010%22%3E%3Cpath%20d%3D%22M8%205%20H88%20M112%205%20H192%22%20stroke%3D%22%23ff96b9%22%20stroke-width%3D%221.8%22%20stroke-linecap%3D%22round%22%2F%3E%3Cpath%20d%3D%22M100%201%20L104%205%20L100%209%20L96%205%20Z%22%20fill%3D%22%23ff96b9%22%2F%3E%3Ccircle%20cx%3D%2290.5%22%20cy%3D%225%22%20r%3D%221.5%22%20fill%3D%22%23ff96b9%22%2F%3E%3Ccircle%20cx%3D%22109.5%22%20cy%3D%225%22%20r%3D%221.5%22%20fill%3D%22%23ff96b9%22%2F%3E%3C%2Fsvg%3E") center/100% .5em no-repeat}
.dv-hearts:not(.st-bow) .cm::after{height:.46em;opacity:.9;background-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2218%22%20height%3D%2210%22%20viewBox%3D%220%200%2018%2010%22%3E%3Cpath%20d%3D%22M9%209C4.6%205.9%203%204%203%202.6A2.3%202.3%200%200%201%209%201.6A2.3%202.3%200%200%201%2015%202.6C15%204%2013.4%205.9%209%209Z%22%20fill%3D%22%23ff96b9%22%2F%3E%3C%2Fsvg%3E");
 background-size:1.05em .46em;background-position:0 50%;background-repeat:round no-repeat}
.st-ribbon .cbin{gap:.3em;padding-inline:.35em}
.st-ribbon .cm{padding-top:.12em}
/* 1.19.0: a flat ribbon drawn as a shape, not a photo — the end tails are fixed and only the band stretches,
   so it is sharp at any size, weighs nothing and never has to be cut from a sheet again. */
.st-ribbon .cm .head{display:inline-flex;align-items:center;gap:.3em;box-sizing:content-box;--u:.034em;
 height:calc(29*var(--u));padding:calc(3*var(--u)) .3em calc(12*var(--u));color:#fff;font-weight:800;font-size:.92em;line-height:1;
 border-style:solid;border-width:0 calc(40*var(--u)) 0 calc(40*var(--u));
 border-image-source:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22140%22%20height%3D%2244%22%20viewBox%3D%220%200%20140%2044%22%3E%3Cg%20stroke%3D%22%2373183c%22%20stroke-width%3D%222.6%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M0%2012%20L32%2012%20L32%2041%20L0%2041%20L12%2026.5%20Z%22%20fill%3D%22%23d2456f%22%2F%3E%3Cpath%20d%3D%22M140%2012%20L108%2012%20L108%2041%20L140%2041%20L128%2026.5%20Z%22%20fill%3D%22%23d2456f%22%2F%3E%3C%2Fg%3E%3Cpath%20d%3D%22M24%2030%20L34%2030%20L24%2041%20Z%22%20fill%3D%22%2396284c%22%20stroke%3D%22%2373183c%22%20stroke-width%3D%222.2%22%20stroke-linejoin%3D%22round%22%2F%3E%3Cpath%20d%3D%22M116%2030%20L106%2030%20L116%2041%20Z%22%20fill%3D%22%2396284c%22%20stroke%3D%22%2373183c%22%20stroke-width%3D%222.2%22%20stroke-linejoin%3D%22round%22%2F%3E%3Crect%20x%3D%2222%22%20y%3D%223%22%20width%3D%2296%22%20height%3D%2229%22%20rx%3D%222.5%22%20fill%3D%22%23f05f90%22%2F%3E%3Cpath%20d%3D%22M24.5%203%20H115.5%20A2.5%202.5%200%200%201%20118%205.5%20V18%20H22%20V5.5%20A2.5%202.5%200%200%201%2024.5%203%20Z%22%20fill%3D%22%23ff85ae%22%2F%3E%3Crect%20x%3D%2222%22%20y%3D%223%22%20width%3D%2296%22%20height%3D%2229%22%20rx%3D%222.5%22%20fill%3D%22none%22%20stroke%3D%22%2373183c%22%20stroke-width%3D%222.6%22%2F%3E%3C%2Fsvg%3E");border-image-slice:0 40 0 40 fill;border-image-repeat:stretch;
 filter:drop-shadow(0 .07em .14em rgba(90,15,45,.45));-webkit-text-stroke:0;vertical-align:middle}
.st-ribbon .cm .nm{color:#fff!important;text-shadow:0 .06em .1em rgba(120,20,55,.7)}
.st-ribbon .cm .bd{background:rgba(255,255,255,.28);color:#fff;border-radius:.5em;font-size:.74em}
.st-ribbon .cm .pic,.st-ribbon .cm .tb,.st-ribbon .cm .sh{display:none}
.st-ribbon .cm .sep{display:none}
.st-ribbon .cm .tx{display:block;margin-top:.12em;padding-inline-start:.55em}   /* the words go under the ribbon, not beside it */
.st-ribbon .cm .ans,.st-ribbon .cm .rpl{padding-inline-start:.55em}
.st-ribbon .cm .tx{color:#fff;-webkit-text-stroke:.14em rgba(70,10,30,.85);paint-order:stroke fill}
.st-ribbon .cm .cnt{vertical-align:.1em}
.st-ribbon .cm .mn{color:#ffc2d4}
.st-ribbon .cm.fold{color:#ffc2d4}
.st-ribbon .cm.mention{background:transparent!important}
.st-ribbon.line .cm .head{height:auto;border:0;padding:0;filter:none}
.cbox.line.st-cards .cm,.cbox.line.st-fade .cm{align-self:center!important}
/* 1.19.0: turned a little, so the chat reads as if it stands in the room. The place and size do not change — only how it is drawn. */
.cbox.tl-left,.cbox.tl-right{transform-style:preserve-3d;will-change:transform}
.cbox.tl-left{transform:perspective(calc(900px*var(--s0))) rotateY(13deg)}
.cbox.tl-right{transform:perspective(calc(900px*var(--s0))) rotateY(-13deg)}
.cbox.tl-left .cm,.cbox.tl-right .cm{backface-visibility:hidden}
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
#arena{position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:0}
</style></head><body><canvas id="arena"></canvas><div id="z"></div><div id="abs"></div><div id="band"></div><div id="sel"><span class="tag"></span><span class="h tr" data-h="tr"></span><span class="h" data-h="br"></span></div>
<script>
var q=new URLSearchParams(location.search),old={},firstKey=null,lang="en",EDIT=!!q.get("edit"),DRAG=null,RES=null,BAND=null,SEL=[],POS={},VER=null;
if(q.get("column"))document.body.classList.add("col");if(EDIT)document.body.classList.add("edit");if(q.get("cbonly"))document.body.classList.add("cbonly");
var SIZE=parseFloat(q.get("size")||"1");if(!(SIZE>=0.5&&SIZE<=3))SIZE=1;
var CBONLY=!!q.get("cbonly");    // 1.18.0: the Chat box's own preview next to its settings (only the chat box, filling the frame)
var CHATONLY=location.pathname=="/chat";   // 1.18.0: the Chat box's own link: only the chat box, filling the Browser Source (any scene, any size)
var ADEMO=q.get("arena")=="demo";    // 1.19.0: the Arena's own preview in the app (Overlays > Arena): only the soldiers, made-up viewers
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
/* 1.19.0: nobody typed first in time: the "Who's first?" card tears down the middle, the two halves fall and fade */
var TEAR=[[52,0],[47,12],[54,25],[46,38],[53,50],[45,63],[52,76],[46,88],[51,100]];
function tearFirst(card){var r=card.getBoundingClientRect();if(!r.width||!card.animate){card.remove();return}
  var left="polygon(0 0,"+TEAR.map(function(p){return p[0]+"% "+p[1]+"%"}).join(",")+",0 100%)",right="polygon(100% 0,"+TEAR.map(function(p){return p[0]+"% "+p[1]+"%"}).join(",")+",100% 100%)";
  [[left,-1],[right,1]].forEach(function(h,i){var c=card.cloneNode(true);c.classList.remove("pick");c.removeAttribute("data-key");
    c.style.cssText+=";position:fixed;margin:0;left:"+r.left+"px;top:"+r.top+"px;width:"+r.width+"px;height:"+r.height+"px;clip-path:"+h[0]+";z-index:50;pointer-events:none;transform-origin:"+(h[1]<0?"10% 90%":"90% 90%");
    document.body.appendChild(c);var d=h[1],drop=Math.max(innerHeight-r.top,r.height*3);
    c.animate([{transform:"none",opacity:1},{transform:"translate("+(d*6)+"px,-4px) rotate("+(d*4)+"deg)",opacity:1,offset:.18},
      {transform:"translate("+(d*40)+"px,"+(drop*.55)+"px) rotate("+(d*22)+"deg)",opacity:.6,offset:.7},{transform:"translate("+(d*60)+"px,"+drop+"px) rotate("+(d*34)+"deg)",opacity:0}],
      {duration:1300,delay:i*90,easing:"cubic-bezier(.45,0,.75,.6)",fill:"forwards"}).onfinish=function(){c.remove()}});
  card.remove()}
function drawFirst(f){var cur=document.querySelector(".first");
  if(!showF||!f||(f.over&&!EDIT)){if(cur){if(f&&f.over&&!f.won&&String(firstKey).indexOf("wait")==0)tearFirst(cur);else cur.remove()}firstKey=null;return}   /* 1.18.0: time's up and nobody was first: gone (1.19.0: torn in two, falling) */
  var fs="fs-"+(f.style||"pill"),who=f.who||tx("who"),lab=f.label||tx("first");   /* 1.19.0: the look, and your own two texts */
  var key=(f.won?"w:"+f.login+":"+f.streak+":"+(f.avatar?1:0):"wait:"+f.words.join(",")+lang+(f.over?":over":""))+"|"+fs+"|"+who+"|"+lab;
  if(key!==firstKey){var wasWait=firstKey===null||String(firstKey).indexOf("wait")==0;firstKey=key;
    var d=document.createElement("div");d.dataset.key="first";d.dataset.label=tx("fic");
    if(!f.won){d.className="first "+fs+(f.over?" over":"");d.innerHTML='<div class="av"><div class="ph">?</div></div><div class="ft"><small>'+esc(who)+'</small><b style="font-weight:600">'+esc(tx("type"))+' '+f.words.map(function(w){return '<bdi class="kw">'+esc(w)+'</bdi>'}).join(" ")+'</b></div>'}
    else{var pic=f.avatar?'<img src="'+esc(f.avatar)+'" alt="">':'<div class="ph ini">'+esc(String(f.user).charAt(0).toUpperCase())+'</div>';
      d.className="first "+fs+(wasWait?" won":" wonl");d.innerHTML='<div class="shine"></div><div class="av">'+pic+'<span class="badge">1</span></div><div class="ft"><small>'+esc(lab)+'</small><b class="fw"><bdi>'+esc(f.user)+'</bdi></b>'+(f.streak>1?' <bdi class="st">🔥 '+f.streak+' '+esc(tx("row"))+'</bdi>':'')+'</div>'}
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
function nameColor(row,cfg){if(cfg.name_color=="white")return "#fff";if(cfg.name_color=="accent")return "var(--acc2)";if(cfg.name_color=="rose")return "#ff8fb0";   /* 1.19.0 */
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
/* 1.19.0: which ornament this message wears on the Bow rail. Worked out from the message's own id,
   so it is the same every time the chat is drawn — before, it came from the row's place in the list,
   and every bow turned into a flower the moment a new message pushed the list along. */
function ornOf(id){var s=String(id==null?"":id),h=2166136261,i;
  for(i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}
  h^=h>>>15;h=Math.imul(h,2246822507);h^=h>>>13;            /* mixed hard, so even 1,2,3 in a row come out jumbled */
  return ((h>>>0)%3)}
function cbRow(row,cfg){var d=document.createElement("div");d.dataset.id=row.id;
  d.dataset.orn=ornOf(row.id);   /* 1.19.0: the bow / flower / heart belongs to the message, so it never changes when a new one arrives */
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
  el.className="cbox abs st-"+cfg.style+" g-"+cfg.glow+" o-"+cfg.outline+" s-"+cfg.shadow+" b-"+cfg.bg+" a-"+cfg.anim+(cfg.shape=="line"?" line":cfg.flow=="top"?" top":"")+(cfg.lines?"":" lines0")+(cfg.tilt&&cfg.tilt!="off"?" tl-"+cfg.tilt:"")+
    (cfg.divider&&cfg.divider!="off"?" dv-"+cfg.divider:"")+
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
/* ---- 1.19.0: the Arena (Overlays > Arena): Chat soldiers. Drawn on one canvas over the whole Browser Source. ---- */
(function(){

var cv=document.getElementById('arena'),ctx=cv.getContext('2d'),CFG={on:false,max:20,grow:'little',crown:true,size:100,names:true,blood:true},DEMO=ADEMO,DPR=1;
var W=1280,H=720,G=680,U=1;
function fit(){DPR=Math.min(2,window.devicePixelRatio||1);W=innerWidth||1280;H=innerHeight||720;U=Math.max(Math.min(W/1280,H/720),DEMO?.62:0)*(CFG.size||100)/100;   /* 1.19.1: by the smaller side, so an ultrawide or very wide source doesn't make giants */   /* the preview in the app is a small strip: the soldiers there never shrink below readable */ G=H*(DEMO?100:(+CFG.ground||100))/100-Math.max(6,14*U);   /* 1.19.1: where the ground line sits (Overlays > Arena > Where they walk) */
  cv.width=Math.round(W*DPR);cv.height=Math.round(H*DPR);ents.forEach(function(e){e.x=Math.min(RX(),Math.max(LX(),e.x))})}
/* 1.19.1: the stretch of the line the soldiers walk (left and right edge, % of the width) */
function LX(){return W*Math.max(0,Math.min(80,+CFG.left||0))/100+40}
function RX(){var r=CFG.right==null?100:+CFG.right;return Math.max(LX()+60,W*Math.max(20,Math.min(100,r))/100-40)}
var COLORS=['#ff6b85','#ffb02e','#ffe14d','#7be37b','#2fd6c3','#4db8ff','#8f9cff','#c08cff','#ff7ce0','#ff8a4d'];
var PALS=[['#4d6b3a','#2b3d20','#8a9a5b'],['#c2a878','#86693f','#e6d6ad'],['#7d8590','#474d57','#b9c0ca'],['#33507a','#1c2f4d','#6f8fbf'],
  ['#d5dae2','#8f9aab','#ffffff'],['#3b3b49','#1d1d26','#5d5d74'],['#2f6b62','#18403a','#62a898'],['#7a5a3a','#4a3421','#a98a62'],['#59663a','#7a5a3a','#262e1a']];
var PT=['wood','digi','tiger'];
var BUILD=[[1,1]];      /* 1.19.0: everyone the same shape — kills make them bigger, nothing makes them fatter or lankier */
var SKINS=['balaclava','gas','skull','bandana','nvg','visor'];
var NAMES=['سلطان','نواف_77','Shuaiil','ريم','xDarkWolf','خالد','Mido','جود','Zezo','أبو_فهد','Noor','فيصل','Kira','تركي','Lulu','ساره','Hamood','مشعل','Ghost_x','لينا'];
var ents=[],parts=[],floats=[],T=0,auto=true,n0=0;
function rnd(a,b){return a+Math.random()*(b-a)}
function pick(a){return a[Math.floor(Math.random()*a.length)]}
function chat(){}
function readable(c){if(!/^#[0-9a-f]{6}$/i.test(c||''))return '';var r=parseInt(c.substr(1,2),16),g=parseInt(c.substr(3,2),16),b=parseInt(c.substr(5,2),16),l=(.299*r+.587*g+.114*b)/255;
  if(l<.4){var f=.55;r=Math.round(r+(255-r)*f);g=Math.round(g+(255-g)*f);b=Math.round(b+(255-b)*f)}return 'rgb('+r+','+g+','+b+')'}
function gone(e){e.dead=true;e.dv=3;e.dt=0;e.fd=1}
function alive(){return ents.filter(function(e){return !e.dead})}
function find(n){return alive().filter(function(e){return e.key===n})[0]}
function spawn(name,key,color){
  key=key||name;if(find(key))return;var al=alive();if(al.length>=(CFG.max||20))gone(al.slice().sort(function(a,b){return a.wins-b.wins||a.born-b.born})[0]);var i=n0++;
  var e={name:name,key:key,born:T,color:readable(color)||COLORS[i%COLORS.length],pal:PALS[(i*4)%PALS.length],ptype:PT[i%3],skin:SKINS[(i*5)%SKINS.length],seed:Math.floor(Math.random()*1e6),
    x:rnd(LX()+30,Math.max(LX()+31,RX()-30)),dir:Math.random()<.5?-1:1,sp:rnd(14,32),s:1,ts:1,wins:0,wt:0,shield:0,fall:G+80,vy:0,turn:rnd(1,4),kb:0,ph:rnd(0,6),a:1,swing:0,dress:0,p:rnd(0,6),land:0,fv:n0%3,cdA:0,cdP:0,ky:0,
    bx:BUILD[0][0],by:BUILD[0][1],hurt:0,by_:null,tn:0,tdir:0,rest:0,look:0,leaving:0,flash:0};
  ents.push(e);chat(name,e.color,'!spawn');
}
function near(a){var best=null,bd=1e9;alive().forEach(function(b){if(b===a||b.fall>0)return;var d=Math.abs(b.x-a.x);if(d<15*(a.s+b.s)*U&&d<bd){bd=d;best=b}});return best}
function attack(a){if(!a||a.fall>0)return;chat(a.name,a.color,'!attack');if(a.dress>0||a.land>0||a.hurt>0||a.leaving||(DEMO&&T<a.cdA))return;a.cdA=T+CD;a.swing=SWING;a.tn=0;a.rest=0;var b=near(a);
  if(!b){floats.push({x:a.x,y:G-104*a.s*U,t:'MISS',c:'#b9b9c9',life:.9});return}
  a.dir=b.x>=a.x?1:-1;resolve(a,b)}
function protect(a){if(!a||a.fall>0)return;chat(a.name,a.color,'!protect');if(a.land>0||a.shield>T||a.hurt>0||a.leaving||(DEMO&&T<a.cdP))return;a.rest=0;a.cdP=T+CD;a.dress=DRESS;a.shield=T+12+DRESS}
function burst(x,y,color,n,alt){for(var i=0;i<n;i++)parts.push({x:x,y:y,vx:rnd(-260,260),vy:rnd(-380,-60),life:rnd(.5,1),c:Math.random()<.5?color:(alt||'#fff'),r:rnd(3,7)})}
function spark(x,y,n){for(var i=0;i<(n||9);i++){var an=rnd(0,6.283),sp=rnd(90,300);
  parts.push({x:x,y:y,vx:Math.cos(an)*sp,vy:Math.sin(an)*sp-90,life:rnd(.16,.3),c:'#fff',r:rnd(2,4.5),g:0})}}
function resolve(a,b){
  if(b.shield>T&&!(b.dress>0)){b.shield=0;a.kb=-a.dir*420;burst(b.x,G-38*b.s*U,'#aeb4c0',22);spark(b.x+a.dir*12*U,G-48*b.s*U,12);
    floats.push({x:b.x,y:G-104*b.s*U,t:'BLOCKED!',c:'#d5dae3',life:1.3});return}
  /* the knife lands: he jerks back first, and falls a moment later */
  b.hurt=HURT;b.by_=a;b.fd=a.dir;b.flash=.16;b.kb=a.dir*300*U;b.rest=0;b.tn=0;
  spark(b.x+a.dir*10*U,G-46*b.s*U,14);
  if(CFG.blood)burst(b.x,G-42*b.s*U,'#d3141f',12,'#8a0c13');
}
function finish(b){     /* the jerk is over: now he goes down */
  var a=b.by_;b.hurt=0;b.by_=null;
  b.dead=true;b.dt=0;b.dv=Math.floor(Math.random()*3);b.kvx=b.fd*rnd(180,300)*U;b.kvy=-520*U;b.ky=0;
  if(CFG.blood)burst(b.x,G-38*b.s*U,'#d3141f',22,'#8a0c13');else burst(b.x,G-38*b.s*U,b.color,20);
  if(!a||a.dead)return;
  a.wins++;a.wt=T;a.ts=CFG.grow=='off'?1:CFG.grow=='lot'?Math.min(2.4,1+a.wins*.2):Math.min(1.45,1+a.wins*.07);
  floats.push({x:a.x,y:G-108*a.s*U,t:'KO!',c:'#ffd84d',life:1.3});
}
function newGoal(e){var L=LX(),R=RX(),o=alive().filter(function(x){return x!==e&&x.fall<=0&&!x.leaving}),x;
  if(o.length&&Math.random()<.25)x=o[Math.floor(Math.random()*o.length)].x+rnd(-15,15);
  else{var lo=e.x-L,hi=R-e.x;x=Math.random()<hi/(lo+hi)?rnd(e.x+(R-L)*.35,R):rnd(L,e.x-(R-L)*.35);if(!(x>=L&&x<=R))x=rnd(L,R)}   /* mostly far away, toward the side with more room, so the whole line gets used */
  return Math.min(R,Math.max(L,x))}
function startTurn(e){if(e.tn>0||e.leaving)return;e.tn=TURN;e.tdir=-e.dir}
function king(){return alive().filter(function(e){return e.wins>0}).sort(function(a,b){return b.wins-a.wins||a.wt-b.wt})[0]}
function step(dt){
  T+=dt;
  ents.forEach(function(e){
    if(e.dead){e.dt+=dt;if(e.dv===3)e.a-=dt*2.5;else if(e.dv===2){e.x+=e.kvx*dt;e.ky+=e.kvy*dt;e.kvy+=1500*U*dt;if(e.dt>1.5)e.a-=dt*1.7}else{if(e.dv===0&&e.dt<.4)e.x+=e.fd*70*U*dt;if(e.dt>2.5)e.a-=dt*1.5}return}
    if(e.fall>0){e.vy=Math.min(560*U,e.vy+1100*U*dt);e.fall-=e.vy*dt;if(e.fall<=0){e.fall=0;e.vy=0;e.land=LAND;burst(e.x,G,'#c9c2b0',12)}return}
    if(e.land>0){e.land-=dt;return}
    e.s+=(e.ts-e.s)*Math.min(1,dt*.9);if(e.swing>0)e.swing-=dt;if(e.flash>0)e.flash-=dt;
    if(Math.abs(e.kb)>5){e.x+=e.kb*dt;e.kb*=Math.pow(.02,dt)}
    if(e.hurt>0){e.hurt-=dt;if(e.hurt<=0)finish(e);return}          /* jerking back: nothing else happens */
    if(e.tn>0){e.tn-=dt;if(e.tn<=TURN/2)e.dir=e.tdir;if(e.tn<0)e.tn=0;return}
    if(e.leaving){var lx=e.sp*U*1.7*dt;e.x+=e.dir*lx;e.p+=lx*6.2832/(42*e.s*U);
      if(e.x<-70||e.x>W+70)e.a=0;return}
    if(e.rest>0){e.rest-=dt;
      if(e.look>0&&(e.look-=dt)<=0)startTurn(e);                    /* a look around while he stands */
      var tgt=Math.round(e.p/6.2832)*6.2832;e.p+=(tgt-e.p)*Math.min(1,dt*7);return}   /* so he walks off again from a clean stride */
    e.turn-=dt;   /* 1.19.1: each soldier walks to a spot somewhere along the whole line (often to another soldier, so fights happen), stops a while, picks the next one */
    var reach=e.goal!=null&&Math.abs(e.goal-e.x)<10;
    if(e.turn<0||reach||e.goal==null){
      if(reach&&Math.random()<.45){e.rest=rnd(1.2,3.4);e.look=e.rest*rnd(.3,.55);e.goal=null;e.turn=e.rest+rnd(1,2)}
      else{e.goal=newGoal(e);e.turn=Math.abs(e.goal-e.x)/Math.max(1,e.sp*U)+rnd(3,6);if((e.goal-e.x)*e.dir<0)startTurn(e)}}   /* time enough to get there */
    if(e.dress>0){e.dress-=dt;if(e.dress<=0)burst(e.x,G-50*e.s*U,'#cfd4de',8)}
    else if(e.swing<=0){var dx=e.sp*U*(e.shield>T?.6:1)*dt;e.x+=e.dir*dx;e.p+=dx*6.2832/(42*e.s*U)}
    if(e.x<LX()){e.x=LX();e.goal=null;if(e.dir<0)startTurn(e)}if(e.x>RX()){e.x=RX();e.goal=null;if(e.dir>0)startTurn(e)}
  });
  ents=ents.filter(function(e){return e.a>0});
  parts.forEach(function(p){p.vy+=(p.g===0?120:900)*dt;p.x+=p.vx*dt;p.y+=p.vy*dt;p.life-=dt});parts=parts.filter(function(p){return p.life>0});
  floats.forEach(function(f){f.y-=40*dt;f.life-=dt});floats=floats.filter(function(f){return f.life>0});
}
function rr(x,y,w,h,r){ctx.beginPath();ctx.roundRect(x,y,w,h,r)}
function rng(seed){return function(){seed|=0;seed=seed+0x6D2B79F5|0;var t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function pat(e,key,x,y,w,h){var r=rng(e.seed+key*977),P=e.pal,i;
  if(e.ptype==='digi'){for(i=0;i<w*h/34;i++){ctx.fillStyle=r()<.55?P[1]:P[2];var b=5;ctx.fillRect(x+Math.floor(r()*w/b)*b,y+Math.floor(r()*h/b)*b,b+(r()<.45?b:0),b)}}
  else if(e.ptype==='tiger'){ctx.lineCap='round';for(i=0;i<h/7.5;i++){ctx.strokeStyle=i%3===2?P[2]:P[1];ctx.lineWidth=3.4+r()*1.8;var yy=y+i*7.5+r()*4,xx=x-2+r()*w*.4;ctx.beginPath();ctx.moveTo(xx,yy);ctx.quadraticCurveTo(xx+w*.3,yy-4+r()*4,xx+w*(.45+r()*.5),yy+r()*3);ctx.stroke()}}
  else{for(i=0;i<w*h/95+2;i++){ctx.fillStyle=r()<.6?P[1]:P[2];ctx.beginPath();ctx.ellipse(x+r()*w,y+r()*h,4.5+r()*5,3.2+r()*3.6,r()*3,0,7);ctx.fill()}}}
function part(e,key,x,y,w,h,rad){rr(x,y,w,h,rad);rim();ctx.fillStyle=e.pal[0];ctx.fill();ctx.save();rr(x,y,w,h,rad);ctx.clip();pat(e,key,x,y,w,h);
  var g=ctx.createLinearGradient(x,0,x+w,0);g.addColorStop(0,'rgba(0,0,0,.28)');g.addColorStop(.55,'rgba(0,0,0,0)');g.addColorStop(1,'rgba(255,255,255,.1)');ctx.fillStyle=g;ctx.fillRect(x,y,w,h);if(DK){ctx.fillStyle='rgba(0,0,0,.38)';ctx.fillRect(x,y,w,h)}ctx.restore();
  rr(x,y,w,h,rad);ctx.strokeStyle='rgba(0,0,0,.55)';ctx.lineWidth=1.3;ctx.stroke()}
function plate(x,y,w,h,r,k){if(k<=0)return;ctx.save();ctx.globalAlpha*=k;ctx.translate(0,-(1-k)*45);
  rr(x,y,w,h,r);rim();ctx.fillStyle=DK?'#131418':'#25272e';ctx.fill();ctx.strokeStyle='#14161b';ctx.lineWidth=1.3;ctx.stroke();ctx.fillStyle='rgba(255,255,255,.2)';ctx.fillRect(x+1.5,y+1.2,w-3,1.2);ctx.restore()}
function limb(e,key,x,y,l1,l2,w,a1,a2,end,front){ctx.save();ctx.translate(x,y);ctx.rotate(a1);part(e,key,-w/2,0,w,l1,w/2);
  if(AR){if(end==='boot')plate(-w/2-1.8,1.5,w+3.6,l1-3,3.5,AP[0]);else plate(-w/2-2.6,-4,w+5.2,10,5,AP[2])}
  if(front){ctx.fillStyle=e.color;ctx.fillRect(-w/2+.6,AR&&AP[2]>0?6.5:3,w-1.2,3.5)}
  ctx.translate(0,l1-2.5);ctx.rotate(a2);part(e,key+10,-w/2+.4,0,w-.8,l2,w/2);
  if(AR&&end!=='boot')plate(-w/2-1.3,1,w+2.6,l2-4,3,AP[2]);
  if(end==='boot'){rr(-w/2-.6,l2-8,w+1.2,8,2);ctx.fillStyle='#17171d';ctx.fill();rr(-w/2-.6,l2-4,w+6,5.5,2.2);ctx.fill();ctx.fillStyle='#34343d';ctx.fillRect(-w/2-.6,l2+.6,w+6,1.4)}
  else{ctx.beginPath();ctx.arc(0,l2+1,w/2+.7,0,7);ctx.fillStyle='#23232b';ctx.fill()}
  if(front){ctx.fillStyle='#101014';ctx.strokeStyle='#59606c';ctx.lineWidth=1;
    if(HIT){ctx.fillRect(-1.8,l2+1,3.6,4.5);ctx.fillRect(-3.2,l2+5,6.4,1.6);ctx.beginPath();ctx.moveTo(-2.3,l2+6.6);ctx.lineTo(2.3,l2+6.6);ctx.lineTo(.8,l2+20);ctx.closePath()}
    else{ctx.fillRect(-2.5,l2-.8,5,3.6);ctx.fillRect(2.5,l2-2,1.6,6);ctx.beginPath();ctx.moveTo(4.1,l2-1.3);ctx.lineTo(17,l2+.4);ctx.lineTo(4.1,l2+3.3);ctx.closePath()}
    ctx.fillStyle='#e6ebf2';ctx.fill();ctx.stroke();
    if(CFG.blood&&e.wins>0){ctx.fillStyle='#c4141d';ctx.beginPath();if(HIT){ctx.moveTo(-1.4,l2+12);ctx.lineTo(1.6,l2+12);ctx.lineTo(.8,l2+20)}else{ctx.moveTo(10,l2-.6);ctx.lineTo(17,l2+.4);ctx.lineTo(10,l2+2)}ctx.closePath();ctx.fill()}}
  ctx.restore()}
function eye(x,y,r){ctx.beginPath();ctx.arc(x,y,r,0,7);ctx.fillStyle='#fff';ctx.fill();ctx.beginPath();ctx.arc(x+r*.25,y+r*.08,r*.68,0,7);ctx.fillStyle='#16161d';ctx.fill();ctx.beginPath();ctx.arc(x+r*.5,y-r*.3,r*.26,0,7);ctx.fillStyle='#fff';ctx.fill()}
function head(e){var c=e.color,hy=0;
  function hc(f){ctx.beginPath();ctx.arc(0,0,15,0,7);rim();ctx.fillStyle=f;ctx.fill();ctx.strokeStyle='rgba(0,0,0,.55)';ctx.lineWidth=1.8;ctx.stroke()}
  function clipH(){ctx.save();ctx.beginPath();ctx.arc(0,0,15,0,7);ctx.clip()}
  if(e.skin==='bandana'){hc('#d9a37a');clipH();ctx.fillStyle=e.pal[1];ctx.fillRect(-16,1,32,16);ctx.fillStyle='rgba(255,255,255,.12)';ctx.fillRect(-16,1,32,2.5);ctx.restore();eye(3.5,-3.5,4.8);eye(12,-3.5,4.2)}
  else if(e.skin==='balaclava'){hc('#1b1b24');clipH();ctx.fillStyle='#d9a37a';rr(-4,-9.5,24,11.5,5);ctx.fill();ctx.restore();eye(3.5,-3.6,4.6);eye(12,-3.6,4)}
  else if(e.skin==='skull'){hc('#1b1b24');clipH();ctx.fillStyle='#d9a37a';rr(-4,-10,24,9.5,4.5);ctx.fill();
    ctx.fillStyle='#e9e2d0';ctx.beginPath();ctx.moveTo(-6,2);ctx.quadraticCurveTo(8,-1.8,17,1.5);ctx.lineTo(17,9);ctx.quadraticCurveTo(9,17.5,-4,11.5);ctx.closePath();ctx.fill();
    ctx.fillStyle='#1b1b24';ctx.beginPath();ctx.moveTo(8.3,.4);ctx.lineTo(11.4,5.2);ctx.lineTo(8.3,4.2);ctx.lineTo(5.2,5.2);ctx.closePath();ctx.fill();
    ctx.strokeStyle='#1b1b24';ctx.lineWidth=1.1;ctx.beginPath();ctx.moveTo(-.5,8.3);ctx.quadraticCurveTo(8,10.2,16,8);ctx.stroke();
    ctx.beginPath();[1.6,4.6,7.6,10.6,13.6].forEach(function(x){ctx.moveTo(x,6.3);ctx.lineTo(x,11)});ctx.stroke();
    ctx.fillStyle='rgba(27,27,36,.75)';ctx.beginPath();ctx.ellipse(-3.5,6.5,2.2,3.4,.3,0,7);ctx.fill();ctx.restore();eye(3.5,-5,4.3);eye(12,-5,3.8)}
  else if(e.skin==='gas'){hc('#262631');ctx.fillStyle='#8fb6c9';ctx.beginPath();ctx.arc(3.5,-3,5.2,0,7);ctx.arc(12.5,-3,4.4,0,7);ctx.fill();
    ctx.fillStyle='rgba(255,255,255,.6)';ctx.beginPath();ctx.arc(3,-4.5,1.4,0,7);ctx.arc(11.2,-4.5,1.2,0,7);ctx.fill();
    ctx.beginPath();ctx.arc(12,9,6.2,0,7);ctx.fillStyle='#4c4c5a';ctx.fill();ctx.strokeStyle='#15151b';ctx.lineWidth=1.5;ctx.stroke();ctx.fillStyle='#15151b';ctx.beginPath();ctx.arc(12,9,2.6,0,7);ctx.fill()}
  else if(e.skin==='nvg'){hc('#1b1b24');rr(2,-9,14,9,2.5);ctx.fillStyle='#34343f';ctx.fill();rr(12,-9.5,9,5,1.5);ctx.fillStyle='#22222a';ctx.fill();rr(12,-4,9,5,1.5);ctx.fill();
    ctx.fillStyle='#6dff7a';ctx.shadowColor='#6dff7a';ctx.shadowBlur=9;ctx.beginPath();ctx.arc(21,-7,2.1,0,7);ctx.arc(21,-1.5,2.1,0,7);ctx.fill();ctx.shadowBlur=0}
  else{hc('#1b1b24');clipH();ctx.fillStyle=c;ctx.shadowColor=c;ctx.shadowBlur=8;rr(-1,-7.5,19,9,3.5);ctx.fill();ctx.shadowBlur=0;ctx.fillStyle='rgba(255,255,255,.5)';ctx.fillRect(4,-5.5,8,1.8);ctx.restore()}
  function hp(){ctx.beginPath();ctx.arc(0,-2,16.8,Math.PI*1.03,Math.PI*1.97);ctx.closePath()}
  hp();rim();ctx.fillStyle=e.pal[0];ctx.fill();ctx.save();hp();ctx.clip();pat(e,9,-17,-19,34,18);
  var g=ctx.createLinearGradient(0,-19,0,-2);g.addColorStop(0,'rgba(255,255,255,.16)');g.addColorStop(1,'rgba(0,0,0,.22)');ctx.fillStyle=g;ctx.fillRect(-17,-19,34,18);ctx.restore();
  hp();ctx.strokeStyle='rgba(0,0,0,.55)';ctx.lineWidth=1.8;ctx.stroke();
  ctx.save();hp();ctx.clip();rr(-18,-13.5,36,4.6,2.3);ctx.fillStyle=e.color;ctx.fill();ctx.restore();   /* the viewer's colour, so you can tell who is who */
  rr(-17.5,-5,36,4.2,2);ctx.fillStyle=e.pal[1];ctx.fill();ctx.stroke();
  ctx.strokeStyle='#15151b';ctx.lineWidth=1.6;ctx.beginPath();ctx.moveTo(-7,-1);ctx.lineTo(-4,11);ctx.stroke();
}
function cl(v){return v<0?0:v>1?1:v}
/* blood: an uneven splat with a thin drip and a fleck or two (a round ball on a stick looked like a pin) */
function splat(x,y,r,drip,sd){var g=rng(sd*7919+131);
  ctx.fillStyle='#a8101a';ctx.beginPath();ctx.ellipse(x,y,r,r*(.62+g()*.5),g()*3,0,7);ctx.fill();
  ctx.beginPath();ctx.ellipse(x+r*(.5+g()*.6),y+r*(.3-g()*.8),r*.46,r*.36,g()*3,0,7);ctx.fill();
  if(drip>0){ctx.beginPath();ctx.moveTo(x-r*.3,y);ctx.quadraticCurveTo(x-r*.12,y+drip*.6,x-r*.05,y+drip);ctx.lineTo(x+r*.25,y+drip*.86);ctx.quadraticCurveTo(x+r*.3,y+drip*.4,x+r*.3,y);ctx.closePath();ctx.fill();
    ctx.beginPath();ctx.arc(x+r*.08,y+drip,r*.2,0,7);ctx.fill()}
  ctx.fillStyle='#d2242e';ctx.beginPath();ctx.ellipse(x-r*.3,y-r*.34,r*.3,r*.22,g()*3,0,7);ctx.fill()}
function body(e){
  var still=e.fall>0||e.dead||e.dress>0||e.land>0||e.rest>0,p=e.p,sw=still?0:Math.sin(p),cs=still?0:Math.cos(p),bob=still?0:-Math.abs(cs)*1.4,hit=e.swing>0,left=e.shield-T;
  if(hit){sw*=.2;cs=0}
  HIT=hit;AR=0;
  if(!e.dead&&left>0){AR=1;if(e.dress>0){var t=DRESS-e.dress;AP=[0,1,2,3].map(function(i){var k=cl((t-i*.26)/.24);return k*k})}else{var on=(left>2||Math.sin(T*18)>0)?1:0;AP=[on,on,on,on]}}
  var aF=hit?-1.45:sw*.55,fF=hit?-.2:-.35,aB=-sw*.55,fB=-.3,lF=-sw*.5,kF=Math.max(0,cs)*.8,lB=sw*.5,kB=Math.max(0,-cs)*.8,w=Math.sin(T*13+e.ph),w2=Math.cos(T*10+e.ph);
  if(e.dead){aF=-2.3+w*.25;aB=-1.9+w2*.25;lF=-.5;lB=.3;kF=.5;kB=.3}
  else if(e.fall>0){
    if(e.fv===0){aF=-2.3+w*.4;aB=-1.9+w2*.4;fF=-.5;fB=-.5;lF=-1.25+w2*.3;lB=-.85+w*.3;kF=.55+w*.2;kB=.5+w2*.2}
    else if(e.fv===1){aF=-2.4;aB=2.2;fF=0;fB=0;lF=-.7;lB=.7;kF=.2;kB=.2}
    else{aF=-2.7+w*.5;aB=-2.7+w2*.5;fF=.3;fB=.3;lF=w*.65;lB=-w*.65;kF=.7;kB=.7}}
  else if(e.land>0&&e.fv===2){kF=.9*(e.land/LAND);kB=kF;lF=-.5*(e.land/LAND);lB=lF}
  DK=1;
  limb(e,1,0,-44+bob,11,10,6.5,aB,fB,'glove');
  limb(e,2,-1.5,-21,11,11,8,lB,kB,'boot');
  DK=0;
  part(e,7,-17,-46+bob,9,18,3);if(AR)plate(-19,-48+bob,10,21,3,AP[1]);
  limb(e,4,1.5,-21,11,11,8,lF,kF,'boot');
  part(e,5,-10,-48+bob,20,29,6);
  rr(-11,-46+bob,22,17,3);ctx.fillStyle='rgba(18,20,16,.6)';ctx.fill();ctx.strokeStyle='rgba(0,0,0,.6)';ctx.lineWidth=1.2;ctx.stroke();
  ctx.fillStyle='rgba(0,0,0,.4)';rr(2,-38+bob,7.5,7,1.5);ctx.fill();rr(-7.5,-38+bob,7.5,7,1.5);ctx.fill();
  ctx.fillStyle='rgba(255,255,255,.14)';ctx.fillRect(2,-38+bob,7.5,1.5);ctx.fillRect(-7.5,-38+bob,7.5,1.5);ctx.fillRect(-8,-43.5+bob,16,1.3);
  ctx.fillStyle='#17171d';ctx.fillRect(-10,-24+bob,20,3.5);ctx.fillStyle='#55555f';ctx.fillRect(3,-24+bob,4,3.5);
  /* 1.19.0: the coloured shoulder patch is gone. It sat right under the chin on his back half and read as a smudge,
     not a patch. The viewer's colour still shows on the helmet band and the armband, which is plenty to tell them apart. */
  if(AR){plate(-13,-49+bob,26,27,5,AP[1]);if(AP[1]>=1){ctx.save();rr(-13,-49+bob,26,27,5);ctx.clip();ctx.lineCap='round';
      [[-8,-45,-3,-27],[-1,-46,4,-26],[6,-45,10,-29]].forEach(function(L,i){ctx.strokeStyle='rgba(236,234,226,.92)';ctx.lineWidth=3.2-i*.3;ctx.beginPath();ctx.moveTo(L[0],L[1]+bob);ctx.quadraticCurveTo(L[0]+1,(L[1]+L[3])/2+bob,L[2],L[3]+bob);ctx.stroke();
        ctx.strokeStyle='rgba(236,234,226,.35)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(L[0]+2.6,L[1]+3+bob);ctx.lineTo(L[2]+2.4,L[3]-4+bob);ctx.stroke()});
      [[-9,-31],[8,-41],[2,-36]].forEach(function(d){ctx.fillStyle='#08090b';ctx.beginPath();ctx.arc(d[0],d[1]+bob,1.7,0,7);ctx.fill();ctx.strokeStyle='rgba(255,255,255,.4)';ctx.lineWidth=.7;ctx.beginPath();ctx.arc(d[0],d[1]+bob,2.3,3.4,5.6);ctx.stroke()});
      ctx.strokeStyle='rgba(0,0,0,.6)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(-13,-33+bob);ctx.lineTo(13,-36+bob);ctx.stroke();
      if(CFG.blood)[[7,-42,3.1,7],[-7.5,-36,2.5,5],[2,-28,2,0]].forEach(function(d,i){splat(d[0],d[1]+bob,d[2],d[3],e.seed+i)});ctx.restore()}
    plate(-9.5,-24+bob,19,7,3,AP[0])}
  ctx.save();ctx.translate(0,-62+bob);ctx.scale(1.12,1.12);head(e);ctx.restore();
  if(AR&&AP[3]>0){ctx.save();ctx.globalAlpha*=AP[3];ctx.translate(0,-63+bob-(1-AP[3])*45);ctx.scale(1.28,1.28);ctx.beginPath();ctx.arc(0,0,16.5,0,7);rim();ctx.fillStyle='#25272e';ctx.fill();ctx.strokeStyle='#0c0d10';ctx.lineWidth=1.6;ctx.stroke();ctx.save();ctx.beginPath();ctx.arc(0,0,16.5,0,7);ctx.clip();ctx.strokeStyle='rgba(236,234,226,.85)';ctx.lineWidth=3;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-6,-15);ctx.lineTo(-9,7);ctx.stroke();ctx.strokeStyle='rgba(236,234,226,.4)';ctx.lineWidth=1.2;ctx.beginPath();ctx.moveTo(-2,-14);ctx.lineTo(-4.5,2);ctx.stroke();if(CFG.blood)[[-10,-4,2.8,5],[3,8.5,2.1,0]].forEach(function(d,i){splat(d[0],d[1],d[2],d[3],e.seed+9+i)});ctx.restore();
    ctx.beginPath();ctx.arc(0,0,14.5,Math.PI*1.15,Math.PI*1.85);ctx.strokeStyle='rgba(255,255,255,.22)';ctx.lineWidth=2;ctx.stroke();
    rr(-1,-6.5,18,8,3);ctx.fillStyle='#0d0e12';ctx.fill();rr(1.5,-4.8,13.5,4.6,2);ctx.fillStyle=e.color;ctx.shadowColor=e.color;ctx.shadowBlur=9;ctx.fill();ctx.shadowBlur=0;
    ctx.fillStyle='#14161b';for(var q=0;q<3;q++)ctx.fillRect(6+q*3.2,5.5,1.6,6);rr(-3,-19,6,6,2);ctx.fillStyle='#17181c';ctx.fill();ctx.restore()}
  limb(e,3,0,-44+bob,11,10,6.5,aF,fF,'glove',true);
}
var TOP=86,DK=0,AR=0,AP=[1,1,1,1],HIT=0,DRESS=1.3,LAND=.55,CD=3,HURT=.24,TURN=.17,SWING=.35;
var RIMC='rgba(228,236,252,.52)',RIMW=2.6;      /* the light edge: without it dark soldiers vanish on a dark game */
var RIMS='#e4ecfc',RIMA=.52,NORIM=0,RIMEDGE=0,_bA=null,_bB=null;   /* 1.19.0: the edge goes behind the whole soldier, not around each piece */
function rim(){if(NORIM)return;ctx.strokeStyle=RIMC;ctx.lineWidth=RIMW;ctx.stroke()}
/* Draw the soldier once with no edges, work out his outline from that, lay the outline down first and him on top.
   One clean edge around the whole of him instead of one around every arm, leg and helmet.
   RIMEDGE=0 skips all of that and draws him straight onto the canvas with no edge at all: no copy, no halo,
   nothing that can be left behind. That is where it stands now — a stray outline was showing up on stream. */
function outlined(e){
  if(!RIMEDGE){NORIM=1;try{body(e)}finally{NORIM=0}return}
  var m=ctx.getTransform?ctx.getTransform():null;
  var S=m?Math.max(Math.hypot(m.a,m.b),Math.hypot(m.c,m.d)):2;
  if(!(S>.2))S=2; if(S>6)S=6;
  var arm=!e.dead&&e.shield-T>0;                       /* the armour drops in from above, so he needs more room then */
  var X0=-32,Y0=arm?-130:-94,W0=72,H0=arm?140:104,pad=Math.ceil(RIMW*S)+2;
  var bw=Math.ceil(W0*S)+pad*2,bh=Math.ceil(H0*S)+pad*2;
  if(!_bA)_bA=document.createElement('canvas');
  if(_bA.width<bw||_bA.height<bh){_bA.width=Math.max(_bA.width,bw);_bA.height=Math.max(_bA.height,bh)}
  var ga=_bA.getContext('2d');
  ga.setTransform(1,0,0,1,0,0);ga.clearRect(0,0,bw,bh);
  var hold=ctx;ctx=ga;NORIM=1;
  ctx.save();ctx.translate(pad-X0*S,pad-Y0*S);ctx.scale(S,S);
  try{body(e)}finally{ctx.restore();ctx=hold;NORIM=0}
  var dx=X0-pad/S,dy=Y0-pad/S,dw=bw/S,dh=bh/S;
  if(!RIMEDGE){ctx.drawImage(_bA,0,0,bw,bh,dx,dy,dw,dh);return}   /* RIMEDGE=0 turns the edge off if a slow machine ever needs it */
  var Q=4,hw=Math.ceil(bw/Q),hh=Math.ceil(bh/Q);        /* the edge is built small and blown back up: it is a soft halo, nobody counts its pixels */
  if(!_bB)_bB=document.createElement('canvas');
  if(_bB.width<hw||_bB.height<hh){_bB.width=Math.max(_bB.width,hw);_bB.height=Math.max(_bB.height,hh)}
  var gb=_bB.getContext('2d');
  gb.setTransform(1,0,0,1,0,0);gb.globalCompositeOperation='source-over';gb.clearRect(0,0,hw,hh);
  var r=RIMW*S/(2*Q),N=8,i,a;
  for(i=0;i<N;i++){a=i/N*6.2832;gb.drawImage(_bA,0,0,bw,bh,Math.cos(a)*r,Math.sin(a)*r,hw,hh)}
  gb.globalCompositeOperation='source-in';gb.fillStyle=RIMS;gb.fillRect(0,0,hw,hh);
  gb.globalCompositeOperation='source-over';
  var g0=ctx.globalAlpha;
  ctx.globalAlpha=g0*RIMA;ctx.drawImage(_bB,0,0,hw,hh,dx,dy,dw,dh);
  ctx.globalAlpha=g0;ctx.drawImage(_bA,0,0,bw,bh,dx,dy,dw,dh);
}
function slash(e){var k=(SWING-e.swing)/SWING;if(k>.7)return;var a0=.19-k*2.2;   /* 1.19.0: the knife comes up from below, not down from above */
  ctx.save();ctx.translate(5,-50);ctx.globalAlpha*=(1-k/.7)*.9;ctx.strokeStyle='#fff';ctx.lineCap='round';
  ctx.lineWidth=5.5-k*3.5;ctx.beginPath();ctx.arc(0,0,21,a0,a0+1.05);ctx.stroke();
  ctx.lineWidth=1.6;ctx.globalAlpha*=.6;ctx.beginPath();ctx.arc(0,0,26,a0+.1,a0+.95);ctx.stroke();ctx.restore()}
function crown(e){var y=-TOP-1+Math.sin(T*3+e.ph)*1.5;ctx.save();ctx.translate(0,y);ctx.scale(.78,.78);
  ctx.shadowColor='#ffd84d';ctx.shadowBlur=16;ctx.beginPath();ctx.moveTo(-17,0);ctx.lineTo(-20,-18);ctx.lineTo(-9,-9);ctx.lineTo(0,-23);ctx.lineTo(9,-9);ctx.lineTo(20,-18);ctx.lineTo(17,0);ctx.closePath();
  ctx.fillStyle='#ffd84d';ctx.fill();ctx.shadowBlur=0;ctx.strokeStyle='#a36b00';ctx.lineWidth=2.5;ctx.stroke();
  ctx.fillStyle='#ff5c7a';ctx.beginPath();ctx.arc(0,-7,3.2,0,7);ctx.fill();ctx.restore()}
function draw(){
  ctx.setTransform(DPR,0,0,DPR,0,0);ctx.clearRect(0,0,W,H);
  var u=U,K=CFG.crown?king():null,fsz=Math.max(11,Math.round(18*u));
  ctx.font='700 '+fsz+'px Outfit,Tajawal,sans-serif';
  var placed=[];alive().sort(function(a,b){return a.x-b.x}).forEach(function(e){e.lab=e.name+(e.wins>0?'  x'+e.wins:'');e.lw=ctx.measureText(e.lab).width+14;
    e.ly=G-(TOP*e.by+6)*e.s*u-8;placed.push(e)});
  var ms=Math.max.apply(null,placed.map(function(e){return e.s}).concat([1])),top=G-(TOP+6)*ms*u-8;placed.forEach(function(e){e.ly=top});   /* 1.19.0: one line of names, at the tallest soldier's height (a bigger winner doesn't lift his own name) */
  var list=ents.slice().sort(function(a,b){return (a.dead?-1:a.wins)-(b.dead?-1:b.wins)||a.wt-b.wt});
  list.forEach(function(e){
    ctx.save();ctx.globalAlpha=Math.max(0,e.a);
    var lung=e.swing>0?Math.sin((SWING-e.swing)/SWING*Math.PI)*9*e.s*u*e.dir:0;
    ctx.translate(e.x+lung,G-e.fall);
    if(CFG.blood&&e.dead&&e.dv<2){var bq=Math.min(1,e.dt/.9),bx=(e.dv===0?1:-1)*e.fd*22*e.s*u;ctx.fillStyle='#8a0c13';ctx.beginPath();ctx.ellipse(bx,3,30*bq*e.s*u,6*bq*e.s*u,0,0,7);ctx.fill();ctx.fillStyle='#c4141d';ctx.beginPath();ctx.ellipse(bx+3,2.5,20*bq*e.s*u,3.6*bq*e.s*u,0,0,7);ctx.fill()}
    if(e.fall<=0&&!e.dead){ctx.fillStyle='rgba(0,0,0,.4)';ctx.beginPath();ctx.ellipse(0,2,17*e.s*u*e.bx,5*e.s*u,0,0,7);ctx.fill()}
    var tq=e.tn>0?.26+.74*Math.abs(Math.cos((1-e.tn/TURN)*Math.PI)):1;   /* turning on the spot, never paper-thin */
    ctx.save();ctx.scale(e.s*u*e.dir*e.bx*tq,e.s*u*e.by);var ld=e.fd===e.dir?1:-1,q;
    if(e.dead&&e.dv===3){}
    else if(e.dead){q=Math.min(1,e.dt/.4);q=q*q;if(e.dv===2){ctx.translate(0,e.ky/(e.s*u)-40);ctx.rotate(ld*e.dt*9);ctx.translate(0,40)}
      else{var q1=Math.min(1,e.dt/.55),lean=e.dv===1?(q1<.3?.25*(q1/.3):.25-1.75*Math.pow((q1-.3)/.7,2)):1.5*q;ctx.translate(0,-10);ctx.rotate(ld*lean);ctx.translate(0,10)}}
    else if(e.fall>0){ctx.translate(0,-40);ctx.rotate(e.fv===0?-1.35+Math.sin(T*5)*.12:e.fv===1?T*8:Math.sin(T*9)*.18);ctx.translate(0,40)}
    else if(e.land>0){q=e.land/LAND;if(e.fv===2){ctx.scale(1+.18*Math.sin(q*Math.PI),1-.22*Math.sin(q*Math.PI))}
      else{var h=q>.45?1:q/.45;ctx.translate(0,-10);ctx.rotate((e.fv===0?-1.5:1.5)*h*h);ctx.translate(0,10)}}
    if(e.hurt>0){var hq=e.hurt/HURT;ctx.translate(0,-12);ctx.rotate(ld*.45*(1-hq*hq));ctx.translate(0,12)}
    var oc=RIMC,ow=RIMW,os=RIMS,oa=RIMA;if(e.flash>0){RIMC='rgba(255,255,255,.96)';RIMW=5.5;RIMS='#ffffff';RIMA=.96}
    outlined(e);RIMC=oc;RIMW=ow;RIMS=os;RIMA=oa;
    if(e.swing>0&&!e.dead)slash(e);
    ctx.restore();
    ctx.restore();
  });
  ctx.font='700 '+fsz+'px Outfit,Tajawal,sans-serif';ctx.textAlign='center';
  alive().sort(function(a,b){return a.wins-b.wins||a.wt-b.wt}).forEach(function(e){if(e.fall>0||!CFG.names)return;var ly=e.ly;rr(e.x-e.lw/2,ly-fsz-3,e.lw,fsz+9,7);ctx.fillStyle='rgba(8,8,14,.5)';ctx.fill();   /* 1.19.0: a lighter name tag */
    ctx.fillStyle=e.color;ctx.fillText(e.lab,e.x,ly)});
  if(K&&K.fall<=0){ctx.save();
    if(CFG.names){ctx.translate(K.x,K.ly-fsz-5+Math.sin(T*3+K.ph)*1.5);var cs=u*1.05;ctx.scale(cs,cs);ctx.translate(0,TOP+1-Math.sin(T*3+K.ph)*1.5)}   /* 1.19.0: the crown sits on top of the king's name tag */
    else{ctx.translate(K.x,G);ctx.scale(K.s*u,K.s*u*K.by)}   /* names off: on his head as before */
    crown(K);ctx.restore()}
  parts.forEach(function(p){ctx.globalAlpha=Math.min(1,p.life*2);ctx.fillStyle=p.c;ctx.beginPath();ctx.arc(p.x,p.y,p.r*u,0,7);ctx.fill()});ctx.globalAlpha=1;
  floats.forEach(function(f){ctx.globalAlpha=Math.min(1,f.life*2);ctx.font='900 '+Math.round(26*u+4)+'px Outfit,Tajawal,sans-serif';ctx.textAlign='center';
    ctx.lineWidth=5;ctx.lineJoin='round';ctx.lineCap='round';ctx.strokeStyle='rgba(0,0,0,.7)';ctx.strokeText(f.t,f.x,f.y);   /* round, or sharp letters shoot out black spikes */ctx.fillStyle=f.c;ctx.fillText(f.t,f.x,f.y)});ctx.globalAlpha=1;
}
function autoSpawn(){var free=NAMES.filter(function(n){return !find('demo:'+n)});if(free.length&&alive().length<Math.min(12,CFG.max||20)){var n=pick(free);spawn(n,'demo:'+n)}}
function autoAttack(){var l=alive().filter(function(e){return e.fall<=0&&e.land<=0&&T>=e.cdA&&!(e.dress>0)});if(!l.length)return;var hit=l.filter(function(e){return near(e)});
  attack(hit.length&&Math.random()<.7?pick(hit):pick(l))}
function autoProtect(){var l=alive().filter(function(e){return e.shield<=T&&T>=e.cdP&&e.fall<=0});if(l.length)protect(pick(l))}
if(DEMO)setInterval(function(){if(!CFG.on||document.hidden)return;var n=alive().length,r=Math.random();if(n<7)autoSpawn();else if(r<.3)autoSpawn();else if(r<.88)autoAttack();else autoProtect()},1300);
/* what the app says happened (about once a second). The first answer only marks "from now on": old commands are never replayed. */
var SEEN=null,BOOT=null;
window.ARENA_AFTER=function(){return SEEN==null?999999999:SEEN};
window.ARENA_FEED=function(a){if(!a||CBONLY||CHATONLY||(EDIT&&!DEMO))return;
  var c=a.cfg||{},was=[CFG.size,CFG.ground,CFG.left,CFG.right].join();CFG=c;if(DEMO)CFG.on=true;if(was!==[CFG.size,CFG.ground,CFG.left,CFG.right].join())fit();
  if(!CFG.on){ents=[];parts=[];floats=[]}
  if(BOOT!==a.boot||SEEN==null){BOOT=a.boot;SEEN=a.last;return}
  (a.events||[]).forEach(function(ev){if(ev.id<=SEEN)return;SEEN=ev.id;if(!CFG.on)return;
    if(DEMO&&ev.t!='clear'&&String(ev.u).indexOf('test:')!==0)return;       /* (the preview in the app: only its own made-up viewers) */
    if(ev.t=='spawn')spawn(ev.n||ev.u,ev.u,ev.c);else if(ev.t=='attack')attack(find(ev.u));else if(ev.t=='protect')protect(find(ev.u));
    else if(ev.t=='leave'){var le=find(ev.u);if(le&&!le.leaving){le.leaving=1;le.rest=0;le.tn=0;le.swing=0;le.dir=le.x<W/2?-1:1}}
    else if(ev.t=='clear')ents.forEach(function(e){if(!e.dead)gone(e)})})};
fit();addEventListener('resize',fit);
var last=performance.now(),idle=true;
(function loop(now){var dt=Math.min(.05,(now-last)/1000);last=now;
  if(CFG.on&&(ents.length||parts.length||floats.length)){step(dt);draw();idle=false}
  else if(!idle){ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,cv.width,cv.height);idle=true}
  requestAnimationFrame(loop)})(last);
})();
function napping(){if(window.parent===window)return false;try{return document.hidden||!!(parent.asleep&&parent.asleep())}catch(e){return false}}   // 1.19.0: the preview inside the app rests while the app is minimised (OBS never does)
async function tick(){if(napping()){setTimeout(tick,1500);return}try{var r=await fetch("/api/overlay"+(q.get("only")?"?only="+encodeURIComponent(q.get("only")):(CBONLY?"?edit=1&cb=1":CHATONLY?"?chat=1":EDIT?"?edit=1":ADEMO?"?edit=1":"")).replace(/^([^?]*)$/,"$1?x=1")+"&ar="+ARENA_AFTER(),{cache:"no-store"});
    if(r.ok){var d=await r.json();lang=d.lang=="ar"?"ar":"en";document.documentElement.dir=lang=="ar"?"rtl":"ltr";
      if(/^#[0-9a-f]{6}$/i.test(d.accent||""))document.body.style.setProperty("--acc",d.accent);
      if(d.v){if(VER&&VER!==d.v){location.reload();return}VER=d.v}
      try{ARENA_FEED(d.arena)}catch(e){console.log(e)}
      if(!ADEMO){ORDER=d.order||[];drawCounters(d.counters||[]);drawFirst(d.first);try{drawChat(d.chat)}catch(e){console.log(e)}arrange();unstack()}}}catch(e){}
  setTimeout(tick,EDIT?600:800)}
tick();
</script></body></html>"""


import hashlib as _h
VERSION = _h.sha1(OVERLAY_HTML.encode("utf-8")).hexdigest()[:10]   # changes with the app: an open overlay (OBS) reloads itself
