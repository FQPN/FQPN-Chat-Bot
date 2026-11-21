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
var ADEMO=q.get("arena")=="demo";
var ALINE=q.get("arena")=="lineup";   // 1.20.0: Overlays > Arena > Characters: a still picture of every look (soldiers or bears), nothing else    // 1.19.0: the Arena's own preview in the app (Overlays > Arena): only the soldiers, made-up viewers
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

var cv=document.getElementById('arena'),ctx=cv.getContext('2d'),CFG={on:false,kind:'soldiers',max:20,grow:'little',crown:true,size:100,names:true,blood:true},DEMO=ADEMO,DPR=1;
function isB(){return CFG.kind=='bears'}
function isG(){return CFG.kind=='bags'}   /* 1.20.0: Chat bags */
function BLD(){return !!CFG.blood&&!isG()}   /* bags never bleed */
function SPD(){var v=+CFG.speed||100;return Math.max(.5,Math.min(2,v/100))}   /* 1.20.0: Arena > Walk speed */   /* 1.20.0: Chat bears instead of Chat soldiers (same rules, other drawing) */
var W=1280,H=720,G=680,U=1;
function fit(){DPR=Math.min(2,window.devicePixelRatio||1);W=innerWidth||1280;H=innerHeight||720;U=Math.max(Math.min(W/1280,H/720),DEMO?.62:0)*(CFG.size||100)/100;   /* 1.19.1: by the smaller side, so an ultrawide or very wide source doesn't make giants */   /* the preview in the app is a small strip: the soldiers there never shrink below readable */ G=H*(DEMO?100:(+CFG.ground||100))/100-Math.max(6,14*U);   /* 1.19.1: where the ground line sits (Overlays > Arena > Where they walk) */
  cv.width=Math.round(W*DPR);cv.height=Math.round(H*DPR);ents.forEach(function(e){e.x=Math.min(RX(),Math.max(LX(),e.x))})}
/* 1.19.1: the stretch of the line the soldiers walk (left and right edge, % of the width) */
function LX(){return W*Math.max(0,Math.min(80,+CFG.left||0))/100+40}
function RX(){var r=CFG.right==null?100:+CFG.right;return Math.max(LX()+60,W*Math.max(20,Math.min(100,r))/100-40)}
var COLORS=['#ff6b85','#ffb02e','#ffe14d','#7be37b','#2fd6c3','#4db8ff','#8f9cff','#c08cff','#ff7ce0','#ff8a4d'];
var PALS=[['#4d6b3a','#2b3d20','#8a9a5b'],['#c2a878','#86693f','#e6d6ad'],['#7d8590','#474d57','#b9c0ca'],['#33507a','#1c2f4d','#6f8fbf'],
  ['#d5dae2','#8f9aab','#ffffff'],['#3b3b49','#1d1d26','#5d5d74'],['#2f6b62','#18403a','#62a898'],['#7a5a3a','#4a3421','#a98a62'],['#59663a','#7a5a3a','#262e1a']];
PALS=PALS.map(function(P){return P.map(vivid)});   /* 1.20.0: richer colours (more saturated, a touch brighter), same camo */
function vivid(h){var n=parseInt(h.slice(1),16),r=(n>>16)/255,g=(n>>8&255)/255,b=(n&255)/255,mx=Math.max(r,g,b),mn=Math.min(r,g,b),l=(mx+mn)/2,s=0,hh=0,d=mx-mn;
  if(d){s=l>.5?d/(2-mx-mn):d/(mx+mn);hh=mx==r?((g-b)/d+(g<b?6:0)):mx==g?(b-r)/d+2:(r-g)/d+4;hh/=6}
  s=Math.min(1,s*1.45);l=Math.min(.92,l*1.1);
  var q=l<.5?l*(1+s):l+s-l*s,p=2*l-q,f=function(t){t<0&&(t+=1);t>1&&(t-=1);return t<1/6?p+(q-p)*6*t:t<1/2?q:t<2/3?p+(q-p)*(2/3-t)*6:p};
  var o=s?[f(hh+1/3),f(hh),f(hh-1/3)]:[l,l,l];return '#'+o.map(function(v){return ('0'+Math.round(v*255).toString(16)).slice(-2)}).join('')}
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
  var e={name:name,key:key,born:T,paper:Math.floor(Math.random()*16),bfv:Math.floor(Math.random()*8),color:readable(color)||COLORS[i%COLORS.length],pal:PALS[(i*4)%PALS.length],ptype:PT[i%3],skin:SKINS[(i*5)%SKINS.length],seed:Math.floor(Math.random()*1e6),
    x:rnd(LX()+30,Math.max(LX()+31,RX()-30)),dir:Math.random()<.5?-1:1,sp:rnd(14,32),s:1,ts:1,wins:0,wt:0,shield:0,fall:G+80,vy:0,turn:rnd(1,4),kb:0,ph:rnd(0,6),a:1,swing:0,dress:0,p:rnd(0,6),land:0,fv:n0%3,cdA:0,cdP:0,ky:0,
    bx:BUILD[0][0],by:BUILD[0][1],hurt:0,by_:null,tn:0,tdir:0,rest:0,look:0,leaving:0,flash:0,fur:(i*3)%7,wa:0,hitT:0,hitB:null,dn:0,dm:0,et:-1,eb:'',qeat:'',bf:null,gw:0,jmp:0,ult:0,noteT:0};   /* 1.20.0: fur = which bear colour, wa = how much it is walking (bears ease in and out) */
  ents.push(e);chat(name,e.color,'!spawn');
}
function near(a){var best=null,bd=1e9;alive().forEach(function(b){if(b===a||b.fall>0)return;var d=Math.abs(b.x-a.x);if(d<HITR*(a.s+b.s)*U&&d<bd){bd=d;best=b}});return best}
function attack(a){if(!a||a.fall>0)return;chat(a.name,a.color,'!attack');if(a.dress>0||a.land>0||a.hurt>0||a.leaving||a.et>=0||a.ult>0||(DEMO&&T<a.cdA&&!(a.bf&&a.bf.k=='rage')))return;a.dn=0;a.cdA=T+CD;a.swT=isG()?SWG:SWING;a.swing=a.swT;a.tn=0;a.rest=0;var b=near(a);
  if(!b){floats.push({x:a.x,y:G-104*a.s*U,t:'MISS',c:'#b9b9c9',life:.9});return}
  a.dir=b.x>=a.x?1:-1;if(isB()||isG()){a.hitT=isG()?SWG*.5:.17;a.hitB=b}else resolve(a,b)}   /* (a bag's bat lands at the end of the wind-up) */   /* 1.20.0: a bear's claws land a moment later, when the paw comes down */
function protect(a){if(!a||a.fall>0)return;chat(a.name,a.color,'!protect');if(a.land>0||a.shield>T||a.hurt>0||a.leaving||a.et>=0||a.ult>0||(DEMO&&T<a.cdP))return;a.dn=0;a.rest=0;a.cdP=T+CD;a.dress=DRESS;a.shield=T+12+DRESS}
/* 1.20.0: !dance, !eat (one bite of pizza, one power-up) for every character */
var HITR=18,HS=0,SHK=0,IMP=[],SWG=.62,NAMEY=1e9,JUMP=.85,DANCE=3.2,EAT=1.6,FL=0,RINGS=[],BUFF={speed:['\u26a1 SPEEDY!','#7fe0ff',15],jump:['\ud83e\udd98 JUMPY!','#7dff8a',15],rage:['\ud83d\udd25 RAGE!','#ff7a3d',12],armor:['\ud83d\udee1 FREE ARMOR!','#9fd3ff',0]};
function EO(t){return 1-Math.pow(1-t,3)}
function busy(a){return a.fall>0||a.dead||a.land>0||a.hurt>0||a.leaving||a.dress>0||a.swing>0||a.et>=0||a.ult>0}
function dance(a){if(!a||busy(a))return;chat(a.name,a.color,'!dance');a.dn=DANCE;a.dm=Math.floor(Math.random()*3);a.rest=0;a.tn=0;a.noteT=0}
function eat(a,b){if(!a||a.dead||a.leaving)return;chat(a.name,a.color,'!eat');a.qeat=BUFF[b]||b=='ultra'?b:'speed'}   /* (the app has already started the long wait: the bite is never lost, it waits until he's free) */
function buffNow(e,k){var B=BUFF[k];
  if(k=='ultra'){e.ult=1.5;e.bf={k:'ultra',end:T+1.5};FL=1;floats.push({x:W/2,y:H*.4,t:'\u2620 ULTRA KILL \u2620',c:'#ffd84d',life:2.2,sz:2.2});return}
  floats.push({x:e.x,y:Math.min(G-132*e.s*U,NAMEY-50*U),t:B[0],c:B[1],life:1.5});
  if(k=='armor'){if(!(e.shield>T)){e.dress=DRESS;e.shield=T+12+DRESS}else e.shield=Math.max(e.shield,T+12);return}
  e.bf={k:k,end:T+B[2]}}
function ultraHit(a){alive().forEach(function(b){if(b===a||b.fall>0||b.hurt>0)return;b.shield=0;b.dress=0;b.dn=0;b.et=-1;b.qeat='';b.ult=0;
    b.hurt=HURT;b.by_=a;b.fd=b.x<a.x?-1:1;b.flash=.16;b.kb=b.fd*420*U;b.rest=0;b.tn=0;
    if(isB())BEAR.hit({dir:b.fd},b);spark(b.x,G-46*b.s*U,14);if(BLD())burst(b.x,G-42*b.s*U,'#d3141f',12,'#8a0c13');else if(isG())burst(b.x,G-50*b.s*U,'#c49a6c',12,'#efe2c8')});
  RINGS.push({x:a.x,t:0});FL=Math.max(FL,.8)}
function burst(x,y,color,n,alt){for(var i=0;i<n;i++)parts.push({x:x,y:y,vx:rnd(-260,260),vy:rnd(-380,-60),life:rnd(.5,1),c:Math.random()<.5?color:(alt||'#fff'),r:rnd(3,7)})}
function spark(x,y,n){for(var i=0;i<(n||9);i++){var an=rnd(0,6.283),sp=rnd(90,300);
  parts.push({x:x,y:y,vx:Math.cos(an)*sp,vy:Math.sin(an)*sp-90,life:rnd(.16,.3),c:'#fff',r:rnd(2,4.5),g:0})}}
function resolve(a,b){
  if(b.bf&&b.bf.k=='jump'&&T<b.bf.end&&Math.random()<.73){b.jmp=JUMP;a.kb=-a.dir*120*U;burst(b.x,G,'#c9c2b0',10);   /* 1.20.0: JUMPY: 73% of hits are jumped over */
    floats.push({x:b.x,y:Math.min(G-300*b.s*U,NAMEY-90*U),t:'JUMP!',c:'#7dff8a',life:1.1});return}
  if(b.shield>T&&!(b.dress>0)){b.shield=0;a.kb=-a.dir*420;if(isB())burst(b.x,G-50*b.s*U,'#a5713f',24,'#5e3a1c');else if(isG()){burst(b.x,G-50*b.s*U,'#e8f2fb',24,'#ffffff');floats.push({x:b.x+20*U,y:G-80*b.s*U,t:'POP! POP!',c:'#e8f2fb',life:1,sz:.8})}else burst(b.x,G-38*b.s*U,'#aeb4c0',22);spark(b.x+a.dir*12*U,G-48*b.s*U,12);
    if(isG()){HS=.05;SHK=Math.max(SHK,4*U);IMP.push({x:b.x-a.dir*14*b.s*U,y:G-52*b.s*U,t:0,s:b.s*.8,d:a.dir,w:1})}
    floats.push({x:b.x,y:G-104*b.s*U,t:'BLOCKED!',c:'#d5dae3',life:1.3});return}
  /* the knife lands: he jerks back first, and falls a moment later */
  b.hurt=HURT;b.by_=a;b.fd=a.dir;b.flash=.16;b.kb=a.dir*300*U;b.rest=0;b.tn=0;
  if(isG()){HS=.085;SHK=Math.max(SHK,7*U);IMP.push({x:b.x+a.dir*4*b.s*U,y:G-58*b.s*U,t:0,s:b.s,d:a.dir});b.kb=a.dir*380*U}   /* 1.20.0: a bag's hit FEELS like a hit: the world freezes for a blink, shakes, a comic impact star */
  if(isB())BEAR.hit(a,b);
  spark(b.x+a.dir*10*U,G-46*b.s*U,14);
  if(BLD())burst(b.x,G-42*b.s*U,'#d3141f',12,'#8a0c13');else if(isG()){burst(b.x,G-50*b.s*U,'#c49a6c',14,'#efe2c8');floats.push({x:b.x+a.dir*20*U,y:G-70*b.s*U,t:'BONK!',c:'#ffe9a8',life:.8,sz:.8})}   /* a bag: paper bits, BONK */
}
function finish(b){     /* the jerk is over: now he goes down */
  var a=b.by_;b.hurt=0;b.by_=null;
  b.dead=true;b.dt=0;b.dv=Math.floor(Math.random()*3);if(isG()&&b.dv===2){SHK=Math.max(SHK,10*U);HS=.06}b.kvx=b.fd*rnd(180,300)*U;b.kvy=-520*U;b.ky=0;
  if(BLD())burst(b.x,G-38*b.s*U,'#d3141f',22,'#8a0c13');else if(isG())burst(b.x,G-38*b.s*U,'#c49a6c',20,'#efe2c8');else burst(b.x,G-38*b.s*U,b.color,20);
  if(!a||a.dead)return;
  a.wins++;a.wt=T;a.ts=CFG.grow=='off'?1:CFG.grow=='lot'?Math.min(2.4,1+a.wins*.2):Math.min(1.45,1+a.wins*.07);
  floats.push({x:a.x,y:G-108*a.s*U,t:isG()&&b.dv===2?'HOME RUN!':'KO!',c:'#ffd84d',life:1.3});
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
    if(isB()||isG()){var mv=!(e.fall>0||e.dead||e.dress>0||e.land>0||e.rest>0||e.swing>0||e.hurt>0||e.dn>0||e.et>=0||e.ult>0);e.wa+=((mv?1:0)-e.wa)*Math.min(1,dt*7);   /* 1.20.0: bears ease into and out of walking */
      if(e.hitT>0){e.hitT-=dt;if(e.hitT<=0){var hb=e.hitB;e.hitB=null;if(hb&&!e.dead&&!(e.hurt>0)&&!hb.dead&&!(hb.fall>0)&&!(hb.hurt>0))resolve(e,hb)}}}
    if(e.dead){e.dt+=dt;if(e.dv===3)e.a-=dt*2.5;else if(e.dv===2){e.x+=e.kvx*dt;e.ky+=e.kvy*dt;e.kvy+=1500*U*dt;if(e.dt>1.5)e.a-=dt*1.7}else{if(e.dv===0&&e.dt<.4)e.x+=e.fd*70*U*dt;if(e.dt>2.5)e.a-=dt*1.5}return}
    if(e.fall>0){e.vy=Math.min(560*U,e.vy+1100*U*dt);e.fall-=e.vy*dt;if(e.fall<=0){e.fall=0;e.vy=0;e.land=LAND;burst(e.x,G,'#c9c2b0',12)}return}
    if(e.land>0){e.land-=dt;return}
    e.s+=(e.ts-e.s)*Math.min(1,dt*.9);if(e.bf&&T>e.bf.end)e.bf=null;if(e.jmp>0)e.jmp-=dt;if(e.swing>0)e.swing-=dt;if(e.flash>0)e.flash-=dt;
    if(Math.abs(e.kb)>5){e.x+=e.kb*dt;e.kb*=Math.pow(.02,dt)}
    if(e.hurt>0){e.hurt-=dt;if(e.hurt<=0)finish(e);return}          /* jerking back: nothing else happens */
    if(e.ult>0){var u0=e.ult;e.ult-=dt;if(u0>1.0&&e.ult<=1.0)ultraHit(e);if(e.ult<=0){e.ult=0;e.bf=null}return}   /* 1.20.0: ULTRA KILL: a wind-up, then everyone else goes down */
    if(e.qeat&&!(e.dress>0||e.swing>0||e.tn>0||e.land>0)){e.eb=e.qeat;e.qeat='';e.et=0;e.dn=0;e.rest=0}
    if(e.et>=0){var e0=e.et;e.et+=dt;
      if(e0<.7&&e.et>=.7){floats.push({x:e.x+e.dir*10*e.s*U,y:Math.min(G-108*e.s*U,NAMEY-26*U),t:'CHOMP!',c:'#ffcf6b',life:.9,sz:.8});for(var ci=0;ci<10;ci++)parts.push({x:e.x+e.dir*16*e.s*U,y:G-58*e.s*U,vx:rnd(-120,120)+e.dir*60,vy:rnd(-220,-40),life:rnd(.4,.8),c:pick(['#f2c14e','#d9862b','#c4301c','#fff2c2']),r:rnd(1.5,3)})}
      if(e0<1&&e.et>=1)buffNow(e,e.eb);
      if(e.et>=EAT)e.et=-1;return}
    if(e.dn>0){e.dn-=dt;e.noteT-=dt;if(e.noteT<=0&&e.dn>.3){e.noteT=.38;floats.push({x:e.x+rnd(-18,18)*U,y:Math.min(G-(TOP+6)*e.s*U-34*U-8,NAMEY-14*U),t:pick(['\u266a','\u266b']),c:e.color,life:1.3,sz:.75,vx:rnd(-20,20)})}
      if(e.dn<=0)e.dn=0;return}
    if(e.tn>0){e.tn-=dt;if(e.tn<=TURN/2)e.dir=e.tdir;if(e.tn<0)e.tn=0;return}
    if(e.leaving){var lx=e.sp*U*1.7*SPD()*(e.bf&&e.bf.k=='speed'?1.9:1)*dt;e.x+=e.dir*lx;e.p+=lx*6.2832/(42*e.s*U);
      if(e.x<-70||e.x>W+70)e.a=0;return}
    if(e.rest>0){e.rest-=dt;
      if(e.look>0&&(e.look-=dt)<=0)startTurn(e);                    /* a look around while he stands */
      var tgt=Math.round(e.p/6.2832)*6.2832;e.p+=(tgt-e.p)*Math.min(1,dt*7);return}   /* so he walks off again from a clean stride */
    e.turn-=dt;   /* 1.19.1: each soldier walks to a spot somewhere along the whole line (often to another soldier, so fights happen), stops a while, picks the next one */
    var reach=e.goal!=null&&Math.abs(e.goal-e.x)<10;
    if(e.turn<0||reach||e.goal==null){
      if(reach&&Math.random()<.45){e.rest=rnd(1.2,3.4);e.look=e.rest*rnd(.3,.55);e.goal=null;e.turn=e.rest+rnd(1,2)}
      else{e.goal=newGoal(e);e.turn=Math.abs(e.goal-e.x)/Math.max(1,e.sp*U*SPD())+rnd(3,6);if((e.goal-e.x)*e.dir<0)startTurn(e)}}   /* time enough to get there */
    if(e.dress>0){var a0=DRESS-e.dress;e.dress-=dt;var a1=DRESS-e.dress;
      if(ASTY&&!isB()){[12,38,50,66].forEach(function(hy,i){var li=i*.26+.24;if(a0<li&&a1>=li){var y=G-hy*e.s*U;spark(e.x+e.dir*6*U,y,7);burst(e.x,y,'#9aa3b5',4,'#3a4152');e.kb+=(Math.random()-.5)*40}})}   /* 1.20.0: each armor piece lands with a clank: sparks and bits */
      if(e.dress<=0){if(isG()){burst(e.x,G-50*e.s*U,'#e8f2fb',8,'#d6aa64');floats.push({x:e.x,y:G-104*e.s*U,t:'BUBBLE WRAP!',c:'#e8f2fb',life:1.1})}else if(ASTY&&!isB()){spark(e.x,G-55*e.s*U,18);floats.push({x:e.x,y:G-104*e.s*U,t:'ARMOR!',c:'#9fd3ff',life:1.1})}else burst(e.x,G-50*e.s*U,'#cfd4de',8)}}
    else if(e.swing<=0){var dx=e.sp*U*SPD()*(e.shield>T?.6:1)*(e.bf&&e.bf.k=='speed'?1.9:1)*dt;e.x+=e.dir*dx;e.p+=dx*6.2832/(42*e.s*U)}
    if(e.x<LX()){e.x=LX();e.goal=null;if(e.dir<0)startTurn(e)}if(e.x>RX()){e.x=RX();e.goal=null;if(e.dir>0)startTurn(e)}
  });
  ents=ents.filter(function(e){return e.a>0});
  if(isB())BEAR.step(dt);
  parts.forEach(function(p){p.vy+=(p.g===0?120:900)*dt;p.x+=p.vx*dt;p.y+=p.vy*dt;p.life-=dt});parts=parts.filter(function(p){return p.life>0});
  floats.forEach(function(f){f.y-=40*dt;if(f.vx)f.x+=f.vx*dt;f.life-=dt});SHK=SHK>.3?SHK*Math.pow(.0005,dt):0;IMP.forEach(function(m){m.t+=dt});IMP=IMP.filter(function(m){return m.t<.22});RINGS.forEach(function(r){r.t+=dt});RINGS=RINGS.filter(function(r){return r.t<.8});if(FL>0)FL-=dt*1.6;floats=floats.filter(function(f){return f.life>0});
}
function rr(x,y,w,h,r){ctx.beginPath();ctx.roundRect(x,y,w,h,r)}
function rng(seed){return function(){seed|=0;seed=seed+0x6D2B79F5|0;var t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function pat(e,key,x,y,w,h){var r=rng(e.seed+key*977),P=e.pal,i;
  if(e.ptype==='digi'){for(i=0;i<w*h/34;i++){ctx.fillStyle=r()<.55?P[1]:P[2];var b=5;ctx.fillRect(x+Math.floor(r()*w/b)*b,y+Math.floor(r()*h/b)*b,b+(r()<.45?b:0),b)}}
  else if(e.ptype==='tiger'){ctx.lineCap='round';for(i=0;i<h/7.5;i++){ctx.strokeStyle=i%3===2?P[2]:P[1];ctx.lineWidth=3.4+r()*1.8;var yy=y+i*7.5+r()*4,xx=x-2+r()*w*.4;ctx.beginPath();ctx.moveTo(xx,yy);ctx.quadraticCurveTo(xx+w*.3,yy-4+r()*4,xx+w*(.45+r()*.5),yy+r()*3);ctx.stroke()}}
  else{for(i=0;i<w*h/95+2;i++){ctx.fillStyle=r()<.6?P[1]:P[2];ctx.beginPath();ctx.ellipse(x+r()*w,y+r()*h,4.5+r()*5,3.2+r()*3.6,r()*3,0,7);ctx.fill()}}}
function part(e,key,x,y,w,h,rad){rr(x,y,w,h,rad);rim();ctx.fillStyle=e.pal[0];ctx.fill();ctx.save();rr(x,y,w,h,rad);ctx.clip();pat(e,key,x,y,w,h);
  /* 1.20.0: lit like the bears: a warm light from the front, deep shade at the back and bottom, a cool back-light on the far edge */
  var g=ctx.createLinearGradient(x,0,x+w,0);g.addColorStop(0,'rgba(0,0,0,.34)');g.addColorStop(.45,'rgba(0,0,0,0)');g.addColorStop(.75,'rgba(255,232,196,.14)');g.addColorStop(1,'rgba(255,232,196,.32)');ctx.fillStyle=g;ctx.fillRect(x,y,w,h);
  var v=ctx.createLinearGradient(0,y,0,y+h);v.addColorStop(0,'rgba(255,255,255,.18)');v.addColorStop(.35,'rgba(255,255,255,0)');v.addColorStop(1,'rgba(0,0,0,.26)');ctx.fillStyle=v;ctx.fillRect(x,y,w,h);
  if(DK){ctx.fillStyle='rgba(0,0,0,.38)';ctx.fillRect(x,y,w,h)}else{ctx.strokeStyle='rgba(150,200,255,.38)';ctx.lineWidth=2.2;ctx.beginPath();ctx.moveTo(x+1,y+rad*.6);ctx.lineTo(x+1,y+h-rad*.6);ctx.stroke()}
  ctx.restore();rr(x,y,w,h,rad);ctx.strokeStyle='rgba(14,10,16,.8)';ctx.lineWidth=1.6;ctx.stroke()}
function lit(h,a){var n=parseInt(String(h).slice(1),16);if(isNaN(n))return h;var f=function(v){return Math.max(0,Math.min(255,v+a))};return 'rgb('+f(n>>16)+','+f(n>>8&255)+','+f(n&255)+')'}
function soft(cx,cy,rx,ry,a){ctx.save();ctx.translate(cx,cy);ctx.scale(1,ry/rx);var g=ctx.createRadialGradient(0,0,0,0,0,rx);g.addColorStop(0,'rgba(0,0,0,'+a+')');g.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=g;ctx.beginPath();ctx.arc(0,0,rx,0,7);ctx.fill();ctx.restore()}
function plate(x,y,w,h,r,k){if(k<=0)return;ctx.save();
  if(ASTY){if(k<1){var p=Math.sqrt(k),e=1-Math.pow(1-p,3),sd=x+w/2<0?-1:1,cx=x+w/2,cy=y+h/2;   /* 1.20.0: each piece flies in from the side, spinning, and snaps into place */
      ctx.globalAlpha*=Math.min(1,p*3);ctx.translate(cx+sd*34*(1-e),cy-30*(1-e)*(1-e));ctx.rotate(sd*1.7*(1-e));ctx.translate(-cx,-cy)}
    plateS(x,y,w,h,r);ctx.restore();return}
  ctx.globalAlpha*=k;ctx.translate(0,-(1-k)*45);
  rr(x,y,w,h,r);rim();var pg=ctx.createLinearGradient(x,y,x+w,y+h);pg.addColorStop(0,DK?'#1b1c21':'#3a3e49');pg.addColorStop(.55,DK?'#131418':'#25272e');pg.addColorStop(1,DK?'#0c0d10':'#17181d');ctx.fillStyle=pg;ctx.fill();ctx.strokeStyle='#0c0d10';ctx.lineWidth=1.5;ctx.stroke();ctx.fillStyle='rgba(255,255,255,.24)';ctx.fillRect(x+1.5,y+1.2,w-3,1.2);if(!DK){ctx.fillStyle='rgba(150,200,255,.2)';ctx.fillRect(x+.8,y+2,1.4,h-4)}ctx.restore()}
/* 1.20.0: the soldiers' heavy armor (!protect), three looks. ASTY 0 = the old dark plates; 1 knight steel, 2 hazard mech, 3 gold energy */
var ASTY=4,CE=null,ARMF=0;   /* riot gear (picked by FQPN); 1-3 kept as other looks */
function glowOn(c,b){ctx.shadowColor=c;ctx.shadowBlur=b}function glowOff(){ctx.shadowBlur=0}
function rivet(x,y,r,c){ctx.fillStyle=c||'#3a3f48';ctx.beginPath();ctx.arc(x,y,r,0,7);ctx.fill();ctx.fillStyle='rgba(255,255,255,.55)';ctx.beginPath();ctx.arc(x-r*.3,y-r*.3,r*.4,0,7);ctx.fill()}
function hazard(x,y,w,h){ctx.save();ctx.beginPath();ctx.rect(x,y,w,h);ctx.clip();ctx.fillStyle='#f2c230';ctx.fillRect(x,y,w,h);ctx.fillStyle='#16161a';
  for(var i=-h;i<w+h;i+=5){ctx.beginPath();ctx.moveTo(x+i,y+h);ctx.lineTo(x+i+2.5,y+h);ctx.lineTo(x+i+2.5+h,y);ctx.lineTo(x+i+h,y);ctx.closePath();ctx.fill()}ctx.restore()}
function plateS(x,y,w,h,r){var g=ctx.createLinearGradient(x,y,x+w,y+h),col=CE?CE.color:'#ff6b85';
  if(ASTY==1){g.addColorStop(0,'#f3f6fa');g.addColorStop(.45,'#aeb7c3');g.addColorStop(1,'#5e6672')}
  else if(ASTY==2){g.addColorStop(0,'#6b765b');g.addColorStop(.5,'#434b39');g.addColorStop(1,'#262b21')}
  else if(ASTY==4){g.addColorStop(0,'#4a5366');g.addColorStop(.5,'#262c39');g.addColorStop(1,'#12151c')}
  else{g.addColorStop(0,'#525867');g.addColorStop(.5,'#2a2d36');g.addColorStop(1,'#14161b')}
  rr(x,y,w,h,r);ctx.fillStyle=g;ctx.fill();
  ctx.save();rr(x,y,w,h,r);ctx.clip();
  if(ASTY==2&&h>5)hazard(x,y,w,Math.min(3.6,h*.32));
  if(ASTY==4){ctx.strokeStyle='rgba(0,0,0,.5)';ctx.lineWidth=1;for(var yy=y+3.4;yy<y+h-1.5;yy+=3.4){ctx.beginPath();ctx.moveTo(x,yy);ctx.lineTo(x+w,yy);ctx.stroke()}ctx.strokeStyle='rgba(255,255,255,.1)';for(yy=y+4.2;yy<y+h-1.5;yy+=3.4){ctx.beginPath();ctx.moveTo(x,yy);ctx.lineTo(x+w,yy);ctx.stroke()}}   /* riot: padded ridges */
  if(ASTY==3&&w>12&&h>12){ctx.strokeStyle=col;ctx.lineWidth=1.3;glowOn(col,6);ctx.beginPath();ctx.moveTo(x+2,y+h*.55);ctx.lineTo(x+w-2,y+h*.45);ctx.stroke();glowOff()}
  ctx.fillStyle='rgba(255,255,255,'+(ASTY==1?.6:.22)+')';ctx.fillRect(x+1.5,y+1.2,w-3,1.2);
  if(DK){ctx.fillStyle='rgba(0,0,0,.4)';ctx.fillRect(x,y,w,h)}else{ctx.fillStyle='rgba(150,200,255,.22)';ctx.fillRect(x+.8,y+2,1.4,h-4)}
  ctx.restore();
  rr(x,y,w,h,r);ctx.strokeStyle=ASTY==3?'#e0b04a':ASTY==1?'#262a31':ASTY==4?'#07080b':'#0d0f0b';ctx.lineWidth=ASTY==3?1.3:1.5;ctx.stroke();
  if(ASTY==1){rr(x+1.6,y+1.6,w-3.2,h-3.2,Math.max(1,r-1.5));ctx.strokeStyle='rgba(216,169,59,.85)';ctx.lineWidth=.8;ctx.stroke()}
  if(ASTY!=3&&w>9&&h>8){var rc=ASTY==1?'#c79a35':ASTY==4?'#59606e':'#1b1d17';rivet(x+2.6,y+h-2.6,.9,rc);rivet(x+w-2.6,y+h-2.6,.9,rc)}}
function chestS(e,bob){var c=e.color;
  if(ASTY==1){ctx.save();ctx.translate(2,-38+bob);   /* a shield crest in the viewer's colour, gold rim */
    ctx.beginPath();ctx.moveTo(-6,-6);ctx.lineTo(6,-6);ctx.lineTo(6,0);ctx.quadraticCurveTo(6,5,0,8);ctx.quadraticCurveTo(-6,5,-6,0);ctx.closePath();
    ctx.fillStyle=c;ctx.fill();ctx.lineWidth=1.4;ctx.strokeStyle='#d8a93b';ctx.stroke();ctx.fillStyle='rgba(255,255,255,.35)';ctx.fillRect(-4.6,-4.6,9.2,1.4);
    ctx.strokeStyle='rgba(0,0,0,.35)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(0,-5);ctx.lineTo(0,6.5);ctx.moveTo(-5,-1);ctx.lineTo(5,-1);ctx.stroke();ctx.restore();
    [[-10,-45],[10,-45],[-10,-26],[10,-26]].forEach(function(p){rivet(p[0],p[1]+bob,1.1,'#c79a35')})}
  else if(ASTY==2){hazard(-13,-31+bob,26,4.2);   /* hazard band, stencil number, vents, a status light */
    ctx.fillStyle='rgba(235,235,220,.75)';ctx.font='900 7px Outfit,Arial,sans-serif';ctx.textAlign='center';ctx.fillText(String(10+(e.seed%90)),4,-37+bob);
    ctx.strokeStyle='rgba(0,0,0,.55)';ctx.lineWidth=1;for(var i=0;i<3;i++){ctx.beginPath();ctx.moveTo(-10,-44+i*2.6+bob);ctx.lineTo(-5,-44+i*2.6+bob);ctx.stroke()}
    var on=Math.sin(T*6+e.ph)>-.3;ctx.fillStyle=on?c:'#2a2a2a';if(on)glowOn(c,7);ctx.beginPath();ctx.arc(9,-44+bob,1.5,0,7);ctx.fill();glowOff();
    [[-10,-27],[10,-27]].forEach(function(p){rivet(p[0],p[1]+bob,1,'#1b1d17')})}
  else if(ASTY==4){   /* riot vest: a reflective stripe in the viewer's colour, RIOT stencil, straps */
    ctx.fillStyle=c;ctx.fillRect(-13,-34+bob,26,3.2);ctx.fillStyle='rgba(255,255,255,.45)';ctx.fillRect(-13,-34+bob,26,.9);
    ctx.fillStyle='rgba(240,242,246,.9)';ctx.font='900 6.4px Outfit,Arial,sans-serif';ctx.textAlign='center';ctx.fillText('RIOT',3,-38.5+bob);
    ctx.strokeStyle='rgba(0,0,0,.55)';ctx.lineWidth=1.2;[-6,0,6].forEach(function(xx){ctx.beginPath();ctx.moveTo(xx,-29+bob);ctx.lineTo(xx,-23.5+bob);ctx.stroke()});
    ctx.fillStyle='#0b0d12';ctx.fillRect(-12,-47+bob,4,6);ctx.fillRect(9,-47+bob,4,6)}
  else{ctx.save();ctx.translate(2,-38+bob);   /* a glowing core in the viewer's colour, gold lines */
    ctx.strokeStyle='#e0b04a';ctx.lineWidth=1.2;ctx.beginPath();ctx.moveTo(-11,-8);ctx.lineTo(0,0);ctx.lineTo(9,-8);ctx.moveTo(-11,9);ctx.lineTo(0,0);ctx.lineTo(9,9);ctx.stroke();
    ctx.fillStyle='#14161b';ctx.beginPath();ctx.arc(0,0,5.4,0,7);ctx.fill();ctx.strokeStyle='#e0b04a';ctx.lineWidth=1.4;ctx.stroke();
    var pu=.75+.25*Math.sin(T*5+e.ph);glowOn(c,10*pu);ctx.fillStyle=c;ctx.beginPath();ctx.arc(0,0,3.3*pu+.4,0,7);ctx.fill();glowOff();
    ctx.fillStyle='rgba(255,255,255,.75)';ctx.beginPath();ctx.arc(-.8,-.9,1,0,7);ctx.fill();ctx.restore()}}
function helmS(e){var c=e.color,g;
  if(ASTY==1){   /* knight's great helm: steel, an eye slit glowing in the viewer's colour, a plume in it too */
    ctx.save();ctx.translate(-4,-15);ctx.rotate(-.35);for(var i=0;i<5;i++){ctx.save();ctx.rotate(-i*.16);ctx.beginPath();ctx.moveTo(0,0);ctx.quadraticCurveTo(-8,-10-i,-20+i,-6-i*1.5);ctx.quadraticCurveTo(-10,-3,0,2);ctx.closePath();
      ctx.fillStyle=i%2?lit(hexOf(c),-30):c;ctx.fill();ctx.restore()}ctx.restore();
    rr(-15,-17,32,31,8);g=ctx.createLinearGradient(-15,-17,17,14);g.addColorStop(0,'#f3f6fa');g.addColorStop(.45,'#aeb7c3');g.addColorStop(1,'#5a626e');ctx.fillStyle=g;ctx.fill();ctx.strokeStyle='#262a31';ctx.lineWidth=1.7;ctx.stroke();
    ctx.save();rr(-15,-17,32,31,8);ctx.clip();ctx.strokeStyle='rgba(150,200,255,.45)';ctx.lineWidth=2.4;ctx.beginPath();ctx.moveTo(-14,-12);ctx.lineTo(-14,10);ctx.stroke();
      ctx.fillStyle='rgba(255,255,255,.45)';ctx.beginPath();ctx.ellipse(6,-12,7,2.2,-.15,0,7);ctx.fill();ctx.fillStyle='#d8a93b';ctx.fillRect(-15,9,32,2.4);ctx.restore();
    ctx.strokeStyle='rgba(40,44,52,.55)';ctx.lineWidth=1.2;ctx.beginPath();ctx.moveTo(8,-16);ctx.lineTo(8,13);ctx.stroke();
    rr(1,-5.5,16,4,1.6);ctx.fillStyle='#08090c';ctx.fill();rr(3,-4.6,12.5,2.2,1);glowOn(c,10);ctx.fillStyle=c;ctx.fill();glowOff();
    ctx.fillStyle='#14161b';for(var q=0;q<3;q++)for(var r2=0;r2<2;r2++){ctx.beginPath();ctx.arc(11+q*2.4,2.5+r2*2.4,.75,0,7);ctx.fill()}
    rivet(-11,-12,1.1,'#c79a35');rivet(-11,6,1.1,'#c79a35')}
  else if(ASTY==2){   /* hazard mech helmet: boxy, a wide glowing visor, side vents, a blinking antenna */
    ctx.strokeStyle='#1b1d17';ctx.lineWidth=1.4;ctx.beginPath();ctx.moveTo(-9,-15);ctx.lineTo(-13,-27);ctx.stroke();var on=Math.sin(T*5+e.ph)>0;ctx.fillStyle=on?c:'#2a2a2a';if(on)glowOn(c,8);ctx.beginPath();ctx.arc(-13,-27,1.9,0,7);ctx.fill();glowOff();
    rr(-15,-16,32,30,6);g=ctx.createLinearGradient(-15,-16,17,14);g.addColorStop(0,'#6f7a5e');g.addColorStop(.5,'#434b39');g.addColorStop(1,'#232820');ctx.fillStyle=g;ctx.fill();ctx.strokeStyle='#0d0f0b';ctx.lineWidth=1.7;ctx.stroke();
    ctx.save();rr(-15,-16,32,30,6);ctx.clip();hazard(-15,-16,32,4.2);ctx.strokeStyle='rgba(150,200,255,.4)';ctx.lineWidth=2.2;ctx.beginPath();ctx.moveTo(-14,-10);ctx.lineTo(-14,10);ctx.stroke();ctx.restore();
    ctx.strokeStyle='rgba(0,0,0,.6)';ctx.lineWidth=1.1;for(var i=0;i<4;i++){ctx.beginPath();ctx.moveTo(-11,-6+i*3);ctx.lineTo(-5,-6+i*3);ctx.stroke()}
    rr(-3,-9,21,11,3.5);ctx.fillStyle='#0a0b0d';ctx.fill();rr(-1,-7.4,17.5,7.6,2.6);glowOn(c,11);ctx.fillStyle=c;ctx.fill();glowOff();
    ctx.fillStyle='rgba(0,0,0,.28)';for(var s=0;s<4;s++)ctx.fillRect(-1,-6.6+s*1.9,17.5,.7);ctx.fillStyle='rgba(255,255,255,.55)';ctx.fillRect(1,-6.6,7,1.1);
    rr(3,5,12,5,2);ctx.fillStyle='#1b1d17';ctx.fill()}
  else if(ASTY==4){   /* riot helmet: neck guard, a stripe in the viewer's colour, a clear face shield you can see the face through */
    ctx.beginPath();ctx.moveTo(-15,2);ctx.lineTo(-17,13);ctx.quadraticCurveTo(-8,16,2,13);ctx.lineTo(0,4);ctx.closePath();g=ctx.createLinearGradient(-17,2,2,15);g.addColorStop(0,'#2b3240');g.addColorStop(1,'#10131a');ctx.fillStyle=g;ctx.fill();ctx.strokeStyle='#07080b';ctx.lineWidth=1.3;ctx.stroke();
    ctx.strokeStyle='rgba(0,0,0,.5)';ctx.lineWidth=.9;for(var nk=0;nk<3;nk++){ctx.beginPath();ctx.moveTo(-15.5+nk*.3,6+nk*2.6);ctx.lineTo(0,6+nk*2.6);ctx.stroke()}
    ctx.beginPath();ctx.arc(0,-1,16.2,Math.PI*.98,Math.PI*2.02);ctx.closePath();g=ctx.createRadialGradient(5,-10,1,0,-2,18);g.addColorStop(0,'#5d6880');g.addColorStop(.5,'#283041');g.addColorStop(1,'#11141b');ctx.fillStyle=g;ctx.fill();ctx.strokeStyle='#07080b';ctx.lineWidth=1.7;ctx.stroke();
    ctx.save();ctx.beginPath();ctx.arc(0,-1,16.2,Math.PI*.98,Math.PI*2.02);ctx.closePath();ctx.clip();ctx.fillStyle=c;ctx.fillRect(-17,-11,34,3);ctx.fillStyle='rgba(255,255,255,.4)';ctx.fillRect(-17,-11,34,.8);
      ctx.strokeStyle='rgba(150,200,255,.45)';ctx.lineWidth=2.4;ctx.beginPath();ctx.arc(0,-1,15.2,Math.PI*1.02,Math.PI*1.35);ctx.stroke();ctx.fillStyle='rgba(255,255,255,.28)';ctx.beginPath();ctx.ellipse(5,-12,6,1.8,-.2,0,7);ctx.fill();ctx.restore();
    ctx.fillStyle='#0b0d12';rr(-2,-3,20,3.2,1.4);ctx.fill();
    ctx.beginPath();ctx.moveTo(1,-1);ctx.lineTo(19,-1);ctx.quadraticCurveTo(21,8,15,15);ctx.lineTo(3,15);ctx.quadraticCurveTo(0,7,1,-1);ctx.closePath();
    g=ctx.createLinearGradient(1,0,20,14);g.addColorStop(0,'rgba(170,205,235,.18)');g.addColorStop(1,'rgba(120,160,200,.34)');ctx.fillStyle=g;ctx.fill();ctx.strokeStyle='rgba(200,225,245,.7)';ctx.lineWidth=1.1;ctx.stroke();
    ctx.strokeStyle='rgba(255,255,255,.6)';ctx.lineWidth=1.3;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(15,1.5);ctx.lineTo(18,8);ctx.moveTo(12.5,2);ctx.lineTo(13.6,5);ctx.stroke();
    if(ARMF>0){ctx.save();ctx.globalAlpha*=ARMF;glowOn(c,16);ctx.fillStyle=c;ctx.fillRect(-17,-11,34,3);ctx.fillStyle='rgba(255,255,255,.7)';ctx.beginPath();ctx.moveTo(1,-1);ctx.lineTo(19,-1);ctx.quadraticCurveTo(21,8,15,15);ctx.lineTo(3,15);ctx.quadraticCurveTo(0,7,1,-1);ctx.closePath();ctx.fill();glowOff();   /* the shield and stripe flash as it locks on */
      var sx=-4+ARMF*0+(1-ARMF)*22;ctx.fillStyle='rgba(255,255,255,.9)';ctx.fillRect(sx,-1,2.2,16);ctx.restore()}}
  else{   /* gold energy dome: gunmetal, a gold fin, two angled eye slits glowing in the viewer's colour */
    ctx.beginPath();ctx.moveTo(-14,-11);ctx.quadraticCurveTo(-4,-27,9,-17);ctx.lineTo(4,-13);ctx.quadraticCurveTo(-4,-19,-11,-8);ctx.closePath();ctx.fillStyle='#e0b04a';ctx.fill();ctx.strokeStyle='#8a6414';ctx.lineWidth=1;ctx.stroke();
    ctx.beginPath();ctx.arc(0,0,16.5,0,7);g=ctx.createRadialGradient(6,-7,1,0,0,18);g.addColorStop(0,'#666d7e');g.addColorStop(.5,'#2c2f39');g.addColorStop(1,'#121318');ctx.fillStyle=g;ctx.fill();ctx.strokeStyle='#e0b04a';ctx.lineWidth=1.5;ctx.stroke();
    ctx.save();ctx.beginPath();ctx.arc(0,0,16.5,0,7);ctx.clip();ctx.strokeStyle='rgba(150,200,255,.42)';ctx.lineWidth=2.4;ctx.beginPath();ctx.arc(0,0,15.5,Math.PI*.62,Math.PI*1.25);ctx.stroke();
      ctx.fillStyle='rgba(255,255,255,.3)';ctx.beginPath();ctx.ellipse(6,-11,6,2.2,-.4,0,7);ctx.fill();ctx.strokeStyle='#e0b04a';ctx.lineWidth=1.2;ctx.beginPath();ctx.moveTo(-16,6);ctx.quadraticCurveTo(2,12,17,4);ctx.stroke();ctx.restore();
    glowOn(c,10);ctx.fillStyle=c;ctx.beginPath();ctx.moveTo(2,-6);ctx.lineTo(9,-3.2);ctx.lineTo(8.4,-1.2);ctx.lineTo(2,-3.6);ctx.closePath();ctx.fill();
    ctx.beginPath();ctx.moveTo(11,-3.2);ctx.lineTo(16.2,-5.4);ctx.lineTo(16.4,-3.3);ctx.lineTo(11.4,-1.2);ctx.closePath();ctx.fill();glowOff()}
  if(CFG.blood&&ASTY==1)[[-10,-2,2.6,5],[4,9,2,0]].forEach(function(d,i){splat(d[0],d[1],d[2],d[3],e.seed+9+i)})}
function hexOf(c){if(/^#[0-9a-f]{6}$/i.test(c||''))return c;var m=/rgb\((\d+),\s*(\d+),\s*(\d+)/.exec(c||'');return m?'#'+[m[1],m[2],m[3]].map(function(v){return ('0'+(+v).toString(16)).slice(-2)}).join(''):'#ff6b85'}
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
  function hc(f){ctx.beginPath();ctx.arc(0,0,15,0,7);rim();var g=ctx.createRadialGradient(6,-5,1,1,0,17);g.addColorStop(0,lit(f,34));g.addColorStop(.55,f);g.addColorStop(1,lit(f,-26));ctx.fillStyle=g;ctx.fill();ctx.save();ctx.clip();ctx.strokeStyle='rgba(150,200,255,.45)';ctx.lineWidth=2.6;ctx.beginPath();ctx.arc(0,0,14.5,Math.PI*.6,Math.PI*1.25);ctx.stroke();ctx.fillStyle='rgba(255,255,255,.16)';ctx.beginPath();ctx.ellipse(7,-6,4,2.4,-.5,0,7);ctx.fill();ctx.restore();ctx.beginPath();ctx.arc(0,0,15,0,7);ctx.strokeStyle='rgba(14,10,16,.8)';ctx.lineWidth=2;ctx.stroke()}   /* 1.20.0: a round, lit head with a back-light */
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
  ctx.save();ctx.beginPath();ctx.arc(0,0,15,0,7);ctx.clip();var bs=ctx.createLinearGradient(0,-7,0,1);bs.addColorStop(0,'rgba(0,0,0,.34)');bs.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=bs;ctx.fillRect(-16,-7,32,8);ctx.restore();   /* 1.20.0: the helmet's shadow on the face */
  function hp(){ctx.beginPath();ctx.arc(0,-2,16.8,Math.PI*1.03,Math.PI*1.97);ctx.closePath()}
  hp();rim();ctx.fillStyle=e.pal[0];ctx.fill();ctx.save();hp();ctx.clip();pat(e,9,-17,-19,34,18);
  var g=ctx.createLinearGradient(0,-19,0,-2);g.addColorStop(0,'rgba(255,255,255,.16)');g.addColorStop(1,'rgba(0,0,0,.22)');ctx.fillStyle=g;ctx.fillRect(-17,-19,34,18);ctx.restore();
  ctx.save();hp();ctx.clip();ctx.fillStyle='rgba(255,250,235,.3)';ctx.beginPath();ctx.ellipse(6,-15,6.5,2.6,-.25,0,7);ctx.fill();ctx.strokeStyle='rgba(150,200,255,.42)';ctx.lineWidth=2.4;ctx.beginPath();ctx.arc(0,-2,16,Math.PI*1.08,Math.PI*1.38);ctx.stroke();ctx.restore();   /* 1.20.0: shine and back-light */
  hp();ctx.strokeStyle='rgba(14,10,16,.8)';ctx.lineWidth=2;ctx.stroke();
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
  var still=e.fall>0||e.dead||e.dress>0||e.land>0||e.rest>0||e.dn>0||e.et>=0||e.ult>0,p=e.p,sw=still?0:Math.sin(p),cs=still?0:Math.cos(p),bob=still?0:-Math.abs(cs)*1.4,hit=e.swing>0,left=e.shield-T;
  if(hit){sw*=.2;cs=0}
  HIT=hit;AR=0;CE=e;
  if(!e.dead&&left>0){AR=1;if(e.dress>0){var t=DRESS-e.dress;AP=[0,1,2,3].map(function(i){var k=cl((t-i*.26)/.24);return k*k})}else{var on=(left>2||Math.sin(T*18)>0)?1:0;AP=[on,on,on,on]}}
  var aF=hit?-1.45:sw*.55,fF=hit?-.2:-.35,aB=-sw*.55,fB=-.3,lF=-sw*.5,kF=Math.max(0,cs)*.8,lB=sw*.5,kB=Math.max(0,-cs)*.8,w=Math.sin(T*13+e.ph),w2=Math.cos(T*10+e.ph);
  if(e.dress>0&&!e.dead&&ASTY){aF=-1.05+Math.sin(T*22)*.4;fF=-.7;aB=-.55+Math.cos(T*19)*.25;fB=-.5}   /* 1.20.0: strapping the armor on */
  if(!e.dead&&e.dn>0){var dk=DANCE-e.dn,dw=Math.sin(dk*10);   /* 1.20.0: !dance */
    if(e.dm==0){aF=-1.3+dw*.4;aB=1.9-dw*.4;fF=-.9;fB=.8;lF=dw*.35;lB=-dw*.35;kF=Math.max(0,dw)*.7;kB=Math.max(0,-dw)*.7}
    else if(e.dm==1){aF=-1.0+dw*.5;aB=1.0+dw*.5;fF=-1.2;fB=1.0;lF=-.25;lB=.25;kF=.35+dw*.2;kB=.35-dw*.2}
    else{aF=-1.57+dw*.15;aB=1.57-dw*.15;fF=0;fB=0;lF=Math.max(0,dw)*-.9;kF=Math.max(0,dw)*1.2;lB=.05;kB=.05}}
  else if(!e.dead&&e.et>=0){var ek=e.et<.4?EO(e.et/.4):e.et<1?1:1-EO(Math.min(1,(e.et-1)/.5));aF=-1.05*ek;fF=-.35-1.95*ek}   /* 1.20.0: !eat: the slice goes up to the mouth */
  else if(!e.dead&&e.ult>0){var uk=1.5-e.ult;aF=uk<.5?-2.9*EO(uk/.5):-2.9+3.5*EO(Math.min(1,(uk-.5)/.12));fF=-.3}
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
  ctx.save();rr(-10,-48+bob,20,29,6);ctx.clip();soft(3,-47+bob,15,7,.5);soft(0,-21+bob,14,4,.3);ctx.restore();   /* 1.20.0: the head's shadow on the chest, the belt's on the hips */
  /* 1.19.0: the coloured shoulder patch is gone. It sat right under the chin on his back half and read as a smudge,
     not a patch. The viewer's colour still shows on the helmet band and the armband, which is plenty to tell them apart. */
  if(AR){plate(-13,-49+bob,26,27,5,AP[1]);if(AP[1]>=1&&ASTY){ctx.save();rr(-13,-49+bob,26,27,5);ctx.clip();chestS(e,bob);if(CFG.blood&&ASTY!=3)[[7,-42,3.1,7],[-7.5,-30,2.5,5]].forEach(function(d,i){splat(d[0],d[1]+bob,d[2],d[3],e.seed+i)});ctx.restore()}
    else if(AP[1]>=1){ctx.save();rr(-13,-49+bob,26,27,5);ctx.clip();ctx.lineCap='round';
      [[-8,-45,-3,-27],[-1,-46,4,-26],[6,-45,10,-29]].forEach(function(L,i){ctx.strokeStyle='rgba(236,234,226,.92)';ctx.lineWidth=3.2-i*.3;ctx.beginPath();ctx.moveTo(L[0],L[1]+bob);ctx.quadraticCurveTo(L[0]+1,(L[1]+L[3])/2+bob,L[2],L[3]+bob);ctx.stroke();
        ctx.strokeStyle='rgba(236,234,226,.35)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(L[0]+2.6,L[1]+3+bob);ctx.lineTo(L[2]+2.4,L[3]-4+bob);ctx.stroke()});
      [[-9,-31],[8,-41],[2,-36]].forEach(function(d){ctx.fillStyle='#08090b';ctx.beginPath();ctx.arc(d[0],d[1]+bob,1.7,0,7);ctx.fill();ctx.strokeStyle='rgba(255,255,255,.4)';ctx.lineWidth=.7;ctx.beginPath();ctx.arc(d[0],d[1]+bob,2.3,3.4,5.6);ctx.stroke()});
      ctx.strokeStyle='rgba(0,0,0,.6)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(-13,-33+bob);ctx.lineTo(13,-36+bob);ctx.stroke();
      if(CFG.blood)[[7,-42,3.1,7],[-7.5,-36,2.5,5],[2,-28,2,0]].forEach(function(d,i){splat(d[0],d[1]+bob,d[2],d[3],e.seed+i)});ctx.restore()}
    plate(-9.5,-24+bob,19,7,3,AP[0])}
  ctx.save();ctx.translate(0,-62+bob);ctx.scale(1.12,1.12);head(e);ctx.restore();
  if(AR&&AP[3]>0&&ASTY){var hp3=Math.sqrt(AP[3]),he=1-Math.pow(1-hp3,3);ctx.save();ctx.globalAlpha*=Math.min(1,hp3*3);ctx.translate(0,-63+bob-(1-he)*60);ctx.rotate(-(1-he)*5);ctx.scale(1.28,1.28);   /* the helmet spins down onto the head */
    var dt0=e.dress>0?DRESS-e.dress:9;ARMF=dt0>1.02&&dt0<1.3?1-(dt0-1.02)/.28:0;helmS(e);ARMF=0;ctx.restore()}
  else if(AR&&AP[3]>0){ctx.save();ctx.globalAlpha*=AP[3];ctx.translate(0,-63+bob-(1-AP[3])*45);ctx.scale(1.28,1.28);ctx.beginPath();ctx.arc(0,0,16.5,0,7);rim();ctx.fillStyle='#25272e';ctx.fill();ctx.strokeStyle='#0c0d10';ctx.lineWidth=1.6;ctx.stroke();ctx.save();ctx.beginPath();ctx.arc(0,0,16.5,0,7);ctx.clip();ctx.strokeStyle='rgba(236,234,226,.85)';ctx.lineWidth=3;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(-6,-15);ctx.lineTo(-9,7);ctx.stroke();ctx.strokeStyle='rgba(236,234,226,.4)';ctx.lineWidth=1.2;ctx.beginPath();ctx.moveTo(-2,-14);ctx.lineTo(-4.5,2);ctx.stroke();if(CFG.blood)[[-10,-4,2.8,5],[3,8.5,2.1,0]].forEach(function(d,i){splat(d[0],d[1],d[2],d[3],e.seed+9+i)});ctx.restore();
    ctx.beginPath();ctx.arc(0,0,14.5,Math.PI*1.15,Math.PI*1.85);ctx.strokeStyle='rgba(255,255,255,.22)';ctx.lineWidth=2;ctx.stroke();
    rr(-1,-6.5,18,8,3);ctx.fillStyle='#0d0e12';ctx.fill();rr(1.5,-4.8,13.5,4.6,2);ctx.fillStyle=e.color;ctx.shadowColor=e.color;ctx.shadowBlur=9;ctx.fill();ctx.shadowBlur=0;
    ctx.fillStyle='#14161b';for(var q=0;q<3;q++)ctx.fillRect(6+q*3.2,5.5,1.6,6);rr(-3,-19,6,6,2);ctx.fillStyle='#17181c';ctx.fill();ctx.restore()}
  limb(e,3,0,-44+bob,11,10,6.5,aF,fF,'glove',true);
}
/* ---- 1.20.0: Chat bears (Overlays > Arena > Characters). Same viewers, same rules as the soldiers above: only the drawing
   and the effects differ. A bear is drawn in its own units (BS) so it stands as tall as a soldier (TOP). ---- */
var BEAR=(function(){
var BS=.62,INK='rgba(22,12,20,.62)';
var FURS=[   /* real bear colours: body, belly, muzzle, inner ear, nose and eyes, paws (and the panda's black parts) */
 {body:'#6e4426',belly:'#83573a',muzzle:'#a8794f',ear:'#4a2b17',dark:'#170d06',paw:'#3b2312'},
 {body:'#8b6a48',belly:'#a2825f',muzzle:'#c4a37b',ear:'#5c412b',dark:'#1b120a',paw:'#4a3522'},
 {body:'#26211f',belly:'#322b28',muzzle:'#a8825c',ear:'#171412',dark:'#0a0807',paw:'#141110',ring:'#4a423d'},
 {body:'#985a2d',belly:'#b07243',muzzle:'#d39d6a',ear:'#663818',dark:'#1f0f06',paw:'#5a3215'},
 {body:'#eee8da',belly:'#faf6ec',ear:'#cfc5b1',dark:'#18181c',paw:'#d6ccb8'},
 {body:'#1e1a19',belly:'#e0a447',ear:'#131010',dark:'#090707',paw:'#121010',ring:'#46403c',muzzle:'#cfa877'},
 {body:'#f3f1ec',belly:'#ffffff',ear:'#1b1b1e',dark:'#111113',paw:'#1b1b1e',limb:'#1f1f22',patch:'#1b1b1e'}];
var GEAR_T=[.3,.42,.54,.66,.78,.9],GEAR=1.45;   /* when each plank of the wooden vest lands (on a 1.45 s clock, squeezed into DRESS) */
var marks=[],stains=[];
function hex(c){if(/^#[0-9a-f]{6}$/i.test(c||''))return c;var m=/rgb\((\d+),\s*(\d+),\s*(\d+)/.exec(c||'');if(!m)return '#ff6b85';
  return '#'+[m[1],m[2],m[3]].map(function(v){return ('0'+(+v).toString(16)).slice(-2)}).join('')}
function shade(h,amt){var n=parseInt(hex(h).slice(1),16),r=(n>>16)+amt,g=(n>>8&255)+amt,b=(n&255)+amt;
  r=Math.max(0,Math.min(255,r));g=Math.max(0,Math.min(255,g));b=Math.max(0,Math.min(255,b));return 'rgb('+r+','+g+','+b+')'}
function eo(t){return 1-Math.pow(1-t,3)}function ei(t){return t*t*t}function eio(t){return t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2}
function hash(n){var x=Math.sin(n*127.1+311.7)*43758.5453;return x-Math.floor(x)}
function oval(cx,cy,rx,ry){ctx.beginPath();ctx.ellipse(cx,cy,rx,ry,0,0,7)}
function vol(cx,cy,rx,ry,base,flat){if(flat)return base;
  var g=ctx.createRadialGradient(cx+rx*.32,cy-ry*.42,Math.min(rx,ry)*.08,cx+rx*.05,cy-ry*.05,Math.max(rx,ry)*1.18);
  g.addColorStop(0,shade(base,26));g.addColorStop(.42,base);g.addColorStop(1,shade(base,-38));return g}
function inked(cx,cy,rx,ry,fill,s){oval(cx,cy,rx,ry);ctx.fillStyle=fill;ctx.fill();ctx.strokeStyle=INK;ctx.lineWidth=2.3*s;ctx.stroke()}
function rimL(cx,cy,rx,ry,s,a0,a1){ctx.save();oval(cx,cy,rx,ry);ctx.clip();
  ctx.strokeStyle='rgba(150,200,255,.26)';ctx.lineWidth=3.6*s;ctx.beginPath();ctx.ellipse(cx,cy,rx,ry,0,a0,a1);ctx.stroke();ctx.restore()}
function furTex(cx,cy,rx,ry,s,seed,n){ctx.save();oval(cx,cy,rx,ry);ctx.clip();ctx.lineCap='round';ctx.lineWidth=1.25*s;
  for(var i=0;i<n;i++){var a=hash(seed+i*1.37)*6.2832,r=Math.sqrt(hash(seed+i*2.91))*.9,x=cx+Math.cos(a)*rx*r,y=cy+Math.sin(a)*ry*r,l=(3+hash(seed+i*4.7)*2.6)*s,
      lit=(x-cx)/rx-(y-cy)/ry>.35,tilt=((x-cx)/rx)*.9;
    ctx.strokeStyle=lit?'rgba(255,255,255,.16)':'rgba(0,0,0,.12)';
    ctx.beginPath();ctx.moveTo(x-tilt*l*.3,y-l*.6);ctx.quadraticCurveTo(x+l*.25,y-l*.1,x+tilt*l*.4,y+l*.5);
    ctx.moveTo(x+2*s-tilt*l*.3,y-l*.35);ctx.quadraticCurveTo(x+2*s+l*.2,y,x+2*s+tilt*l*.35,y+l*.55);ctx.stroke()}
  ctx.restore()}
function soft(cx,cy,rx,ry,a){ctx.save();ctx.translate(cx,cy);ctx.scale(1,ry/rx);var g=ctx.createRadialGradient(0,0,0,0,0,rx);
  g.addColorStop(0,'rgba(0,0,0,'+a+')');g.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=g;ctx.beginPath();ctx.arc(0,0,rx,0,7);ctx.fill();ctx.restore()}
function gore(cx,cy,rx,ry,s,seed,n,area){   /* a killer's fur: blood spots, some with a drip and a drop that slides and falls */
  ctx.save();oval(cx,cy,rx,ry);ctx.clip();
  for(var i=0;i<n;i++){var h1=hash(seed+i*5.3),h2=hash(seed+i*8.1),h3=hash(seed+i*2.2),x=area[0]+h1*(area[2]-area[0]),y=area[1]+h2*(area[3]-area[1]),r=(2.2+h3*3.4)*s;
    ctx.fillStyle='rgba(122,8,16,.92)';ctx.beginPath();ctx.ellipse(x,y,r,r*.8,h1*3,0,7);ctx.fill();
    ctx.beginPath();ctx.arc(x+r*1.1,y-r*.5,r*.32,0,7);ctx.arc(x-r*.9,y+r*.7,r*.25,0,7);ctx.fill();
    if(i%2==0){var L=(7+h2*13)*s;ctx.strokeStyle='rgba(122,8,16,.92)';ctx.lineCap='round';ctx.lineWidth=r*.7;ctx.beginPath();ctx.moveTo(x,y);ctx.quadraticCurveTo(x+.8*s,y+L*.5,x+.3*s,y+L);ctx.stroke();
      ctx.beginPath();ctx.arc(x+.3*s,y+L,r*.48,0,7);ctx.fill();
      var f=(T*.22+h3)%1;ctx.fillStyle='rgba(196,20,29,'+(1-f*f)+')';ctx.beginPath();ctx.ellipse(x+.4*s,y+L+f*16*s,r*.38,r*.5,0,0,7);ctx.fill()}
    ctx.fillStyle='rgba(255,160,160,.35)';ctx.beginPath();ctx.arc(x-r*.3,y-r*.3,r*.28,0,7);ctx.fill()}
  ctx.restore()}
function point(x,y,dx,dy,w){ctx.moveTo(x-dy*w,y+dx*w);ctx.quadraticCurveTo(x+dx*.55-dy*w*.2,y+dy*.55+dx*w*.2,x+dx,y+dy);ctx.quadraticCurveTo(x+dx*.45+dy*w*.6,y+dy*.45-dx*w*.6,x+dy*w,y-dx*w)}
function cheeks(hx,hy,col,s){ctx.fillStyle=col;ctx.beginPath();
  point(hx-25*s,hy+5*s,-4.5*s,3*s,.5);point(hx-23*s,hy+10*s,-3.5*s,4*s,.5);point(hx+25*s,hy+6*s,4*s,3*s,.5);point(hx+23*s,hy+11*s,3*s,4*s,.5);
  point(hx-2*s,hy-22*s,-1.5*s,-4.5*s,.5);point(hx+3*s,hy-22*s,2*s,-4*s,.5);ctx.fill()}
function fluff(x,y,col,s){ctx.fillStyle=col;ctx.beginPath();point(x-7*s,y+4*s,-2*s,-6*s,.35);point(x,y+2*s,0,-7*s,.35);point(x+7*s,y+4*s,2*s,-6*s,.35);ctx.fill()}
function star(x,y,r,c){ctx.save();ctx.translate(x,y);ctx.fillStyle=c;ctx.beginPath();for(var i=0;i<10;i++){var a=i*Math.PI/5-Math.PI/2,rr=i%2?r*.45:r;ctx.lineTo(Math.cos(a)*rr,Math.sin(a)*rr)}ctx.closePath();ctx.fill();ctx.restore()}

/* one bear, facing right, feet at (0,0). The caller has already moved, flipped, grown and tipped it (exactly as for a soldier). */
function draw(e){
  var s=BS,F=FURS[e.fur%FURS.length],amp=e.wa||0,ph=e.p*1.3,L=13*s,time=T,blood=CFG.blood!==false;
  var flash=e.flash>0,hurt=e.hurt>0,dead=!!e.dead,falling=e.fall>0;
  var body=flash?'#ffffff':F.body,belly=flash?'#ffffff':F.belly;
  var kk=e.swing>0?(SWING-e.swing)/SWING:-1,wind=kk>=0&&kk<.45,swipe=kk>=.45&&kk<.62,mad=wind||swipe;
  var left=e.shield-T,gp=-1,blinkV=1;
  if(!dead&&left>0){if(e.dress>0)gp=(DRESS-e.dress)*GEAR/DRESS;else{gp=9;if(left<2.2)blinkV=.45+.55*Math.abs(Math.cos(left*9))}}
  var K=dead?0:Math.min(e.wins||0,5),seed=e.seed%997;
  var breathe=Math.sin(time*2.2+e.ph)*.018*(1-amp),bob=Math.abs(Math.sin(ph))*4*s*amp;
  ctx.save();ctx.scale(1,1+breathe);
  var lean=.07*amp;if(wind)lean=-.16*eo(kk/.45);if(swipe)lean=.22;if(hurt)lean=-.18;
  function foot(p){p=((p%6.2832)+6.2832)%6.2832;if(p<Math.PI)return{x:(L-p/Math.PI*2*L)*amp,y:0};
    var q=(p-Math.PI)/Math.PI;return{x:(-L+eio(q)*2*L)*amp,y:-Math.sin(q*Math.PI)*9*s*amp}}
  function leg(p,back){var f=foot(p),hx=back?-7*s:7*s,hy=-24*s-bob;f.x+=(back?-8:8)*s;   /* each foot under its own hip: standing legs never cross */
    var lc=flash?'#ffffff':(F.limb||body);ctx.lineCap='round';
    function path(){ctx.beginPath();ctx.moveTo(hx,hy);ctx.quadraticCurveTo((hx+f.x)/2+2*s,(hy+f.y-7*s)/2,f.x,f.y-7*s)}
    path();ctx.strokeStyle=INK;ctx.lineWidth=19.6*s;ctx.stroke();
    path();ctx.strokeStyle=back?shade(lc,-30):shade(lc,-8);ctx.lineWidth=15*s;ctx.stroke();
    if(!flash){ctx.save();ctx.translate(-3.5*s,0);path();ctx.strokeStyle='rgba(0,0,0,.18)';ctx.lineWidth=6*s;ctx.stroke();ctx.restore();
      ctx.save();ctx.translate(3.5*s,-1*s);path();ctx.strokeStyle='rgba(255,255,255,'+(back?.05:.13)+')';ctx.lineWidth=4*s;ctx.stroke();ctx.restore()}
    inked(f.x+3*s,f.y-4*s,10*s,5*s,flash?'#fff':vol(f.x+3*s,f.y-4*s,10*s,5*s,F.paw,false),s);
    if(back){ctx.fillStyle='rgba(0,0,0,.22)';oval(f.x+3*s,f.y-4*s,10*s,5*s);ctx.fill()}}
  leg(ph+Math.PI,true);leg(ph,false);
  ctx.save();ctx.translate(0,-bob);ctx.rotate(lean);
  var sw=Math.cos(ph)*.55*amp,wv=Math.sin(T*13+e.ph);
  var dB=!dead&&e.dn>0?(e.dm==0?2.5-Math.sin((DANCE-e.dn)*10)*.4:e.dm==1?1.2+Math.sin((DANCE-e.dn)*10)*.5:1.6):null;   /* 1.20.0: !dance */
  arm(-2*s,-72*s,dB!=null?dB:mad?.35:gp>=0&&e.dress>0?-.5:falling?-2.2+wv*.4:-sw+.08,true,0);
  inked(-29*s,-36*s,6.5*s,6.5*s,flash?body:shade(body,-30),s);
  inked(0,-52*s,29*s,36*s,vol(0,-52*s,29*s,36*s,body,flash),s);
  if(!flash){furTex(0,-52*s,29*s,36*s,s,seed,18);rimL(0,-52*s,29*s,36*s,s,Math.PI*.62,Math.PI*1.42)}
  ctx.fillStyle=vol(5*s,-46*s,19*s,24*s,F.belly,flash);oval(5*s,-46*s,19*s,24*s);ctx.fill();
  if(!flash){furTex(5*s,-46*s,19*s,24*s,s,seed+50,10);ctx.save();oval(0,-52*s,29*s,36*s);ctx.clip();soft(2*s,-20*s,26*s,9*s,.3);ctx.restore()}
  fluff(5*s,-70*s,belly,s);
  if(dead&&e.dv<3&&blood){ctx.save();oval(0,-52*s,29*s,36*s);ctx.clip();ctx.lineCap='round';   /* the scratch wounds */
    for(var w=0;w<3;w++){var wx=-10*s+w*9*s;ctx.strokeStyle='#5a050b';ctx.lineWidth=6*s;ctx.beginPath();ctx.moveTo(wx-6*s,-78*s);ctx.lineTo(wx+6*s,-40*s);ctx.stroke();
      ctx.strokeStyle='#c4141d';ctx.lineWidth=3*s;ctx.beginPath();ctx.moveTo(wx-6*s,-78*s);ctx.lineTo(wx+6*s,-40*s);ctx.stroke();
      ctx.strokeStyle='#8a0c13';ctx.lineWidth=2.4*s;ctx.beginPath();ctx.moveTo(wx+4*s,-46*s);ctx.lineTo(wx+4.5*s,-46*s+Math.min(1,e.dt/1.2)*16*s);ctx.stroke()}
    ctx.restore()}
  if(gp>=0)vest(gp,s,blinkV);
  if(K>0&&!flash&&blood)gore(0,-52*s,29*s,36*s,s,seed+7,2+K*2,[-14*s,-82*s,24*s,-34*s]);
  if(!flash){ctx.save();oval(0,-52*s,29.5*s,36.5*s);ctx.clip();soft(5*s,-82*s,30*s,13*s,.42);ctx.restore()}
  var hx=4*s,hy=-105*s,nod=Math.sin(ph*2)*.04*amp+Math.sin(time*.9+e.ph)*.05*(1-amp);
  ctx.save();ctx.translate(hx,hy+14*s);ctx.rotate(nod);ctx.translate(-hx,-hy-14*s);
  [[hx-17*s,hy-19*s],[hx+15*s,hy-21*s]].forEach(function(p){var ec=flash?'#ffffff':(F.patch||F.body);
    inked(p[0],p[1],9.5*s,9.5*s,vol(p[0],p[1],9.5*s,9.5*s,ec,flash),s);
    var ig=flash?'#fff':ctx.createRadialGradient(p[0],p[1]+1.5*s,0,p[0],p[1],5.2*s);if(!flash){ig.addColorStop(0,shade(F.ear,-30));ig.addColorStop(1,F.ear)}
    ctx.fillStyle=ig;oval(p[0],p[1],4.8*s,4.8*s);ctx.fill()});
  inked(hx,hy,27*s,24*s,vol(hx,hy,27*s,24*s,body,flash),s);
  cheeks(hx,hy,flash?body:shade(body,-6),s);
  if(!flash){furTex(hx,hy,27*s,24*s,s,seed+90,14);rimL(hx,hy,27*s,24*s,s,Math.PI*.7,Math.PI*1.4)}
  if(!flash)soft(hx+10*s,hy+15*s,13*s,5*s,.25);
  ctx.fillStyle=flash?'#fff':vol(hx+10*s,hy+9*s,12*s,9*s,F.muzzle||F.belly,false);oval(hx+10*s,hy+9*s,12*s,9*s);ctx.fill();
  if(K>0&&!flash&&blood)gore(hx,hy,27*s,24*s,s,seed+31,Math.min(4,K+1),[hx-16*s,hy+7*s,hx+24*s,hy+17*s]);
  ctx.fillStyle=F.dark;oval(hx+14*s,hy+4*s,4.6*s,3.3*s);ctx.fill();
  ctx.fillStyle='rgba(255,255,255,.55)';oval(hx+15.2*s,hy+2.6*s,1.9*s,1*s);ctx.fill();
  ctx.strokeStyle=F.dark;ctx.fillStyle=F.dark;ctx.lineWidth=1.8*s;ctx.lineCap='round';
  var grr=K>0&&!hurt;
  if(grr&&!mad){ctx.beginPath();ctx.moveTo(hx+7*s,hy+13*s);ctx.quadraticCurveTo(hx+13.5*s,hy+9*s,hx+20*s,hy+13*s);ctx.quadraticCurveTo(hx+13.5*s,hy+16.5*s,hx+7*s,hy+13*s);ctx.fill();   /* a snarl with two fangs */
    ctx.fillStyle='#fff';[10.5,16.5].forEach(function(f){ctx.beginPath();ctx.moveTo(hx+(f-1.5)*s,hy+11.4*s);ctx.lineTo(hx+(f+1.5)*s,hy+11.4*s);ctx.lineTo(hx+f*s,hy+14.2*s);ctx.fill()});ctx.fillStyle=F.dark}
  else if(mad||hurt||falling){ctx.beginPath();ctx.ellipse(hx+12*s,hy+13*s,3.4*s,(hurt?3.8:3)*s,0,0,7);ctx.fill()}
  else{ctx.beginPath();ctx.moveTo(hx+14*s,hy+8*s);ctx.quadraticCurveTo(hx+11*s,hy+13*s,hx+8*s,hy+11*s);ctx.moveTo(hx+14*s,hy+8*s);ctx.quadraticCurveTo(hx+17*s,hy+13*s,hx+20*s,hy+11*s);ctx.stroke()}
  var E=[[hx-6*s,hy-6*s],[hx+17*s,hy-7*s]],blink=((time*.9+e.ph*3)%3.7)<.12;
  if(dead){ctx.lineWidth=2.4*s;E.forEach(function(p){ctx.beginPath();ctx.moveTo(p[0]-4*s,p[1]-4*s);ctx.lineTo(p[0]+4*s,p[1]+4*s);ctx.moveTo(p[0]+4*s,p[1]-4*s);ctx.lineTo(p[0]-4*s,p[1]+4*s);ctx.stroke()})}
  else E.forEach(function(p,i){
    if(F.patch){ctx.fillStyle=F.patch;ctx.beginPath();ctx.ellipse(p[0]-.5*s,p[1]+1.5*s,7.5*s,9.5*s,i?.5:-.5,0,7);ctx.fill()}
    else if(F.ring){ctx.fillStyle=F.ring;ctx.beginPath();ctx.ellipse(p[0],p[1],6.2*s,6.8*s,0,0,7);ctx.fill()}
    if(blink||hurt){ctx.strokeStyle=F.dark;ctx.lineWidth=2.4*s;ctx.beginPath();if(hurt){ctx.moveTo(p[0]-4*s,p[1]-3*s);ctx.lineTo(p[0]+3*s,p[1]);ctx.lineTo(p[0]-4*s,p[1]+3*s)}else{ctx.moveTo(p[0]-4*s,p[1]);ctx.quadraticCurveTo(p[0],p[1]+3*s,p[0]+4*s,p[1])}ctx.stroke()}
    else{if(grr){ctx.save();ctx.beginPath();var yo=i?-1.2:-4.2,yi=i?-4.2:-1.2;ctx.moveTo(p[0]-9*s,p[1]+yo*s);ctx.lineTo(p[0]+9*s,p[1]+yi*s);ctx.lineTo(p[0]+9*s,p[1]+9*s);ctx.lineTo(p[0]-9*s,p[1]+9*s);ctx.clip()}   /* angry: the eye's top hides under the brow */
      ctx.fillStyle=F.dark;ctx.beginPath();ctx.ellipse(p[0],p[1],4.3*s,5*s,0,0,7);ctx.fill();ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(p[0]+1.4*s,p[1]-1.8*s,1.5*s,0,7);ctx.fill();
      ctx.globalAlpha*=.75;ctx.beginPath();ctx.arc(p[0]-1.5*s,p[1]+2*s,.75*s,0,7);ctx.fill();ctx.globalAlpha/=.75;if(grr)ctx.restore()}
    if(grr&&!mad){ctx.strokeStyle=F.ring||F.patch?'#000':F.dark;ctx.lineWidth=3.2*s;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(p[0]-7*s,p[1]+(i?-3:-7.5)*s);ctx.lineTo(p[0]+7*s,p[1]+(i?-7.5:-3)*s);ctx.stroke()}
    if(mad){ctx.strokeStyle=F.dark;ctx.lineWidth=(grr?3.2:2.2)*s;ctx.beginPath();ctx.moveTo(p[0]-6*s,p[1]-(i?6:10)*s);ctx.lineTo(p[0]+6*s,p[1]-(i?10:6)*s);ctx.stroke()}});
  ctx.fillStyle='rgba(255,120,150,'+(hurt?.7:K>0?.12:(F.ring||F.patch?.22:.38))+')';ctx.beginPath();ctx.ellipse(hx-12*s,hy+6*s,5.3*s,3.1*s,0,0,7);ctx.ellipse(hx+24*s,hy+5*s,4.3*s,2.9*s,0,0,7);ctx.fill();
  bandana(e,hx,hy,s,amp);
  ctx.restore();
  var a,claws=0;   /* the front arm, drawn last: on top of the head when it comes up for a swipe */
  if(wind){a=sw*(1-eo(kk/.45))-2.75*eo(kk/.45);claws=1}
  else if(swipe){var q=(kk-.45)/.17;a=-2.75+2.55*ei(q);claws=1;
    ctx.save();ctx.globalAlpha*=.55*(1-q*.6);ctx.strokeStyle='#fff';ctx.lineWidth=7*s;ctx.lineCap='round';ctx.beginPath();ctx.arc(1*s,-72*s,40*s,-Math.PI/2-2.75+Math.PI,-Math.PI/2+a+Math.PI,false);ctx.stroke();ctx.restore()}
  else if(kk>=.62)a=-.2*(1-(kk-.62)/.38);
  else if(!dead&&e.dn>0){var dk=DANCE-e.dn,dw=Math.sin(dk*10);a=e.dm==0?-1.7+dw*.45:e.dm==1?-1.3+dw*.5:-1.6}   /* 1.20.0: !dance */
  else if(!dead&&e.et>=0){a=-2.25*(e.et<.4?eo(e.et/.4):e.et<1?1:1-eo(Math.min(1,(e.et-1)/.5)))}   /* !eat: paw to the mouth */
  else if(!dead&&e.ult>0){var uk=1.5-e.ult;claws=1;a=uk<.5?-2.75*eo(uk/.5):-2.75+2.55*ei(Math.min(1,(uk-.5)/.15))}
  else if(e.dress>0&&gp>=0)a=gp<1.05?-1.1+Math.sin(gp*20)*.35:-.3;   /* patting each plank into place */
  else if(dead)a=-1.3;
  else if(falling)a=-2.6+Math.cos(T*10+e.ph)*.4;
  else if(hurt)a=-.9;
  else a=sw+.04;
  arm(1*s,-72*s,a,false,claws);
  ctx.restore();
  if(dead&&e.dv<2&&e.dt<1.6){for(var j=0;j<3;j++){var an=time*5+j*2.1;star(Math.cos(an)*30*s,-130*s+Math.sin(an)*9*s,7*s,'#ffd84d')}}
  ctx.restore();
  function arm(ax,ay,rot,back,cl){
    ctx.save();ctx.translate(ax,ay);ctx.rotate(rot);
    var ac=flash?'#ffffff':(F.limb||body);
    var ag=flash?ac:ctx.createLinearGradient(-7*s,0,7*s,0);if(!flash){ag.addColorStop(0,shade(ac,back?-48:-8));ag.addColorStop(.55,shade(ac,back?-22:16));ag.addColorStop(1,shade(ac,back?-14:34))}
    if(!back&&!flash){ctx.fillStyle='rgba(0,0,0,.28)';oval(-3.5*s,17*s,8*s,15.5*s);ctx.fill()}
    oval(0,15*s,7*s,15*s);ctx.fillStyle=ag;ctx.fill();ctx.strokeStyle=back?INK:'rgba(22,12,20,.38)';ctx.lineWidth=(back?2.3:1.6)*s;ctx.stroke();
    inked(0,28*s,6.5*s,6.5*s,flash?'#fff':vol(0,28*s,6.5*s,6.5*s,F.paw,false),s);
    if(back){ctx.fillStyle='rgba(0,0,0,.2)';oval(0,28*s,6.5*s,6.5*s);ctx.fill()}
    if(!back&&!flash){ctx.fillStyle='rgba(0,0,0,.25)';for(var k=-1;k<=1;k++){oval(k*2.6*s,31.5*s,1.1*s,1.6*s);ctx.fill()}}
    if(!back&&K>0&&!flash&&blood){ctx.save();oval(0,28*s,6.5*s,6.5*s);ctx.clip();ctx.fillStyle='rgba(140,8,18,.75)';oval(0,33*s,8*s,6*s);ctx.fill();ctx.restore()}
    if(cl){ctx.strokeStyle=blood&&K>0?'#c4141d':'#fff';ctx.lineWidth=2.2*s;ctx.lineCap='round';for(var k=-1;k<=1;k++){ctx.beginPath();ctx.moveTo(k*3.5*s,33*s);ctx.lineTo(k*4.6*s,40*s);ctx.stroke()}}
    ctx.restore()}
}
function vest(gp,s,alpha){ctx.save();ctx.globalAlpha*=alpha;   /* !protect: a wooden vest builds itself on, plank by plank, then rope straps tie on */
  var woods=['#b07a45','#9c6a3a','#b98552','#a5713f','#b07a45','#9c6a3a'],x0=-24*s,pw=9.4*s,flying=[];
  ctx.save();ctx.beginPath();ctx.ellipse(0,-52*s,29.5*s,36.5*s,0,0,7);ctx.clip();
  for(var k=0;k<6;k++){var px=x0+k*pw,top=-80*s+Math.abs(k-2.5)*2.2*s,bot=-27*s-Math.abs(k-2.5)*1.2*s,land=GEAR_T[k],q=(gp-(land-.22))/.22;
    if(q<0)continue;if(q<1){flying.push([k,px,top,bot,q]);continue}
    var bump=gp-land<.12?Math.sin((gp-land)/.12*Math.PI)*2.5*s:0;
    ctx.fillStyle=woods[k];ctx.fillRect(px,top+bump,pw,bot-top);
    ctx.strokeStyle='rgba(70,40,18,.35)';ctx.lineWidth=1.1*s;ctx.beginPath();ctx.moveTo(px+pw*.35,top+6*s+bump);ctx.quadraticCurveTo(px+pw*.6,(top+bot)/2+bump,px+pw*.3,bot-5*s+bump);ctx.stroke();
    ctx.strokeStyle='#5e3a1c';ctx.lineWidth=1.8*s;ctx.strokeRect(px,top+bump,pw,bot-top);
    var nq=Math.min(1,(gp-land-.04)/.08);if(nq>0){ctx.fillStyle='#3e2a1a';ctx.beginPath();ctx.arc(px+pw/2,top+5*s+bump,1.3*s*nq,0,7);ctx.arc(px+pw/2,bot-5*s+bump,1.3*s*nq,0,7);ctx.fill()}}
  if(gp>GEAR_T[5]){ctx.fillStyle='rgba(255,235,200,.18)';ctx.fillRect(x0,-80*s,pw*1.2,55*s)}
  ctx.restore();
  flying.forEach(function(f){var k=f[0],e=eo(f[4]),side=k<3?-1:1,dx=side*(46-k%3*8)*s*(1-e),dy=-70*s*(1-e)*(1-e),rot=side*1.6*(1-e);
    ctx.save();ctx.translate(f[1]+pw/2+dx,(f[2]+f[3])/2+dy);ctx.rotate(rot);ctx.globalAlpha*=Math.min(1,f[4]*3);
    ctx.fillStyle=woods[k];ctx.fillRect(-pw/2,-(f[3]-f[2])/2,pw,f[3]-f[2]);ctx.strokeStyle='#5e3a1c';ctx.lineWidth=1.8*s;ctx.strokeRect(-pw/2,-(f[3]-f[2])/2,pw,f[3]-f[2]);ctx.restore()});
  var rq=Math.max(0,Math.min(1,(gp-.78)/.3));
  if(rq>0){ctx.strokeStyle='#c9a86a';ctx.lineWidth=3.2*s;ctx.lineCap='round';
    var strap=function(ax,ay,cx,cy,bx,by){ctx.beginPath();ctx.moveTo(ax,ay);for(var i=1;i<=12*rq;i++){var u=i/12,iu=1-u;ctx.lineTo(iu*iu*ax+2*iu*u*cx+u*u*bx,iu*iu*ay+2*iu*u*cy+u*u*by)}ctx.stroke()};
    strap(-15*s,-76*s,-12*s,-90*s,-2*s,-88*s);strap(22*s,-76*s,20*s,-90*s,10*s,-88*s);
    if(rq>=1){ctx.strokeStyle='rgba(120,90,40,.6)';ctx.lineWidth=1*s;ctx.beginPath();ctx.moveTo(-14*s,-80*s);ctx.lineTo(-11*s,-84*s);ctx.moveTo(20*s,-80*s);ctx.lineTo(17*s,-84*s);ctx.stroke()}}
  ctx.restore()}
function bandana(e,hx,hy,s,amp){   /* in the viewer's chat colour: a cloth band round the head, dots, stitching, a knot with two tails that flutter */
  var c=hex(e.color),dk=shade(c,-55),md=shade(c,-25),lt=shade(c,45),fl=Math.sin(T*9+e.ph)*(.25+amp*.55),fl2=Math.sin(T*9+e.ph+1.3)*(.25+amp*.55);
  function band(){ctx.beginPath();ctx.moveTo(hx-31*s,hy-11*s);ctx.quadraticCurveTo(hx,hy-21*s,hx+31*s,hy-13*s);ctx.lineTo(hx+31*s,hy-25*s);ctx.quadraticCurveTo(hx,hy-35*s,hx-31*s,hy-23*s);ctx.closePath()}
  ctx.save();ctx.beginPath();ctx.ellipse(hx,hy,27.2*s,24.2*s,0,0,7);ctx.clip();
  var g=ctx.createLinearGradient(0,hy-34*s,0,hy-11*s);g.addColorStop(0,lt);g.addColorStop(.35,c);g.addColorStop(1,md);
  ctx.fillStyle='rgba(0,0,0,.18)';ctx.save();ctx.translate(0,2*s);band();ctx.fill();ctx.restore();
  ctx.fillStyle=g;band();ctx.fill();
  ctx.save();band();ctx.clip();ctx.fillStyle='rgba(255,255,255,.8)';
  for(var r=0;r<2;r++)for(var k=-3;k<=3;k++){var u=k/3.4,x=hx+u*27*s+(r?4.5*s:0),y=hy-(r?27:19)*s-(1-u*u)*5*s+(r?0:1.5*s);ctx.beginPath();ctx.arc(x,y,1.3*s,0,7);ctx.fill()}
  ctx.strokeStyle='rgba(0,0,0,.22)';ctx.lineWidth=1.2*s;
  [[-16,.3],[2,-.2],[17,.25]].forEach(function(f){ctx.beginPath();ctx.moveTo(hx+f[0]*s,hy-31*s+Math.abs(f[0])*.08*s);ctx.quadraticCurveTo(hx+(f[0]+3)*s,hy-24*s,hx+(f[0]+f[1]*10)*s,hy-16*s+Math.abs(f[0])*.06*s);ctx.stroke()});
  ctx.restore();
  ctx.setLineDash([2.2*s,2*s]);ctx.strokeStyle='rgba(255,255,255,.55)';ctx.lineWidth=1*s;
  ctx.beginPath();ctx.moveTo(hx-31*s,hy-13.5*s);ctx.quadraticCurveTo(hx,hy-23.5*s,hx+31*s,hy-15.5*s);ctx.moveTo(hx-31*s,hy-20.5*s);ctx.quadraticCurveTo(hx,hy-32.5*s,hx+31*s,hy-22.5*s);ctx.stroke();ctx.setLineDash([]);
  ctx.strokeStyle=dk;ctx.lineWidth=1.5*s;band();ctx.stroke();
  ctx.restore();
  var kx=hx-25*s,ky=hy-17*s;
  function tail(len,lift,f,col){ctx.save();ctx.translate(kx,ky);ctx.rotate(.15+lift+f*.4);
    var tg=ctx.createLinearGradient(0,-4*s,0,4*s);tg.addColorStop(0,lt);tg.addColorStop(1,col);ctx.fillStyle=tg;ctx.strokeStyle=dk;ctx.lineWidth=1.4*s;
    ctx.beginPath();ctx.moveTo(0,-3.6*s);ctx.bezierCurveTo(-len*.35,-5*s+f*3*s,-len*.7,-2*s-f*4*s,-len,-4.5*s-f*5*s);
    ctx.lineTo(-len*.86,0);ctx.lineTo(-len*1.02,4.5*s-f*5*s);
    ctx.bezierCurveTo(-len*.7,4*s-f*4*s,-len*.35,5*s+f*3*s,0,3.6*s);ctx.closePath();ctx.fill();ctx.stroke();
    ctx.strokeStyle='rgba(0,0,0,.2)';ctx.lineWidth=1*s;ctx.beginPath();ctx.moveTo(-3*s,0);ctx.quadraticCurveTo(-len*.4,f*2*s,-len*.75,-f*3*s);ctx.stroke();ctx.restore()}
  tail(17*s,.55,fl2,md);tail(20*s,-.1,fl,c);
  var kg=ctx.createRadialGradient(kx+1*s,ky-1.5*s,.5*s,kx,ky,5*s);kg.addColorStop(0,lt);kg.addColorStop(1,md);
  ctx.fillStyle=kg;ctx.strokeStyle=dk;ctx.lineWidth=1.4*s;ctx.beginPath();ctx.ellipse(kx,ky,4.6*s,5.4*s,.3,0,7);ctx.fill();ctx.stroke()}

/* effects that only bears have: claw marks where a scratch lands, blood drops that splat on the floor */
function hit(a,b){var u=U*b.s,y=G-50*u;marks.push({x:b.x,y:y,dir:a.dir,u:u,t:0});
  if(!CFG.blood)return;for(var i=0;i<26;i++){var sp=rnd(80,330)*U;parts.push({x:b.x+rnd(-5,5)*U,y:y+rnd(-9,9)*U,vx:a.dir*sp*rnd(.5,1)+rnd(-50,50)*U,vy:-rnd(50,280)*U,life:2.5,c:pick(['#7d0a12','#a30f1b','#c4141d']),r:rnd(1.8,4.6),bl:1})}}
function step(dt){
  marks.forEach(function(m){m.t+=dt});marks=marks.filter(function(m){return m.t<.7});
  stains.forEach(function(s){s.t+=dt});stains=stains.filter(function(s){return s.t<s.life});
  parts.forEach(function(p){if(p.bl&&p.vy>0&&p.y>=G-2){if(stains.length<160)stains.push({x:p.x,y:G+rnd(-2,5)*U,r:p.r*U*rnd(1.6,2.6),c:p.c,t:0,life:rnd(7,10),n:2+Math.floor(Math.random()*3),sd:Math.random()*99});p.life=0}})}
function under(){   /* floor splats, under everyone */
  stains.forEach(function(e){var a=Math.min(1,(e.life-e.t)/1.5);ctx.globalAlpha=a;ctx.fillStyle=e.c;ctx.beginPath();ctx.ellipse(e.x,e.y,e.r,e.r*.26,0,0,7);ctx.fill();
    for(var i=0;i<e.n;i++){var an=hash(e.sd+i)*6.283,d=e.r*(.8+hash(e.sd+i*3)*.6);ctx.beginPath();ctx.ellipse(e.x+Math.cos(an)*d,e.y+Math.sin(an)*d*.26,e.r*.22,e.r*.07,0,0,7);ctx.fill()}});
  ctx.globalAlpha=1}
function over(){   /* claw marks, over everyone */
  marks.forEach(function(m){var p=m.t/.7,red=CFG.blood!==false;ctx.save();ctx.translate(m.x,m.y);ctx.scale(m.dir*m.u*.55,m.u*.55);ctx.globalAlpha=1-p;ctx.lineCap='round';
    for(var i=0;i<3;i++){ctx.strokeStyle=red?'rgba(120,0,10,.75)':'rgba(255,255,255,.45)';ctx.lineWidth=13;ctx.beginPath();ctx.moveTo(-34+i*16,-44);ctx.quadraticCurveTo(-8+i*16,-8,-30+i*16,38);ctx.stroke();
      ctx.strokeStyle=red?'#e0202c':'#fff';ctx.lineWidth=5;ctx.beginPath();ctx.moveTo(-34+i*16,-44);ctx.quadraticCurveTo(-8+i*16,-8,-30+i*16,38);ctx.stroke()}
    ctx.restore()});ctx.globalAlpha=1}
function clear(){marks=[];stains=[]}
return {draw:draw,hit:hit,step:step,under:under,over:over,clear:clear,FURS:FURS};
})();
/* ---- 1.20.0: Chat bags: upside-down paper bags with legs, arms and a baseball bat. The drawing comes from the Bag Brawl preview (design/bag_brawl_preview.html). No blood, ever. ---- */
var BAG=(function(){
var ARMOR_STYLE=2;   /* bubble wrap */
var PAPERS=[{p:"#c49a6c"},{p:"#a97c4f"},{p:"#dcbb8e"},{p:"#efe8dc"},{p:"#b8a78a",print:"recycle"},{p:"#c9a273",print:"thanks"},{p:"#9c7349"},
  {p:"#f4eee4",print:"stripes"},{p:"#34302d",print:"stars",dark:1},{p:"#eeb1c0",print:"heart"},{p:"#a9d8c2",print:"tape"},{p:"#c8a070",print:"grease"},{p:"#b98d5e",print:"coffee"},
  {p:"#9fc3e8",print:"dots"},{p:"#f3d36b",print:"smile"},{p:"#c49a6c",print:"doodle"}];
var INK="rgba(40,24,12,.62)";
function hash(n){var x=Math.sin(n*127.1+311.7)*43758.5453;return x-Math.floor(x)}
function shade(h,a){var n=parseInt(h.slice(1),16),f=function(v){return Math.max(0,Math.min(255,v+a))};return "rgb("+f(n>>16)+","+f(n>>8&255)+","+f(n&255)+")"}
function hex(c){if(c[0]=="#")return c;var m=/(\d+),\s*(\d+),\s*(\d+)/.exec(c);return "#"+[m[1],m[2],m[3]].map(function(v){return ("0"+(+v).toString(16)).slice(-2)}).join("")}
function oval(x,y,rx,ry){ctx.beginPath();ctx.ellipse(x,y,rx,ry,0,0,7)}
function soft(cx,cy,rx,ry,a){ctx.save();ctx.translate(cx,cy);ctx.scale(1,ry/rx);var g=ctx.createRadialGradient(0,0,0,0,0,rx);g.addColorStop(0,"rgba(0,0,0,"+a+")");g.addColorStop(1,"rgba(0,0,0,0)");ctx.fillStyle=g;ctx.beginPath();ctx.arc(0,0,rx,0,7);ctx.fill();ctx.restore()}
function eo(t){return 1-Math.pow(1-t,3)}function ei(t){return t*t*t}function eio(t){return t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2}
function eob(t){var c=1.7;return 1+(c+1)*Math.pow(t-1,3)+c*Math.pow(t-1,2)}
function star(x,y,r,c){ctx.save();ctx.translate(x,y);ctx.fillStyle=c;ctx.beginPath();for(var i=0;i<10;i++){var a=i*Math.PI/5-Math.PI/2,rr=i%2?r*.45:r;ctx.lineTo(Math.cos(a)*rr,Math.sin(a)*rr)}ctx.closePath();ctx.fill();ctx.restore()}
function crown(x,y,s){ctx.save();ctx.translate(x,y);ctx.fillStyle="#ffcf3d";ctx.strokeStyle="#a77400";ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(-18*s,8*s);ctx.lineTo(-18*s,-6*s);ctx.lineTo(-9*s,2*s);ctx.lineTo(0,-10*s);ctx.lineTo(9*s,2*s);ctx.lineTo(18*s,-6*s);ctx.lineTo(18*s,8*s);ctx.closePath();ctx.fill();ctx.stroke();ctx.fillStyle="#e0353f";ctx.beginPath();ctx.arc(0,3*s,2.6*s,0,7);ctx.fill();ctx.restore()}
function rr(x,y,w,h,r){ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath()}

/* the bag's outline: an upside-down grocery bag. Open, zig-zag mouth at the bottom (the legs come out of it), the folded base on top */
/* the bag in 3D: a front panel, a side panel (the folded gusset) going back, and the bottom of the bag on top */
function bagPath(s){ctx.beginPath();ctx.moveTo(-22*s,-132*s);ctx.lineTo(23*s,-132*s);ctx.quadraticCurveTo(31*s,-132*s,31.5*s,-123*s);   // the front panel
  ctx.quadraticCurveTo(37*s,-78*s,33*s,-26*s);
  for(var i=0;i<=10;i++){var x=33*s-i*55*s/10;ctx.lineTo(x,(i%2?-21:-26)*s)}
  ctx.quadraticCurveTo(-24.5*s,-80*s,-22*s,-132*s);ctx.closePath()}
function sidePath(s){ctx.beginPath();ctx.moveTo(-22*s,-132*s);ctx.lineTo(-38*s,-141*s);ctx.quadraticCurveTo(-44*s,-84*s,-40*s,-34*s);   // the side panel, going back (its far edge sits higher: perspective)
  for(var i=1;i<=3;i++){ctx.lineTo((-40+i*6)*s,(i%2?-28:-33)*s)}ctx.lineTo(-22*s,-26*s);ctx.quadraticCurveTo(-24.5*s,-80*s,-22*s,-132*s);ctx.closePath()}
function topPath(s){ctx.beginPath();ctx.moveTo(-22*s,-132*s);ctx.lineTo(23*s,-132*s);ctx.quadraticCurveTo(29*s,-132*s,29*s,-133*s);ctx.lineTo(15*s,-141.5*s);ctx.lineTo(-38*s,-141*s);ctx.closePath()}
function ears(s,col){[-1,1].forEach(function(d){ctx.beginPath();ctx.moveTo(d*25*s,-128*s);ctx.quadraticCurveTo(d*31*s,-142*s,d*24*s,-145*s);ctx.quadraticCurveTo(d*17*s,-137*s,d*12*s,-131*s);ctx.closePath();   // the bag's top corners, folded up like little ears
  ctx.fillStyle=col;ctx.fill();ctx.strokeStyle=INK;ctx.lineWidth=2*s;ctx.lineJoin="round";ctx.stroke();ctx.fillStyle="rgba(0,0,0,.12)";ctx.beginPath();ctx.moveTo(d*22*s,-130*s);ctx.lineTo(d*24*s,-141*s);ctx.lineTo(d*17*s,-132*s);ctx.closePath();ctx.fill()})}
/* a baseball bat, drawn from the hand: knob behind the fist, barrel out along +y */
function bat(s,blood,gold){var g=ctx.createLinearGradient(-6*s,0,6*s,0);
  if(gold){g.addColorStop(0,"#9a6a00");g.addColorStop(.5,"#ffe27a");g.addColorStop(1,"#b07a00")}else{g.addColorStop(0,"#9c6a35");g.addColorStop(.45,"#e6b06b");g.addColorStop(1,"#8a5a2b")}
  ctx.beginPath();ctx.moveTo(-2*s,-8*s);ctx.lineTo(2*s,-8*s);ctx.lineTo(2.6*s,22*s);ctx.quadraticCurveTo(7*s,40*s,6.2*s,62*s);ctx.arc(0,62*s,6.2*s,0,Math.PI);ctx.quadraticCurveTo(-7*s,40*s,-2.6*s,22*s);ctx.closePath();
  ctx.fillStyle=g;ctx.fill();ctx.strokeStyle=INK;ctx.lineWidth=1.8*s;ctx.stroke();
  ctx.fillStyle="#1d1d22";for(var i=0;i<5;i++){ctx.save();ctx.translate(0,-4*s+i*4*s);ctx.rotate(-.35);ctx.fillRect(-2.6*s,-1*s,5.2*s,2.2*s);ctx.restore()}   // grip tape
  oval(0,-9*s,4*s,2.4*s);ctx.fillStyle=gold?"#b07a00":"#6b4422";ctx.fill();ctx.stroke();   // knob
  ctx.fillStyle="rgba(255,255,255,.35)";ctx.fillRect(1.6*s,26*s,1.4*s,30*s);
  if(blood){ctx.fillStyle="rgba(150,10,20,.85)";ctx.beginPath();ctx.ellipse(1*s,58*s,5.5*s,6*s,0,0,7);ctx.fill();ctx.beginPath();ctx.ellipse(-2*s,50*s,2*s,3.5*s,0,0,7);ctx.fill()}
  if(gold){ctx.save();ctx.globalAlpha=.5+.5*Math.sin(T*20);star(0,40*s,5*s,"#fff");ctx.restore()}}
function glove(s,col){oval(0,0,7*s,6.4*s);var gg=ctx.createRadialGradient(-2*s,-2.5*s,1*s,0,0,7.5*s);gg.addColorStop(0,"#ffffff");gg.addColorStop(.6,"#f1efe8");gg.addColorStop(1,"#c9c4b8");ctx.fillStyle=gg;ctx.fill();ctx.strokeStyle=INK;ctx.lineWidth=1.6*s;ctx.stroke();ctx.fillStyle="rgba(0,0,0,.12)";oval(-2*s,2*s,4*s,3*s);ctx.fill();
  ctx.fillStyle=col;ctx.fillRect(-6*s,-8*s,12*s,3*s)}   // the cuff in the viewer's colour
function snack(k,s,bite){ctx.save();var cut=bite;   // bite 0..3: bites taken
  if(k=="burger"){oval(0,-4*s,12*s,7*s);ctx.fillStyle="#d8923f";ctx.fill();ctx.fillStyle="#5a8f2a";ctx.fillRect(-12*s,0,24*s,2.4*s);ctx.fillStyle="#6b3a1f";ctx.fillRect(-11*s,2*s,22*s,4*s);oval(0,8*s,11*s,3.5*s);ctx.fillStyle="#d8923f";ctx.fill();ctx.fillStyle="#fff3c4";[[-5,-7],[2,-8],[6,-5]].forEach(function(p){oval(p[0]*s,p[1]*s,1*s,.6*s);ctx.fill()})}
  else if(k=="donut"){oval(0,0,11*s,9*s);ctx.fillStyle="#d9a15b";ctx.fill();oval(0,-1*s,10*s,7.5*s);ctx.fillStyle="#ff7cc0";ctx.fill();oval(0,0,3.2*s,2.6*s);ctx.fillStyle="#2b2a30";ctx.fill();["#fff","#5ad","#fd4","#7d4"].forEach(function(c,i){ctx.fillStyle=c;ctx.fillRect((-6+i*4)*s,(-5+i%2*7)*s,2.4*s,1*s)})}
  else if(k=="fries"){ctx.fillStyle="#f2c14e";for(var i=0;i<5;i++)ctx.fillRect((-7+i*3.2)*s,(-14+i%2*3)*s,2.4*s,14*s);ctx.beginPath();ctx.moveTo(-9*s,-3*s);ctx.lineTo(9*s,-3*s);ctx.lineTo(7*s,10*s);ctx.lineTo(-7*s,10*s);ctx.closePath();ctx.fillStyle="#e23b2e";ctx.fill()}
  else if(k=="banana"){ctx.beginPath();ctx.moveTo(-12*s,-4*s);ctx.quadraticCurveTo(0,12*s,12*s,-6*s);ctx.quadraticCurveTo(0,4*s,-12*s,-4*s);ctx.fillStyle="#f5d33f";ctx.fill();ctx.strokeStyle="#9b7d10";ctx.lineWidth=1*s;ctx.stroke()}
  else{ctx.beginPath();ctx.moveTo(-10*s,-8*s);ctx.lineTo(10*s,-8*s);ctx.lineTo(0,12*s);ctx.closePath();ctx.fillStyle="#f6c75a";ctx.fill();ctx.fillStyle="#c7392b";[[-4,-4],[3,-3],[0,3]].forEach(function(p){oval(p[0]*s,p[1]*s,2*s,2*s);ctx.fill()});ctx.fillStyle="#b9772e";ctx.fillRect(-10*s,-10*s,20*s,3*s)}
  ctx.globalCompositeOperation="destination-out";for(var j=0;j<cut;j++){oval((9-j*4)*s,(-4+j*2)*s,5*s,5*s);ctx.fill()}   // bite marks
  ctx.restore()}

/* ---------------- one bag ---------------- */
/* the extra looks: stickers, tape, stains, doodles (all drawn on the back/side so the face stays clear) */
function star(x,y,r,c){ctx.beginPath();for(var i=0;i<10;i++){var a=-Math.PI/2+i*Math.PI/5,rr=i%2?r*.45:r;ctx.lineTo(x+Math.cos(a)*rr,y+Math.sin(a)*rr)}ctx.closePath();ctx.fillStyle=c;ctx.fill()}
function deco(k,s,b){
  if(k=="stars"){star(-12*s,-60*s,6*s,"#f2c94c");star(-2*s,-44*s,4*s,"#f2c94c");star(-19*s,-40*s,3.2*s,"#ffe9a8");star(6*s,-112*s,3.4*s,"#f2c94c")}
  if(k=="heart"){ctx.save();ctx.translate(-10*s,-52*s);ctx.rotate(-.18);ctx.fillStyle="#fff";ctx.beginPath();ctx.arc(-4*s,-2*s,6.4*s,0,7);ctx.arc(4*s,-2*s,6.4*s,0,7);ctx.fill();ctx.beginPath();ctx.moveTo(-10*s,0);ctx.lineTo(0,11*s);ctx.lineTo(10*s,0);ctx.fill();
    ctx.fillStyle="#e2405f";ctx.beginPath();ctx.arc(-3.4*s,-2*s,4.4*s,0,7);ctx.arc(3.4*s,-2*s,4.4*s,0,7);ctx.fill();ctx.beginPath();ctx.moveTo(-7.6*s,-.4*s);ctx.lineTo(0,8*s);ctx.lineTo(7.6*s,-.4*s);ctx.fill();ctx.restore()}
  if(k=="tape"){ctx.save();ctx.translate(-12*s,-58*s);ctx.fillStyle="rgba(250,245,225,.72)";[.7,-.7].forEach(function(a){ctx.save();ctx.rotate(a);ctx.fillRect(-11*s,-3*s,22*s,6*s);ctx.restore()});ctx.restore()}   // an X of tape over a tear
  if(k=="grease"){ctx.fillStyle="rgba(120,70,20,.28)";[[-14,-50,6],[-6,-74,4],[-18,-90,3.5],[8,-44,3]].forEach(function(g){ctx.beginPath();ctx.ellipse(g[0]*s,g[1]*s,g[2]*s,g[2]*.8*s,.4,0,7);ctx.fill()})}
  if(k=="coffee"){ctx.strokeStyle="rgba(90,50,20,.45)";ctx.lineWidth=2.2*s;ctx.beginPath();ctx.arc(-12*s,-56*s,9*s,.3,5.6);ctx.stroke();ctx.lineWidth=1.2*s;ctx.beginPath();ctx.arc(-11*s,-55*s,7.4*s,2.4,4.6);ctx.stroke()}
  if(k=="smile"){ctx.save();ctx.translate(-12*s,-50*s);ctx.fillStyle="#fff7d6";ctx.beginPath();ctx.arc(0,0,7.5*s,0,7);ctx.fill();ctx.strokeStyle="#c98b16";ctx.lineWidth=1.3*s;ctx.stroke();ctx.fillStyle="#7a4a0b";ctx.beginPath();ctx.arc(-2.6*s,-1.8*s,1*s,0,7);ctx.arc(2.6*s,-1.8*s,1*s,0,7);ctx.fill();ctx.beginPath();ctx.arc(0,.6*s,3.6*s,.3,Math.PI-.3);ctx.stroke();ctx.restore()}
  if(k=="doodle"){ctx.strokeStyle="rgba(40,70,160,.6)";ctx.lineWidth=1.4*s;ctx.lineCap="round";ctx.beginPath();ctx.moveTo(-20*s,-46*s);for(var i=1;i<8;i++)ctx.lineTo((-20+i*3)*s,(-46+(i%2?-3:3))*s);ctx.stroke();   // a ballpoint zigzag, a little sun, an arrow
    ctx.beginPath();ctx.arc(-10*s,-66*s,3.2*s,0,7);ctx.stroke();for(var j=0;j<8;j++){var a=j*.785;ctx.beginPath();ctx.moveTo(-10*s+Math.cos(a)*5*s,-66*s+Math.sin(a)*5*s);ctx.lineTo(-10*s+Math.cos(a)*7.4*s,-66*s+Math.sin(a)*7.4*s);ctx.stroke()}
    ctx.beginPath();ctx.moveTo(-18*s,-100*s);ctx.lineTo(-6*s,-104*s);ctx.moveTo(-9*s,-108*s);ctx.lineTo(-6*s,-104*s);ctx.lineTo(-10*s,-100.5*s);ctx.stroke()}
}
function bag(b){var BLOOD=false;
  var s=1.75*b.size,F=PAPERS[b.paper],ph=b.ph,amp=b.walkAmt,time=T,flash=b.hurt>0&&Math.floor(b.hurt*22)%2==0;
  var paper=flash?"#ffffff":F.p,K=b.state=="ko"?0:Math.min(b.kills,5),L=13*s,dance=b.state=="dance",eat=b.state=="eat";
  var bob=Math.abs(Math.sin(ph))*4*s*amp,tilt=0,legKick=0;
  if(dance){var bt=b.t*2.4*Math.PI;bob=Math.abs(Math.sin(bt))*10*s;tilt=Math.sin(bt)*.14;legKick=Math.sin(bt)}
  ctx.save();ctx.translate(b.x,b.y-(b.jmp>0?Math.sin(Math.PI*(1-b.jmp/.85))*300*b.size:0));
  if(b.shadow&&b.state!="drop"&&!(b.state=="ko"&&b.kv==2)){soft(-8*s,1*s,46*s,10*s,.55);soft(-2*s,0,24*s,5*s,.4)}
  if(b.state=="ko"){var k=Math.min(1,b.t/.35);
    if(b.kv==2){ctx.translate(0,b.ky);ctx.translate(0,-70*s);ctx.rotate(b.spin);ctx.translate(0,70*s);ctx.globalAlpha=Math.max(0,1-Math.max(0,b.t-1.1)/.5)}
    else{ctx.translate(0,-14*s*k);ctx.rotate((b.kv==1?1:-1)*b.dir*eob(k)*1.5);ctx.globalAlpha=Math.max(0,1-Math.max(0,b.t-1.2)/.5)}}
  else if(b.state=="drop"){if(b.lv==0){ctx.translate(0,-14*s);ctx.rotate(b.dir*1.4)}else if(b.lv==1){ctx.translate(0,-70*s);ctx.rotate(time*11*b.dir);ctx.translate(0,70*s)}}
  else if(b.state=="getup"){var gq=1-eo(Math.min(1,Math.max(0,(b.t-.3)/.32)));ctx.translate(0,-14*s*gq);ctx.rotate(b.dir*1.4*gq)}
  var sq=b.squish,spinF=dance&&b.move==2?Math.cos(b.t*2.4*Math.PI*.5):1;
  ctx.scale(b.face*(1+sq*.14)*(Math.abs(spinF)<.25?.25*Math.sign(spinF||1):spinF),(1-sq*.16)*(1+Math.sin(time*2.2+b.phase)*.015*(1-amp)));
  var wind=b.state=="windup",swing=b.state=="swing",follow=b.state=="follow";
  var lean=.06*amp;if(wind)lean=-.2*eo(Math.min(1,b.t/.3));if(swing)lean=.25;if(follow)lean=.18*(1-b.t/.3);if(b.hurt>0)lean=-.2;lean+=tilt;
  // legs: thin, dark, with sneakers
  function foot(p){p=((p%6.2832)+6.2832)%6.2832;if(p<Math.PI)return{x:(L-p/Math.PI*2*L)*amp,y:0};var q=(p-Math.PI)/Math.PI;return{x:(-L+eio(q)*2*L)*amp,y:-Math.sin(q*Math.PI)*9*s*amp}}
  function leg(p,back){var f=foot(p),hx=back?-11*s:11*s,hy=-24*s-bob;f.x+=(back?-6:6)*s;
    if(dance){f.x+=(back?-1:1)*Math.max(0,back?-legKick:legKick)*10*s;f.y-=Math.max(0,back?-legKick:legKick)*12*s}
    ctx.lineCap="round";ctx.strokeStyle=INK;ctx.lineWidth=8.4*s;ctx.beginPath();ctx.moveTo(hx,hy);ctx.quadraticCurveTo((hx+f.x)/2+3*s,(hy+f.y)/2-4*s,f.x,f.y-6*s);ctx.stroke();
    var lg=ctx.createLinearGradient(0,hy,0,f.y);lg.addColorStop(0,"#120c08");lg.addColorStop(.45,back?"#241912":"#3a2a1e");lg.addColorStop(1,back?"#2a1d14":"#4a3626");ctx.strokeStyle=lg;ctx.lineWidth=5.6*s;ctx.stroke();   // dark in the bag's shadow at the top
    if(!back){ctx.save();ctx.translate(1.2*s,0);ctx.strokeStyle="rgba(255,225,190,.18)";ctx.lineWidth=1.4*s;ctx.stroke();ctx.restore()}
    ctx.save();ctx.translate(f.x+4*s,f.y-4*s);oval(1*s,-1*s,12*s,7*s);var shg=ctx.createLinearGradient(0,-8*s,0,6*s);shg.addColorStop(0,flash?"#fff":(back?shade(b.shoe,-20):shade(hex(b.shoe),30)));shg.addColorStop(1,flash?"#fff":(back?shade(b.shoe,-60):shade(hex(b.shoe),-30)));ctx.fillStyle=shg;ctx.fill();ctx.strokeStyle=INK;ctx.lineWidth=1.8*s;ctx.stroke();
      ctx.fillStyle="#f6f6f2";ctx.fillRect(-11*s,2.4*s,24*s,3*s);ctx.fillStyle="rgba(255,255,255,.4)";oval(3*s,-2.4*s,4*s,1.4*s);ctx.fill();ctx.restore()}
  leg(ph+Math.PI,true);leg(ph,false);
  ctx.save();ctx.translate(0,-bob);ctx.rotate(lean);
  var sw=Math.cos(ph)*.5*amp,bt2=b.t*2.4*Math.PI;
  // back arm
  var aB=-sw+.15;if(dance)aB=b.move==0?.4+Math.sin(bt2)*.5:b.move==1?-2.6+Math.sin(bt2*2)*.4:-1.4;if(wind||swing)aB=.5;if(b.state=="gear")aB=-1+Math.sin(time*20)*.3;if(b.state=="ko")aB=-1.8;
  arm(-28.6*s,-67.6*s,aB,true);
  var restBat=["walk","getup","leave"].indexOf(b.state)>=0&&!(b.hurt>0);
  // the bag: chubbier (wider and shorter) from the mouth line up
  ctx.save();ctx.translate(0,-24*s);ctx.scale(1.1,.86);ctx.translate(0,24*s);

  // the side panel: in shade, with the gusset fold down the middle
  sidePath(s);var sg=ctx.createLinearGradient(-38*s,0,-22*s,0);sg.addColorStop(0,flash?"#fff":shade(F.p,-62));sg.addColorStop(1,flash?"#fff":shade(F.p,-36));ctx.fillStyle=sg;ctx.fill();
  if(!flash){ctx.save();sidePath(s);ctx.clip();
    ctx.fillStyle="rgba(0,0,0,.26)";ctx.beginPath();ctx.moveTo(-30*s,-136.5*s);ctx.lineTo(-38*s,-141*s);ctx.quadraticCurveTo(-44*s,-84*s,-40*s,-34*s);ctx.lineTo(-31*s,-30*s);ctx.quadraticCurveTo(-35*s,-82*s,-30*s,-136.5*s);ctx.fill();   // the far half of the fold turns away: darker
    var nf=ctx.createLinearGradient(-31*s,0,-22*s,0);nf.addColorStop(0,"rgba(255,240,215,.14)");nf.addColorStop(1,"rgba(0,0,0,.1)");ctx.fillStyle=nf;ctx.beginPath();ctx.moveTo(-30*s,-136.5*s);ctx.lineTo(-22*s,-132*s);ctx.quadraticCurveTo(-24.5*s,-80*s,-22*s,-26*s);ctx.lineTo(-31*s,-30*s);ctx.quadraticCurveTo(-35*s,-82*s,-30*s,-136.5*s);ctx.fill();   // the near half catches some light
    var sv=ctx.createLinearGradient(0,-140*s,0,-26*s);sv.addColorStop(0,"rgba(255,240,215,.08)");sv.addColorStop(.7,"rgba(0,0,0,0)");sv.addColorStop(1,"rgba(0,0,0,.25)");ctx.fillStyle=sv;ctx.fillRect(-46*s,-142*s,26*s,118*s);
    ctx.strokeStyle="rgba(0,0,0,.35)";ctx.lineWidth=1.3*s;ctx.beginPath();ctx.moveTo(-30*s,-136.5*s);ctx.quadraticCurveTo(-35*s,-82*s,-31*s,-30*s);ctx.stroke();
    ctx.strokeStyle="rgba(255,240,215,.18)";ctx.lineWidth=1*s;ctx.beginPath();ctx.moveTo(-31.2*s,-136.5*s);ctx.quadraticCurveTo(-36.2*s,-82*s,-32.2*s,-30*s);ctx.stroke();
    ctx.strokeStyle="rgba(150,200,255,.3)";ctx.lineWidth=2.6*s;ctx.beginPath();ctx.moveTo(-38*s,-139*s);ctx.quadraticCurveTo(-44*s,-84*s,-40*s,-34*s);ctx.stroke();   // cool back-light on the far edge
    ctx.restore()}
  sidePath(s);ctx.strokeStyle=INK;ctx.lineWidth=2.2*s;ctx.stroke();
  // the top: the folded bottom of the bag, seen from a little above, in the light
  topPath(s);var tg=ctx.createLinearGradient(0,-142*s,0,-132*s);tg.addColorStop(0,flash?"#fff":shade(F.p,8));tg.addColorStop(1,flash?"#fff":shade(F.p,30));ctx.fillStyle=tg;ctx.fill();
  if(!flash){ctx.save();topPath(s);ctx.clip();
    ctx.fillStyle="rgba(0,0,0,.12)";ctx.beginPath();ctx.moveTo(-22*s,-132*s);ctx.lineTo(-30*s,-136.6*s);ctx.lineTo(-38*s,-141*s);ctx.lineTo(-22*s,-141*s);ctx.closePath();ctx.fill();   // the folded triangles of the bottom
    ctx.fillStyle="rgba(255,250,235,.16)";ctx.fillRect(-28*s,-138.4*s,48*s,3.4*s);   // the glued flap, raised a little
    ctx.strokeStyle="rgba(60,35,15,.4)";ctx.lineWidth=1*s;ctx.beginPath();ctx.moveTo(-30*s,-136.6*s);ctx.lineTo(21*s,-136.8*s);ctx.moveTo(-28*s,-138.4*s);ctx.lineTo(20*s,-138.4*s);ctx.moveTo(-22*s,-132*s);ctx.lineTo(-30*s,-136.6*s);ctx.lineTo(-24*s,-141*s);ctx.moveTo(23*s,-132*s);ctx.lineTo(19*s,-136.8*s);ctx.lineTo(15*s,-141*s);ctx.stroke();ctx.restore()}   // its folds
  topPath(s);ctx.strokeStyle=INK;ctx.lineWidth=2*s;ctx.stroke();
  // the front panel
  bagPath(s);var g=ctx.createLinearGradient(-22*s,0,34*s,0);g.addColorStop(0,flash?"#fff":shade(F.p,-14));g.addColorStop(.5,paper);g.addColorStop(.85,flash?"#fff":shade(F.p,14));g.addColorStop(1,flash?"#fff":shade(F.p,4));ctx.fillStyle=g;ctx.fill();
  ctx.save();bagPath(s);ctx.clip();
  if(!flash&&F.print=="stripes"){ctx.fillStyle="rgba(214,40,48,.88)";for(var q=-2;q<4;q++)ctx.fillRect((q*11-1)*s,-134*s,5.5*s,118*s)}   // popcorn stripes
  if(!flash&&F.print=="dots"){ctx.fillStyle="rgba(255,255,255,.75)";for(var q=0;q<22;q++){var dx=((q*7)%6-2.5)*10+(Math.floor(q/6)%2)*5,dy=-112+Math.floor(q/6)*20;ctx.beginPath();ctx.arc(dx*s,dy*s,2.6*s,0,7);ctx.fill()}}   // polka dots
  if(!flash){var v=ctx.createLinearGradient(0,-132*s,0,-20*s);v.addColorStop(0,"rgba(255,255,255,.18)");v.addColorStop(.4,"rgba(255,255,255,0)");v.addColorStop(1,"rgba(0,0,0,.28)");ctx.fillStyle=v;ctx.fillRect(-34*s,-133*s,68*s,115*s);
    var ws=ctx.createRadialGradient(18*s,-108*s,2*s,18*s,-108*s,46*s);ws.addColorStop(0,"rgba(255,246,222,.22)");ws.addColorStop(1,"rgba(255,246,222,0)");ctx.fillStyle=ws;ctx.fillRect(-23*s,-133*s,60*s,112*s);   // warm light from the front-right
    var sh2=ctx.createLinearGradient(-6*s,0,22*s,0);sh2.addColorStop(0,"rgba(255,255,255,0)");sh2.addColorStop(.55,"rgba(255,252,240,.13)");sh2.addColorStop(1,"rgba(255,255,255,0)");ctx.fillStyle=sh2;ctx.fillRect(-6*s,-130*s,28*s,104*s);   // the paper bulges: a soft sheen
    var rs=ctx.createLinearGradient(25*s,0,35*s,0);rs.addColorStop(0,"rgba(0,0,0,0)");rs.addColorStop(1,"rgba(0,0,0,.2)");ctx.fillStyle=rs;ctx.fillRect(25*s,-133*s,12*s,112*s);   // the front turns away on the right
    var ao=ctx.createLinearGradient(0,-132*s,0,-120*s);ao.addColorStop(0,"rgba(0,0,0,.22)");ao.addColorStop(1,"rgba(0,0,0,0)");ctx.fillStyle=ao;ctx.fillRect(-23*s,-133*s,58*s,13*s);   // shade under the top edge
    ctx.strokeStyle="rgba(255,248,230,.45)";ctx.lineWidth=1.8*s;ctx.beginPath();ctx.moveTo(-20.8*s,-130*s);ctx.quadraticCurveTo(-23.2*s,-80*s,-20.8*s,-28*s);ctx.stroke();   // a crisp light on the front edge, where it folds into the side
    ctx.strokeStyle="rgba(255,248,230,.35)";ctx.lineWidth=1.4*s;ctx.beginPath();ctx.moveTo(-20*s,-130.6*s);ctx.lineTo(23*s,-130.6*s);ctx.stroke();
    [[4,-118,-2,-104],[22,-60,28,-44],[-12,-40,-4,-30]].forEach(function(w2){ctx.strokeStyle="rgba(0,0,0,.13)";ctx.lineWidth=1.6*s;ctx.beginPath();ctx.moveTo(w2[0]*s,w2[1]*s);ctx.quadraticCurveTo((w2[0]+w2[2])/2*s+2*s,(w2[1]+w2[3])/2*s,w2[2]*s,w2[3]*s);ctx.stroke();
      ctx.strokeStyle="rgba(255,250,235,.22)";ctx.lineWidth=1.1*s;ctx.beginPath();ctx.moveTo((w2[0]+1.4)*s,w2[1]*s);ctx.quadraticCurveTo((w2[0]+w2[2])/2*s+3.4*s,(w2[1]+w2[3])/2*s,(w2[2]+1.4)*s,w2[3]*s);ctx.stroke()});   // crinkles: a shadow and a light
    for(var i=0;i<26;i++){ctx.fillStyle=hash(b.seed+i)>.5?"rgba(90,55,25,.18)":"rgba(255,245,220,.2)";ctx.fillRect((-28+hash(b.seed+i*3)*56)*s,(-118+hash(b.seed+i*7)*92)*s,(1+hash(i)*3)*s,.8*s)}   // paper fibres
    ctx.fillStyle="rgba(0,0,0,.35)";for(var z=0;z<5;z++){ctx.beginPath();ctx.moveTo((-22+z*11)*s,-26*s);ctx.lineTo((-16.5+z*11)*s,-20*s);ctx.lineTo((-11+z*11)*s,-26*s);ctx.closePath();ctx.fill()}   // inside of the mouth, in shadow
    var bo=ctx.createLinearGradient(0,-44*s,0,-22*s);bo.addColorStop(0,"rgba(0,0,0,0)");bo.addColorStop(1,"rgba(0,0,0,.2)");ctx.fillStyle=bo;ctx.fillRect(-23*s,-44*s,60*s,24*s);   // darker near the bottom
    if(F.print=="thanks"){ctx.save();ctx.translate(-4*s,-46*s);ctx.scale(b.face<0?-1:1,1);ctx.rotate(-.06);ctx.fillStyle="rgba(200,40,40,.75)";ctx.font="900 "+(9*s)+"px Outfit, sans-serif";ctx.textAlign="center";ctx.fillText("THANK YOU",0,0);ctx.lineWidth=1.4*s;ctx.strokeStyle="rgba(200,40,40,.75)";ctx.beginPath();ctx.arc(0,9*s,5*s,.2,Math.PI-.2);ctx.stroke();ctx.restore()}
    if(F.print=="recycle"){ctx.save();ctx.translate(-6*s,-44*s);ctx.strokeStyle="rgba(40,110,60,.7)";ctx.lineWidth=2*s;for(var r3=0;r3<3;r3++){ctx.rotate(2.094);ctx.beginPath();ctx.arc(0,-6*s,5*s,-.4,1.2);ctx.stroke()}ctx.restore()}
    deco(F.print,s,b);

    if(K>0&&BLOOD)for(var j=0;j<2+K*2;j++){var gx=(-20+hash(b.seed+j*5.3)*44)*s,gy=(-110+hash(b.seed+j*8.1)*80)*s,gr=(2+hash(b.seed+j)*3.5)*s;ctx.fillStyle="rgba(150,12,20,.85)";oval(gx,gy,gr,gr*.8);ctx.fill();
      if(j%2==0){ctx.fillRect(gx-.6*s,gy,1.4*s,(5+hash(j)*10)*s)}}
  }
  ctx.restore();
  if(!flash){ctx.strokeStyle="rgba(255,240,210,.35)";ctx.lineWidth=1*s;ctx.beginPath();for(var zi=0;zi<=10;zi++){var zx=33*s-zi*55*s/10;ctx.lineTo(zx,((zi%2?-21:-26)-1.6)*s)}ctx.stroke()}   // the torn paper edge has thickness
  bagPath(s);ctx.strokeStyle=INK;ctx.lineWidth=2.4*s;ctx.stroke();
  // the face: two eye holes cut out, eyebrows and mouth drawn on with a marker in the viewer's colour
  var mk=F.dark?"#f2e3c4":"#3b2414",mad=wind||swing||K>0,hx=14*s;   // eyebrows and mouth drawn on in dark brown marker
  var E=[[hx-9*s,-95*s],[hx+10*s,-96*s]],blink=b.blink>0,fv=b.fv||0;   // fv: 0 cute, 1 mustache, 2 sunglasses, 3 freckles, 4 lashes, 5 bushy brows, 6 band-aid, 7 toothy grin
  if(b.state=="ko"){ctx.strokeStyle=mk;ctx.lineWidth=3.2*s;ctx.lineCap="round";E.forEach(function(e){ctx.beginPath();ctx.moveTo(e[0]-5*s,e[1]-5*s);ctx.lineTo(e[0]+5*s,e[1]+5*s);ctx.moveTo(e[0]+5*s,e[1]-5*s);ctx.lineTo(e[0]-5*s,e[1]+5*s);ctx.stroke()})}
  else E.forEach(function(e,i){
    if(blink){ctx.strokeStyle="#1a1009";ctx.lineWidth=2.4*s;ctx.beginPath();ctx.moveTo(e[0]-5*s,e[1]);ctx.lineTo(e[0]+5*s,e[1]);ctx.stroke();return}
    if(fv==2&&b.state!="ko")return;   // (sunglasses cover the eyes)
    var eh=(b.hurt>0?5:11)*s,eg=ctx.createRadialGradient(e[0]+1*s,e[1]+2*s,1*s,e[0],e[1],eh);eg.addColorStop(0,"#2a1a0e");eg.addColorStop(1,"#0b0603");
    ctx.beginPath();ctx.ellipse(e[0],e[1],7.8*s,eh,i?.06:-.06,0,7);ctx.fillStyle=eg;ctx.fill();ctx.strokeStyle="rgba(80,45,20,.6)";ctx.lineWidth=1.2*s;ctx.stroke();   // big round eye holes (cute)
    ctx.strokeStyle=shade(F.p,40);ctx.lineWidth=1.3*s;ctx.beginPath();ctx.ellipse(e[0],e[1]+.6*s,7.6*s,eh,i?.06:-.06,.35,2.8);ctx.stroke();   // the cut paper edge catches the light
    if(fv==4){ctx.strokeStyle="#1a1009";ctx.lineWidth=1.6*s;ctx.lineCap="round";for(var la=0;la<3;la++){var aa=-2.0+la*.42;ctx.beginPath();ctx.moveTo(e[0]+Math.cos(aa)*7.6*s,e[1]+Math.sin(aa)*eh);ctx.lineTo(e[0]+Math.cos(aa)*11.6*s,e[1]+Math.sin(aa)*(eh+4*s));ctx.stroke()}}   // eyelashes
    ctx.fillStyle="rgba(255,255,255,.95)";oval(e[0]+2.4*s,e[1]-3.6*s,2.8*s,3.4*s);ctx.fill();ctx.fillStyle="rgba(255,255,255,.7)";oval(e[0]-2.6*s,e[1]+4*s,1.3*s,1.5*s);ctx.fill()});
  if(b.state!="ko"){[[hx-17*s,-80*s,6.4*s],[hx+19*s,-81*s,5.8*s]].forEach(function(c){var bg3=ctx.createRadialGradient(c[0],c[1],0,c[0],c[1],c[2]);bg3.addColorStop(0,"rgba(255,110,135,"+(K>0?.28:.6)+")");bg3.addColorStop(1,"rgba(255,110,135,0)");ctx.fillStyle=bg3;oval(c[0],c[1],c[2],c[2]*.72);ctx.fill()});   // soft blush
    if(fv==3){ctx.fillStyle="rgba(110,50,20,.75)";[[-20,-84],[-16,-82],[-19,-79],[16,-85],[20,-83],[17,-80]].forEach(function(d){ctx.beginPath();ctx.arc(hx+d[0]*s,d[1]*s,1.3*s,0,7);ctx.fill()})}}   // freckles
  ctx.strokeStyle=mk;ctx.lineCap="round";ctx.lineWidth=(fv==5?5.6:3)*s;
  if(b.state!="ko"){E.forEach(function(e,i){ctx.beginPath();if(mad){ctx.moveTo(e[0]-7*s,e[1]+(i?-11:-15)*s);ctx.lineTo(e[0]+7*s,e[1]+(i?-15:-11)*s)}else{ctx.moveTo(e[0]-5*s,e[1]-13*s);ctx.quadraticCurveTo(e[0],e[1]-16*s,e[0]+5*s,e[1]-13*s)}ctx.stroke()})}
  ctx.lineWidth=3*s;
  var mouthOpen=eat&&b.t>.35&&b.t<.72?Math.min(1,(b.t-.35)/.25)*1.6:0,chew=eat&&b.t>=.72&&b.t<1.5;
  if(mouthOpen>.1){ctx.fillStyle="#140c06";oval(hx+1*s,-75*s,(6+mouthOpen*3)*s,(2+mouthOpen*5)*s);ctx.fill();ctx.stroke()}
  else if(chew){var cw=Math.sin(b.t*30)*1.5*s;ctx.beginPath();ctx.moveTo(hx-8*s,-75*s+cw);ctx.quadraticCurveTo(hx+1*s,-70*s-cw,hx+10*s,-75*s+cw);ctx.stroke();ctx.fillStyle="rgba(255,140,160,.35)";oval(hx-12*s,-80*s,5*s,4*s);ctx.fill();oval(hx+14*s,-81*s,5*s,4*s);ctx.fill()}   // chewing, cheeks full
  else if(b.state=="ko"||b.hurt>0){ctx.beginPath();ctx.moveTo(hx-8*s,-73*s);for(var w=0;w<5;w++)ctx.lineTo(hx+(-8+w*4+2)*s,(w%2?-77:-73)*s);ctx.stroke()}
  else if(K>0||wind||swing){ctx.beginPath();ctx.moveTo(hx-9*s,-72*s);ctx.quadraticCurveTo(hx+1*s,-79*s,hx+11*s,-72*s);ctx.stroke();ctx.fillStyle="#fff";ctx.beginPath();ctx.moveTo(hx-3*s,-75.5*s);ctx.lineTo(hx+0*s,-71.5*s);ctx.lineTo(hx+3*s,-76.5*s);ctx.fill()}
  else if(dance){ctx.beginPath();ctx.arc(hx+1*s,-78*s,8*s,.25,Math.PI-.25);ctx.stroke()}
  else if(fv==7){ctx.beginPath();ctx.moveTo(hx-8*s,-80*s);ctx.quadraticCurveTo(hx+1*s,-80*s,hx+10*s,-80.5*s);ctx.quadraticCurveTo(hx+1*s,-66*s,hx-8*s,-80*s);ctx.closePath();ctx.fillStyle="#3a120c";ctx.fill();ctx.stroke();
    ctx.fillStyle="#fffdf6";ctx.fillRect(hx-3*s,-79.6*s,3.6*s,4.2*s);ctx.fillRect(hx+1.2*s,-79.6*s,3.6*s,4.2*s);ctx.fillStyle="#e2556b";oval(hx+1*s,-71.8*s,4*s,2*s);ctx.fill()}   // a big toothy grin
  else{ctx.beginPath();ctx.moveTo(hx-5*s,-79*s);ctx.quadraticCurveTo(hx-2.5*s,-75*s,hx+.5*s,-78.5*s);ctx.quadraticCurveTo(hx+3.5*s,-75*s,hx+6*s,-79*s);ctx.stroke()}   // a small cute mouth
  if(fv==1){ctx.save();ctx.translate(hx+1*s,-82.5*s);ctx.scale(1.35,1.35);ctx.fillStyle=F.dark?"#e9d6b0":"#2b1a0e";ctx.beginPath();   // a curly handlebar mustache
    [-1,1].forEach(function(d){ctx.moveTo(0,-1.5*s);ctx.bezierCurveTo(d*5*s,-4.5*s,d*10*s,-3.5*s,d*12*s,0);ctx.bezierCurveTo(d*14*s,2.5*s,d*17*s,0,d*16.5*s,-3.5*s);ctx.bezierCurveTo(d*18.5*s,1.5*s,d*14*s,5.5*s,d*10.5*s,3.2*s);ctx.bezierCurveTo(d*7*s,1.2*s,d*3*s,3*s,0,2*s);ctx.closePath()});ctx.fill();
    ctx.fillStyle="rgba(255,255,255,.18)";oval(-5*s,-1.8*s,3.5*s,1*s);ctx.fill();oval(5*s,-1.8*s,3.5*s,1*s);ctx.fill();ctx.restore()}
  if(fv==2&&b.state!="ko"){ctx.save();ctx.fillStyle="#0e0e12";ctx.strokeStyle="#0e0e12";ctx.lineWidth=2*s;   // cool sunglasses
    E.forEach(function(e){ctx.beginPath();ctx.moveTo(e[0]-9*s,e[1]-6*s);ctx.lineTo(e[0]+9*s,e[1]-6*s);ctx.quadraticCurveTo(e[0]+9.5*s,e[1]+7*s,e[0],e[1]+7*s);ctx.quadraticCurveTo(e[0]-9.5*s,e[1]+7*s,e[0]-9*s,e[1]-6*s);ctx.fill();
      var lg2=ctx.createLinearGradient(e[0]-8*s,e[1]-6*s,e[0]+6*s,e[1]+6*s);lg2.addColorStop(0,"rgba(255,255,255,.35)");lg2.addColorStop(.35,"rgba(255,255,255,0)");lg2.addColorStop(.8,"rgba(120,160,255,.18)");ctx.fillStyle=lg2;ctx.fill();ctx.fillStyle="#0e0e12"});
    ctx.beginPath();ctx.moveTo(E[0][0]+8*s,E[0][1]-4*s);ctx.quadraticCurveTo((E[0][0]+E[1][0])/2,E[0][1]-6*s,E[1][0]-8*s,E[1][1]-4*s);ctx.stroke();
    ctx.beginPath();ctx.moveTo(E[0][0]-9*s,E[0][1]-5*s);ctx.lineTo(-22*s,E[0][1]-3*s);ctx.stroke();ctx.restore()}
  if(fv==6&&b.state!="ko"){ctx.save();ctx.translate(hx+19*s,-90*s);ctx.rotate(-.6);ctx.fillStyle="#f2c9a0";ctx.strokeStyle="rgba(120,70,30,.6)";ctx.lineWidth=1*s;ctx.beginPath();ctx.rect(-8*s,-2.6*s,16*s,5.2*s);ctx.fill();ctx.stroke();ctx.fillStyle="#e3b083";ctx.fillRect(-3*s,-2.6*s,6*s,5.2*s);
    ctx.fillStyle="rgba(120,70,30,.5)";[[-1.5,-1],[1.5,-1],[-1.5,1],[1.5,1]].forEach(function(d){ctx.beginPath();ctx.arc(d[0]*s,d[1]*s,.4*s,0,7);ctx.fill()});ctx.restore()}   // a band-aid
  // !protect: the armor (ARMOR_STYLE picks which one)
  var gp=b.state=="gear"?b.t:(b.armor?9:-1),AS=b.as||ARMOR_STYLE;
  if(gp>=0){ctx.save();if(b.armor&&b.armorEnd-T<2.2)ctx.globalAlpha*=.45+.55*Math.abs(Math.cos((b.armorEnd-T)*9));
    if(AS==1)armorPizza(gp);else if(AS==2)armorBubble(gp);else if(AS==3)armorCan(gp);else armorBox(gp);
    ctx.restore()}
  function armorBox(gp){
    var up=eo(Math.min(1,gp/.45)),fl=eo(Math.max(0,Math.min(1,(gp-.4)/.35))),tp=Math.max(0,Math.min(1,(gp-.8)/.3));
    var bx0=-36*s,bw=72*s,top=-66*s,bot=-22*s,h=(bot-top)*up;
    ctx.fillStyle="#b98b55";ctx.fillRect(bx0,bot-h,bw,h);ctx.strokeStyle="#5a3b1c";ctx.lineWidth=2*s;ctx.strokeRect(bx0,bot-h,bw,h);
    if(tp>0){ctx.fillStyle="rgba(222,190,120,.92)";ctx.fillRect(bx0,-48*s,bw*tp,8*s)}}
  /* 1) PIZZA BOX: a pizza box slides up and hugs the bag like a sandwich board, string ties it, a grease spot and "HOT" stamp */
  function armorPizza(gp){
    var up=eob(Math.min(1,gp/.5)),tie=Math.max(0,Math.min(1,(gp-.55)/.3)),st=Math.max(0,Math.min(1,(gp-.95)/.15));
    var y0=-72*s+(1-up)*70*s,y1=-22*s+(1-up)*70*s;
    ctx.save();ctx.beginPath();ctx.rect(-60*s,-160*s,120*s,140*s);ctx.clip();
    // the side of the box (3D)
    ctx.fillStyle="#9c6f3c";ctx.beginPath();ctx.moveTo(-26*s,y0);ctx.lineTo(-40*s,y0-7*s);ctx.lineTo(-40*s,y1-7*s);ctx.lineTo(-26*s,y1);ctx.closePath();ctx.fill();ctx.strokeStyle="#4a2f14";ctx.lineWidth=1.8*s;ctx.stroke();
    ctx.fillStyle="#c79a5f";ctx.beginPath();ctx.moveTo(-26*s,y0);ctx.lineTo(-40*s,y0-7*s);ctx.lineTo(24*s,y0-7*s);ctx.lineTo(38*s,y0);ctx.closePath();ctx.fill();ctx.stroke();   // its top edge
    // the front: the lid
    var g2=ctx.createLinearGradient(-26*s,0,38*s,0);g2.addColorStop(0,"#c2915a");g2.addColorStop(.6,"#e2b97f");g2.addColorStop(1,"#c99a5e");ctx.fillStyle=g2;ctx.fillRect(-26*s,y0,64*s,y1-y0);ctx.strokeRect(-26*s,y0,64*s,y1-y0);
    ctx.strokeStyle="rgba(90,55,25,.4)";ctx.lineWidth=1*s;ctx.strokeRect(-22*s,y0+4*s,56*s,y1-y0-8*s);   // the lid's pressed edge
    ctx.fillStyle="#c8322a";ctx.fillRect(-26*s,y0+6*s,64*s,6*s);ctx.fillStyle="#fff";ctx.font="900 "+(5.2*s)+"px Outfit, sans-serif";ctx.textAlign="center";ctx.save();ctx.translate(6*s,y0+10.8*s);ctx.scale(b.face<0?-1:1,1);ctx.fillText("HOT  PIZZA",0,0);ctx.restore();
    ctx.fillStyle="rgba(150,90,30,.28)";oval(20*s,y1-14*s,7*s,5*s);ctx.fill();oval(26*s,y1-10*s,3*s,2.4*s);ctx.fill();   // a grease spot
    ctx.fillStyle="rgba(255,250,235,.25)";ctx.fillRect(-24*s,y0+1.4*s,60*s,1.6*s);
    ctx.restore();
    if(tie>0){ctx.strokeStyle="#efe4cf";ctx.lineWidth=1.6*s;ctx.setLineDash([3*s,1.6*s]);ctx.beginPath();ctx.moveTo(-17*s,-72*s);ctx.lineTo(-17*s,-72*s-61*s*tie);ctx.moveTo(-17*s,-133*s);ctx.lineTo(-17*s-14*s*tie,-140*s);ctx.stroke();ctx.setLineDash([]);   // string up over the bag
      if(tie>=1){ctx.strokeStyle="#efe4cf";ctx.lineWidth=1.6*s;ctx.beginPath();ctx.moveTo(-17*s,-134*s);ctx.ellipse(-21*s,-135*s,4*s,2.4*s,-.4,0,7);ctx.moveTo(-9*s,-135*s);ctx.ellipse(-13*s,-135*s,4*s,2.4*s,.4,0,7);ctx.stroke()}}   // a little bow on top
    if(st>0){var sc=1.8-.8*st;ctx.save();ctx.translate(16*s,-38*s);ctx.scale(b.face<0?-sc:sc,sc);ctx.rotate(-.15);ctx.strokeStyle="rgba(200,40,30,.9)";ctx.lineWidth=1.2*s;ctx.beginPath();ctx.arc(0,0,7*s,0,7);ctx.stroke();ctx.fillStyle="rgba(200,40,30,.9)";ctx.font="900 "+(4.6*s)+"px Outfit, sans-serif";ctx.textAlign="center";ctx.fillText("HOT!",0,1.6*s);ctx.restore()}}
  /* 2) BUBBLE WRAP: a sheet wraps around from the side, bubbles shine, packing tape zips across, a FRAGILE sticker slaps on */
  function armorBubble(gp){
    var wr=eo(Math.min(1,gp/.55)),tp=Math.max(0,Math.min(1,(gp-.6)/.3)),st=Math.max(0,Math.min(1,(gp-.95)/.15));
    var x0=-44*s,x1=x0+(84*s)*wr,top=-74*s,bot=-24*s;
    ctx.save();ctx.beginPath();ctx.moveTo(x0,top+4*s);ctx.quadraticCurveTo((x0+x1)/2,top-4*s,x1,top);ctx.lineTo(x1,bot);ctx.quadraticCurveTo((x0+x1)/2,bot+5*s,x0,bot-2*s);ctx.closePath();
    var bw2=ctx.createLinearGradient(x0,0,40*s,0);bw2.addColorStop(0,"rgba(190,215,235,.55)");bw2.addColorStop(.6,"rgba(240,248,255,.55)");bw2.addColorStop(1,"rgba(200,220,240,.5)");ctx.fillStyle=bw2;ctx.fill();ctx.strokeStyle="rgba(120,150,180,.8)";ctx.lineWidth=1.6*s;ctx.stroke();
    ctx.clip();
    for(var r=0;r<6;r++)for(var c=0;c<11;c++){var bx2=x0+(4+c*7.6+(r%2)*3.8)*s,by2=top+(5+r*8.2)*s;if(bx2>x1)continue;var lit=bx2>-10*s;   // the bubbles
      ctx.fillStyle=lit?"rgba(255,255,255,.35)":"rgba(220,235,250,.25)";ctx.beginPath();ctx.arc(bx2,by2,3.2*s,0,7);ctx.fill();ctx.strokeStyle="rgba(110,140,170,.45)";ctx.lineWidth=.8*s;ctx.stroke();
      ctx.fillStyle="rgba(255,255,255,.85)";ctx.beginPath();ctx.arc(bx2+1*s,by2-1.2*s,.9*s,0,7);ctx.fill()}
    ctx.restore();
    if(tp>0){ctx.fillStyle="rgba(214,170,100,.88)";ctx.save();ctx.translate(-44*s,-50*s);ctx.rotate(-.06);ctx.fillRect(0,0,86*s*tp,8*s);ctx.fillStyle="rgba(255,255,255,.35)";ctx.fillRect(0,0,86*s*tp,1.6*s);ctx.restore()}   // packing tape
    if(st>0){var sc=1.8-.8*st;ctx.save();ctx.translate(14*s,-34*s);ctx.scale(b.face<0?-sc:sc,sc);ctx.rotate(-.1);ctx.fillStyle="#d83a2e";ctx.fillRect(-14*s,-5*s,28*s,10*s);ctx.fillStyle="#fff";ctx.font="900 "+(5.6*s)+"px Outfit, sans-serif";ctx.textAlign="center";ctx.fillText("FRAGILE",0,2*s);ctx.restore()}}
  /* 3) SODA CAN: a big shiny can (in the viewer's colour) drops down over the bag like a sleeve, clank, the ring-pull clicks */
  function armorCan(gp){
    var dn=Math.min(1,gp/.45),k=dn<1?ei(dn):1,bounce=gp>.45&&gp<.7?Math.sin((gp-.45)/.25*Math.PI)*4*s:0;
    var top=-78*s-(1-k)*120*s-bounce,bot=-24*s-(1-k)*120*s-bounce,x0=-40*s,x1=37*s,c=b.color;
    ctx.save();ctx.globalAlpha*=Math.min(1,gp/.12);
    var mg=ctx.createLinearGradient(x0,0,x1,0);mg.addColorStop(0,"#5d6168");mg.addColorStop(.18,"#9aa0a8");mg.addColorStop(.55,"#eef1f4");mg.addColorStop(.75,"#c3c8ce");mg.addColorStop(1,"#7b8088");
    ctx.beginPath();ctx.moveTo(x0,top);ctx.lineTo(x1,top);ctx.lineTo(x1,bot);ctx.ellipse((x0+x1)/2,bot,(x1-x0)/2,5*s,0,0,Math.PI);ctx.closePath();ctx.fillStyle=mg;ctx.fill();
    var cg=ctx.createLinearGradient(x0,0,x1,0);cg.addColorStop(0,shade(hex(c),-70));cg.addColorStop(.55,shade(hex(c),20));cg.addColorStop(1,shade(hex(c),-50));ctx.fillStyle=cg;ctx.fillRect(x0,top+9*s,x1-x0,bot-top-16*s);   // the label, in the viewer's colour
    ctx.fillStyle="rgba(255,255,255,.9)";ctx.font="900 italic "+(8*s)+"px Outfit, sans-serif";ctx.textAlign="center";ctx.save();ctx.translate(4*s,(top+bot)/2+3*s);ctx.scale(b.face<0?-1:1,1);ctx.fillText("FIZZ",0,0);ctx.restore();
    ctx.fillStyle="rgba(255,255,255,.35)";ctx.fillRect(4*s,top,5*s,bot-top);   // the shine
    ctx.strokeStyle="#41454b";ctx.lineWidth=1.8*s;ctx.beginPath();ctx.moveTo(x0,top);ctx.lineTo(x0,bot);ctx.moveTo(x1,top);ctx.lineTo(x1,bot);ctx.stroke();
    [top,top+3*s,bot-3*s].forEach(function(y){ctx.strokeStyle="rgba(60,64,70,.55)";ctx.lineWidth=1*s;ctx.beginPath();ctx.moveTo(x0,y+2*s);ctx.lineTo(x1,y+2*s);ctx.stroke()});   // ridges
    ctx.beginPath();ctx.ellipse((x0+x1)/2,top,(x1-x0)/2,5*s,0,0,7);ctx.fillStyle="#d9dde2";ctx.fill();ctx.strokeStyle="#41454b";ctx.lineWidth=1.8*s;ctx.stroke();   // the rim (the bag pokes out of it)
    ctx.beginPath();ctx.ellipse((x0+x1)/2,bot,(x1-x0)/2,5*s,0,0,Math.PI);ctx.stroke();
    if(gp>.8){var pull=Math.min(1,(gp-.8)/.15);ctx.save();ctx.translate(26*s,top+12*s);ctx.rotate(-.5*pull);ctx.fillStyle="#cfd3d8";ctx.strokeStyle="#41454b";ctx.lineWidth=1.2*s;ctx.beginPath();ctx.ellipse(0,0,4.6*s,3*s,0,0,7);ctx.fill();ctx.stroke();ctx.fillStyle="#41454b";ctx.beginPath();ctx.ellipse(-.6*s,0,1.8*s,1*s,0,0,7);ctx.fill();ctx.restore()}   // the ring-pull
    ctx.restore()}
  ctx.restore();
  // buff aura
  if(b.buff&&b.state!="ko"){var bk=b.buff.k;ctx.save();ctx.globalAlpha=.55+.25*Math.sin(time*8);
    if(bk=="rage"){for(var f2=0;f2<5;f2++){var fx2=(-26+f2*13)*s,fy=-132*s-((time*60+f2*17)%30)*s;ctx.fillStyle=f2%2?"#ff5a1f":"#ffb32b";ctx.beginPath();ctx.moveTo(fx2-4*s,fy+10*s);ctx.quadraticCurveTo(fx2,fy-8*s,fx2+4*s,fy+10*s);ctx.fill()}}
    if(bk=="speed"&&amp>.3){ctx.strokeStyle="rgba(255,255,255,.6)";ctx.lineWidth=2.4*s;for(var l=0;l<4;l++){ctx.beginPath();ctx.moveTo(-44*s-l*4*s,(-110+l*24)*s);ctx.lineTo(-70*s-l*6*s,(-110+l*24)*s);ctx.stroke()}}
    if(bk=="ultra"){ctx.strokeStyle="#ffd84d";ctx.lineWidth=5*s;ctx.globalAlpha=.6+.4*Math.sin(time*25);bagPath(s);ctx.stroke()}
    ctx.restore()}
  // front arm, with the bat (or a snack), drawn last
  var a,bt=-.5,hold="bat",ul=b.state=="ultra",armL=30,armY=-74,armX=24;
  if(ul){var uq=b.t<.4?eo(b.t/.4):b.t<.55?1-ei((b.t-.4)/.15)*1.8:-.8+.8*eio(Math.min(1,(b.t-.55)/.6));a=-.25+(1.9+.25)*Math.max(-.6,uq);bt=-.5+3.5*Math.max(-.35,uq)}   // the ULTRA KILL swing
  else if(wind){var q=eo(Math.min(1,b.t/.3));a=-.35+(1.9+.35)*q;bt=2.5+.5*q}
  else if(swing){var q2=ei(Math.min(1,b.t/.1));a=1.9-3.5*q2;bt=3.0-4.7*q2;
    ctx.save();ctx.globalAlpha=.5*(1-Math.max(0,b.t-.06)/.1);ctx.strokeStyle="#fff";ctx.lineWidth=12*s;ctx.lineCap="round";ctx.beginPath();ctx.arc(20*s,-72*s,74*s,-Math.PI/2+Math.PI-.2,-Math.PI/2+Math.PI*0+.9,true);ctx.stroke();ctx.restore()}
  else if(follow){var q3=Math.min(1,b.t/.3);a=-1.6+1.25*eio(q3);bt=-1.7+4.2*eio(q3)}
  else if(eat){var e1=Math.min(1,b.t/.4),e3=Math.max(0,Math.min(1,(b.t-.8)/.4));a=-.3-1.5*eo(e1)*(1-e3);hold="snack"}
  else if(dance){a=b.move==0?-2.6+Math.sin(bt2)*.3:b.move==1?-2.4+Math.sin(bt2*2+1)*.4:-1.4;hold="none"}
  else if(b.state=="gear"){a=-1+Math.sin(time*22)*.35}
  else if(b.state=="ko")a=-1.6;else if(b.hurt>0)a=-.9;
  else if(restBat){a=-2.415+sw*.04;bt=1.70+sw*.04;armL=24.1;armY=-44;armX=30}   // walking: the bat rests across the front, knob forward, barrel back over the mouth (like FQPN's sketch)
  if(hold!="bat"&&b.state!="ko"){ctx.save();ctx.translate(-40*s,-72*s);ctx.rotate(.22);bat(s*.9,K>0&&BLOOD,false);ctx.restore()}   // bat leaning on the ground while dancing or eating
  armX*=1.1;armY=-24+(armY+24)*.86;   // shoulder sits on the chubbier body
  arm(armX*s,armY*s,a,false,hold=="bat"&&b.state!="ko"&&bt!=null?bt:null,hold=="snack",armL);
  ctx.restore();
  if(b.state=="ko"&&b.kv!=2&&b.t<1.6){for(var j2=0;j2<3;j2++){var an=time*5+j2*2.1;star(Math.cos(an)*30*s,-150*s+Math.sin(an)*9*s,7*s,"#ffd84d")}}
  ctx.restore();
  function arm(ax,ay,rot,back,batAng,snk,len){   // rubber-hose arm with a white cartoon glove
    len=len||30;var hx2=ax-Math.sin(rot)*len*s,hy2=ay+Math.cos(rot)*len*s,mx=(ax+hx2)/2-Math.cos(rot)*5*s,my=(ay+hy2)/2-Math.sin(rot)*5*s;
    ctx.lineCap="round";ctx.strokeStyle=INK;ctx.lineWidth=8*s;ctx.beginPath();ctx.moveTo(ax,ay);ctx.quadraticCurveTo(mx,my,hx2,hy2);ctx.stroke();
    ctx.strokeStyle=back?"#241912":"#3a2a1e";ctx.lineWidth=5.2*s;ctx.stroke();
    if(!back){ctx.save();ctx.translate(.8*s,-1*s);ctx.strokeStyle="rgba(255,225,190,.2)";ctx.lineWidth=1.4*s;ctx.stroke();ctx.restore()}
    if(batAng!=null&&!back){ctx.save();ctx.translate(hx2,hy2);ctx.rotate(batAng);if(b.buff&&b.buff.k=="ultra")ctx.scale(1.5,1.5);else if(len!=30)ctx.scale(1.15,1.15);bat(s,K>0&&BLOOD,b.buff&&b.buff.k=="ultra");ctx.restore()}
    ctx.save();ctx.translate(hx2,hy2);ctx.rotate(rot);if(back)ctx.globalAlpha*=.92;glove(s,b.color);ctx.restore();
    if(snk&&b.snack&&b.t<.72){ctx.save();ctx.translate(hx2+6*s,hy2-8*s);var sc=Math.min(1,b.t/.3)*1.5;ctx.scale(sc,sc);ctx.rotate(-.4);snack(b.snack,s,0);ctx.restore()}}
}


var BSZ=.62/1.75;
/* one bag, facing right, feet at (0,0). The caller has already moved, flipped, grown and tipped it. */
function draw(e,noShadow){var sT=e.swT||SWING,dead=!!e.dead,kk=e.swing>0?(sT-e.swing)/sT:-1,st='walk',t=0;
  if(dead)st='ko';else if(e.fall>0)st='drop';else if(e.ult>0){st='ultra';t=1.5-e.ult}
  else if(kk>=0){if(kk<.42){st='windup';t=EO(kk/.42)*.3}else if(kk<.55){st='swing';t=(kk-.42)/.13*.1}else{st='follow';t=(kk-.55)/.45*.3}}
  else if(e.dress>0){st='gear';t=DRESS-e.dress}else if(e.et>=0){st='eat';t=e.et}else if(e.dn>0){st='dance';t=DANCE-e.dn}
  bag({x:0,y:0,size:BSZ,paper:(e.paper||0)%PAPERS.length,fv:e.bfv||0,color:hex(e.color),nc:e.color,shoe:hex(e.color),state:st,t:t,ph:e.p*1.3,phase:e.ph,walkAmt:e.wa||0,face:1,dir:1,squish:0,
    hurt:e.hurt>0?e.hurt:0,kills:e.wins||0,armor:!dead&&e.shield>T&&!(e.dress>0)?1:0,armorEnd:e.shield,buff:e.bf&&e.bf.k!='armor'?e.bf:null,snack:'pizza',
    blink:((T+e.ph*5)%4.3)<.12?1:-1,seed:e.seed%997,move:e.dm||0,lv:2,kv:0,ky:0,spin:0,jmp:0,as:ARMOR_STYLE,shadow:!noShadow&&!dead&&!(e.fall>0)});
  if(kk>=.4&&kk<.7&&!dead)smear(kk)}
/* the bat's smear: a bright crescent where the bat just went, with speed lines */
function smear(kk){var k=kk<.55?(kk-.4)/.15:1,f=kk<.55?1:1-(kk-.55)/.15,a0=-2.5,a1=a0+(3.3)*EO(Math.min(1,k));if(a1<=a0+.05)return;
  ctx.save();ctx.translate(12,-42);ctx.globalAlpha=.75*f;var g=ctx.createRadialGradient(0,0,16,0,0,44);g.addColorStop(0,'rgba(255,255,255,0)');g.addColorStop(.75,'rgba(255,255,255,.9)');g.addColorStop(1,'rgba(255,240,200,.2)');
  ctx.fillStyle=g;ctx.beginPath();ctx.arc(0,0,44,Math.max(a0,a1-1.7),a1);ctx.arc(0,0,27,a1,Math.max(a0,a1-1.7),true);ctx.closePath();ctx.fill();
  ctx.strokeStyle='rgba(255,255,255,.8)';ctx.lineWidth=1.6;ctx.lineCap='round';for(var i=0;i<3;i++){var an=a1-.5-i*.45;if(an<a0)break;ctx.beginPath();ctx.arc(0,0,48+i*4,an-.35,an);ctx.stroke()}ctx.restore()}
return {draw:draw,PAPERS:PAPERS};
})();

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
  if(SHK>0)ctx.translate(rnd(-SHK,SHK),rnd(-SHK,SHK)*.6);   /* 1.20.0: a little shake on a big hit */
  var u=U,K=CFG.crown?king():null,fsz=Math.max(11,Math.round(18*u));
  ctx.font='700 '+fsz+'px Outfit,Tajawal,sans-serif';
  var placed=[];alive().sort(function(a,b){return a.x-b.x}).forEach(function(e){e.lab=e.name+(e.wins>0?'  x'+e.wins:'');e.lw=ctx.measureText(e.lab).width+14;
    e.ly=G-(TOP*e.by+6)*e.s*u-8;placed.push(e)});
  var ms=Math.max.apply(null,placed.map(function(e){return e.s}).concat([1])),top=G-(TOP+6)*ms*u-8;NAMEY=CFG.names?top-fsz:1e9;placed.forEach(function(e){e.ly=top});   /* 1.19.0: one line of names, at the tallest soldier's height (a bigger winner doesn't lift his own name) */
  var list=ents.slice().sort(function(a,b){return ((a.jmp>0)*2+(a.swing>0))-((b.jmp>0)*2+(b.swing>0))||(a.dead?-1:a.wins)-(b.dead?-1:b.wins)||a.wt-b.wt});   /* (a JUMPY jump is drawn over everyone) */
  var BB=isB(),GG=isG();if(BB)BEAR.under();
  list.forEach(function(e){
    ctx.save();ctx.globalAlpha=Math.max(0,e.a);
    var sT=e.swT||SWING,sk=e.swing>0?(sT-e.swing)/sT:0,lung=e.swing>0?(GG?(sk<.42?-7*EO(sk/.42):sk<.55?-7+25*EO((sk-.42)/.13):18*(1-EO((sk-.55)/.45))):Math.sin(sk*Math.PI)*9)*e.s*u*e.dir:0;   /* a bag leans back, then steps into the swing */
    ctx.translate(e.x+lung,G-e.fall-(e.jmp>0?Math.sin(Math.PI*(1-e.jmp/JUMP))*165*e.s*U:0));
    if(BLD()&&e.dead&&e.dv<2){var bq=Math.min(1,e.dt/.9),pw=BB?1.6:1,bx=(e.dv===0?1:-1)*e.fd*22*e.s*u;ctx.fillStyle='#8a0c13';ctx.beginPath();ctx.ellipse(bx,3,30*pw*bq*e.s*u,6*pw*bq*e.s*u,0,0,7);ctx.fill();ctx.fillStyle='#c4141d';ctx.beginPath();ctx.ellipse(bx+3,2.5,20*pw*bq*e.s*u,3.6*pw*bq*e.s*u,0,0,7);ctx.fill()}
    if(e.fall<=0&&!e.dead&&!GG){soft(0,2,(BB?34:23)*e.s*u*e.bx,(BB?8:6.5)*e.s*u,.5);soft(0,2,(BB?18:12)*e.s*u*e.bx,(BB?4:3.4)*e.s*u,.35)}   /* 1.20.0: a soft shadow with a darker core */
    var tq=e.tn>0?.26+.74*Math.abs(Math.cos((1-e.tn/TURN)*Math.PI)):1;   /* turning on the spot, never paper-thin */
    ctx.save();ctx.scale(e.s*u*e.dir*e.bx*tq,e.s*u*e.by);var ld=e.fd===e.dir?1:-1,q;
    if(!e.dead&&e.fall<=0)fun(e,BB,GG);   /* 1.20.0: a power-up's glow, and the dance moves */
    if(e.dead&&e.dv===3){}
    else if(e.dead){q=Math.min(1,e.dt/.4);q=q*q;if(e.dv===2){ctx.translate(0,e.ky/(e.s*u)-40);ctx.rotate(ld*e.dt*9);ctx.translate(0,40)}
      else{var q1=Math.min(1,e.dt/.55),lean=e.dv===1?(q1<.3?.25*(q1/.3):.25-1.75*Math.pow((q1-.3)/.7,2)):1.5*q;ctx.translate(0,-10);ctx.rotate(ld*lean);ctx.translate(0,10)}}
    else if(e.fall>0){ctx.translate(0,-40);ctx.rotate(e.fv===0?-1.35+Math.sin(T*5)*.12:e.fv===1?T*8:Math.sin(T*9)*.18);ctx.translate(0,40)}
    else if(e.land>0){q=e.land/LAND;if(e.fv===2){ctx.scale(1+.18*Math.sin(q*Math.PI),1-.22*Math.sin(q*Math.PI))}
      else{var h=q>.45?1:q/.45;ctx.translate(0,-10);ctx.rotate((e.fv===0?-1.5:1.5)*h*h);ctx.translate(0,10)}}
    if(e.hurt>0){var hq=e.hurt/HURT;ctx.translate(0,-12);ctx.rotate(ld*.45*(1-hq*hq));ctx.translate(0,12)}
    var oc=RIMC,ow=RIMW,os=RIMS,oa=RIMA;if(e.flash>0){RIMC='rgba(255,255,255,.96)';RIMW=5.5;RIMS='#ffffff';RIMA=.96}
    if(GG){var hq=e.hurt>0?Math.sin(Math.min(1,(HURT-e.hurt)/HURT)*Math.PI):0;if(hq>0){ctx.translate(0,-40);ctx.scale(1-.16*hq,1+.1*hq);ctx.rotate(-.18*hq);ctx.translate(0,40)}BAG.draw(e)}else if(BB)BEAR.draw(e);else outlined(e);RIMC=oc;RIMW=ow;RIMS=os;RIMA=oa;
    if(e.swing>0&&!e.dead&&!BB&&!GG)slash(e);
    if(e.et>=0&&e.et<.72&&!e.dead&&!GG)pizza(e,BB);   /* (a bag holds its own slice) */
    ctx.restore();
    ctx.restore();
  });
  if(BB)BEAR.over();
  IMP.forEach(function(m){var k=m.t/.22,r=(14+24*EO(Math.min(1,k*1.6)))*m.s*u,n=10;ctx.save();ctx.translate(m.x,m.y);ctx.rotate(m.d*.2);ctx.globalAlpha=1-k*k;   /* a comic impact star */
    ctx.beginPath();for(var i=0;i<n*2;i++){var an=i/(n*2)*6.283,rr=i%2?r*.45:r*(i%4==0?1:.8);ctx.lineTo(Math.cos(an)*rr,Math.sin(an)*rr*.8)}ctx.closePath();ctx.fillStyle=m.w?'#e8f2fb':'#ffe27a';ctx.fill();ctx.lineWidth=3*u;ctx.strokeStyle=m.w?'#9fb8d0':'#ff8a2a';ctx.stroke();
    ctx.beginPath();for(var j=0;j<n*2;j++){var an2=j/(n*2)*6.283,r2=j%2?r*.22:r*.5;ctx.lineTo(Math.cos(an2)*r2,Math.sin(an2)*r2*.8)}ctx.closePath();ctx.fillStyle='#fff';ctx.fill();ctx.restore()});
  RINGS.forEach(function(r){var k=r.t/.8;ctx.save();ctx.globalAlpha=1-k;ctx.strokeStyle='#ffd84d';ctx.lineWidth=(10-7*k)*u;ctx.shadowColor='#ffd84d';ctx.shadowBlur=18;ctx.beginPath();ctx.ellipse(r.x,G-30*u,(30+k*700)*u,(14+k*120)*u,0,0,7);ctx.stroke();ctx.restore()});
  ctx.font='700 '+fsz+'px Outfit,Tajawal,sans-serif';ctx.textAlign='center';
  alive().sort(function(a,b){return a.wins-b.wins||a.wt-b.wt}).forEach(function(e){if(e.fall>0||!CFG.names)return;var ly=e.ly;rr(e.x-e.lw/2,ly-fsz-3,e.lw,fsz+9,7);ctx.fillStyle='rgba(8,8,14,.5)';ctx.fill();   /* 1.19.0: a lighter name tag */
    ctx.fillStyle=e.color;ctx.fillText(e.lab,e.x,ly);
    if(e.bf&&e.bf.k!='ultra'&&BUFF[e.bf.k]){var B=BUFF[e.bf.k],r=fsz*.62,bx=e.x+e.lw/2+r+4,by=ly-fsz*.36,lf=Math.max(0,e.bf.end-T)/B[2];   /* 1.20.0: the power-up and how long it has left */
      ctx.save();ctx.beginPath();ctx.arc(bx,by,r,0,7);ctx.fillStyle='rgba(8,8,14,.6)';ctx.fill();ctx.strokeStyle=B[1];ctx.lineWidth=Math.max(2,r*.22);ctx.beginPath();ctx.arc(bx,by,r,-Math.PI/2,-Math.PI/2+6.283*lf);ctx.stroke();
      ctx.font=Math.round(r*1.05)+'px sans-serif';ctx.fillStyle='#fff';ctx.textBaseline='middle';ctx.fillText(B[0].split(' ')[0],bx,by+1);ctx.restore();ctx.font='700 '+fsz+'px Outfit,Tajawal,sans-serif'}});
  if(K&&K.fall<=0){ctx.save();
    if(CFG.names){ctx.translate(K.x,K.ly-fsz-5+Math.sin(T*3+K.ph)*1.5);var cs=u*1.05;ctx.scale(cs,cs);ctx.translate(0,TOP+1-Math.sin(T*3+K.ph)*1.5)}   /* 1.19.0: the crown sits on top of the king's name tag */
    else{ctx.translate(K.x,G);ctx.scale(K.s*u,K.s*u*K.by);if(isG())ctx.translate(0,14)}   /* names off: on his head as before */
    crown(K);ctx.restore()}
  parts.forEach(function(p){ctx.globalAlpha=Math.min(1,p.life*2);ctx.fillStyle=p.c;ctx.beginPath();ctx.arc(p.x,p.y,p.r*u,0,7);ctx.fill()});ctx.globalAlpha=1;
  if(FL>0){ctx.fillStyle='rgba(255,244,214,'+Math.min(.55,FL*.55)+')';ctx.fillRect(0,0,W,H)}   /* 1.20.0: ULTRA KILL flash */
  floats.forEach(function(f){ctx.globalAlpha=Math.min(1,f.life*2);ctx.font='900 '+Math.round((26*u+4)*(f.sz||1))+'px Outfit,Tajawal,sans-serif';ctx.textAlign='center';
    ctx.lineWidth=5;ctx.lineJoin='round';ctx.lineCap='round';ctx.strokeStyle='rgba(0,0,0,.7)';ctx.strokeText(f.t,f.x,f.y);   /* round, or sharp letters shoot out black spikes */ctx.fillStyle=f.c;ctx.fillText(f.t,f.x,f.y)});ctx.globalAlpha=1;
}
/* 1.20.0: a power-up's glow (under him), the dance moves (they move the whole character) */
function rgba(h,a){var n=parseInt(hexOf(h).slice(1),16);return 'rgba('+(n>>16)+','+(n>>8&255)+','+(n&255)+','+a+')'}
function fun(e,BB,GG){
  if(e.bf){var bc=e.bf.k=='ultra'?'#ffd84d':BUFF[e.bf.k]?BUFF[e.bf.k][1]:'#fff',pu=.55+.25*Math.sin(T*8+e.ph),g=ctx.createRadialGradient(0,-44,6,0,-44,62);
    g.addColorStop(0,rgba(bc,.42*pu));g.addColorStop(.6,rgba(bc,.18*pu));g.addColorStop(1,rgba(bc,0));ctx.fillStyle=g;ctx.beginPath();ctx.ellipse(0,-44,48,62,0,0,7);ctx.fill();
    if(e.bf.k=='speed'&&!(e.rest>0)&&!(e.dn>0)&&!GG){ctx.strokeStyle=rgba(bc,.6);ctx.lineWidth=2;ctx.lineCap='round';for(var i=0;i<3;i++){var yy=-20-i*20,o=(T*90+i*23)%40;ctx.beginPath();ctx.moveTo(-26-o,yy);ctx.lineTo(-12-o,yy);ctx.stroke()}}}
  if(e.dn>0&&!GG){var dk=DANCE-e.dn,fd=Math.min(1,dk/.2,e.dn/.2),hp=Math.abs(Math.sin(dk*10));
    if(e.dm==0)ctx.translate(0,-hp*8*fd);
    else if(e.dm==1){ctx.translate(0,-28);ctx.rotate(Math.sin(dk*10)*.17*fd);ctx.translate(0,28-hp*2*fd)}
    else{var c=Math.cos(dk*Math.PI*2/1.05);if(Math.abs(c)<.22)c=c<0?-.22:.22;ctx.scale(1-fd+fd*c,1);ctx.translate(0,-hp*3*fd)}}}
/* !eat: a slice of pizza in his hand, up to the mouth, gone in one bite */
function pizza(e,BB){var x,y,k=e.et<.4?EO(e.et/.4):1;
  if(BB){var s=.62,a=-2.25*k;x=1*s-Math.sin(a)*30*s;y=-72*s+Math.cos(a)*30*s}
  else{var a1=-1.05*k,a2=a1-.35-1.95*k;x=-Math.sin(a1)*8.5-Math.sin(a2)*11;y=-44+Math.cos(a1)*8.5+Math.cos(a2)*11}
  var sc=Math.min(1,e.et/.15)*(e.et>.62?1+(e.et-.62)*3:1),sh=e.et>.4?Math.sin(e.et*60)*.06:0;
  ctx.save();ctx.translate(x,y);ctx.rotate(-.75+sh+(BB?.2:0));ctx.scale(sc,sc);
  ctx.beginPath();ctx.moveTo(0,-17);ctx.lineTo(8,1);ctx.quadraticCurveTo(0,4.5,-8,1);ctx.closePath();
  var g=ctx.createLinearGradient(0,-17,0,2);g.addColorStop(0,'#ffe08a');g.addColorStop(1,'#f4b740');ctx.fillStyle=g;ctx.fill();ctx.strokeStyle='rgba(60,30,10,.75)';ctx.lineWidth=1.2;ctx.stroke();
  ctx.fillStyle='#c9361f';[[0,-10,2],[-2.6,-3.5,2.1],[3.2,-4,1.8]].forEach(function(p){ctx.beginPath();ctx.arc(p[0],p[1],p[2],0,7);ctx.fill()});
  ctx.fillStyle='rgba(255,255,255,.4)';ctx.beginPath();ctx.arc(-.6,-10.6,.7,0,7);ctx.fill();
  ctx.lineCap='round';ctx.strokeStyle='#c27a33';ctx.lineWidth=4;ctx.beginPath();ctx.moveTo(-8,1.5);ctx.quadraticCurveTo(0,5.5,8,1.5);ctx.stroke();
  ctx.strokeStyle='#e9a457';ctx.lineWidth=1.4;ctx.beginPath();ctx.moveTo(-6.5,1.2);ctx.quadraticCurveTo(0,4.4,6.5,1.2);ctx.stroke();
  ctx.restore()}
function autoFun(){var l=alive().filter(function(e){return !busy(e)});if(!l.length)return;var e=pick(l);if(Math.random()<.55)dance(e);else{var r=Math.random()*100;eat(e,r<30?'speed':r<55?'jump':r<80?'rage':'armor')}}
function autoSpawn(){var free=NAMES.filter(function(n){return !find('demo:'+n)});if(free.length&&alive().length<Math.min(12,CFG.max||20)){var n=pick(free);spawn(n,'demo:'+n)}}
function autoAttack(){var l=alive().filter(function(e){return e.fall<=0&&e.land<=0&&T>=e.cdA&&!(e.dress>0)});if(!l.length)return;var hit=l.filter(function(e){return near(e)});
  attack(hit.length&&Math.random()<.7?pick(hit):pick(l))}
function autoProtect(){var l=alive().filter(function(e){return e.shield<=T&&T>=e.cdP&&e.fall<=0});if(l.length)protect(pick(l))}
if(DEMO)setInterval(function(){if(!CFG.on||document.hidden)return;var n=alive().length,r=Math.random();if(n<7)autoSpawn();else if(r<.27)autoSpawn();else if(r<.75)autoAttack();else if(r<.85)autoProtect();else autoFun()},1300);   /* 1.20.0: + dancing and eating */
/* what the app says happened (about once a second). The first answer only marks "from now on": old commands are never replayed. */
var SEEN=null,BOOT=null;
window.ARENA_AFTER=function(){return SEEN==null?999999999:SEEN};
window.ARENA_FEED=function(a){if(!a||ALINE||CBONLY||CHATONLY||(EDIT&&!DEMO))return;
  var c=a.cfg||{},was=[CFG.size,CFG.ground,CFG.left,CFG.right].join();CFG=c;if(DEMO)CFG.on=true;if(was!==[CFG.size,CFG.ground,CFG.left,CFG.right].join())fit();
  if(!CFG.on){ents=[];parts=[];floats=[]}
  if(BOOT!==a.boot||SEEN==null){BOOT=a.boot;SEEN=a.last;return}
  (a.events||[]).forEach(function(ev){if(ev.id<=SEEN)return;SEEN=ev.id;if(!CFG.on)return;
    if(DEMO&&ev.t!='clear'&&String(ev.u).indexOf('test:')!==0)return;       /* (the preview in the app: only its own made-up viewers) */
    if(ev.t=='spawn')spawn(ev.n||ev.u,ev.u,ev.c);else if(ev.t=='attack')attack(find(ev.u));else if(ev.t=='protect')protect(find(ev.u));
    else if(ev.t=='dance')dance(find(ev.u));else if(ev.t=='eat')eat(find(ev.u),ev.b);   /* 1.20.0 */
    else if(ev.t=='leave'){var le=find(ev.u);if(le&&!le.leaving){le.leaving=1;le.rest=0;le.tn=0;le.swing=0;le.dn=0;le.qeat='';le.dir=le.x<W/2?-1:1;floats.push({x:le.x,y:G-108*le.s*U,t:'\ud83d\udc4b',c:'#fff',life:1.2,sz:.9})}}
    else if(ev.t=='clear'){ents.forEach(function(e){if(!e.dead)gone(e)});BEAR.clear()}})};
/* 1.20.0: Overlays > Arena > Characters: every look side by side in two rows, packed close (a still picture) */
function mk(q){spawn('lineup','lineup:'+Math.random(),q.c);var e=ents.pop();if(q.paper!=null){e.paper=q.paper;e.bfv=q.fv||0}e.fall=0;e.land=0;e.rest=1;e.p=0;e.dir=1;e.s=e.ts=q.s;e.wins=q.w||0;e.shield=q.armor?T+99:0;e.dress=0;e.wa=0;e.ph=1.3;
  if(q.pal!=null){e.pal=PALS[q.pal];e.ptype=PT[q.pt];e.skin=SKINS[q.skin]}if(q.fur!=null)e.fur=q.fur;return e}
function lineup(){DPR=Math.min(3,window.devicePixelRatio||1);W=innerWidth||400;H=innerHeight||200;cv.width=Math.round(W*DPR);cv.height=Math.round(H*DPR);
  ctx.setTransform(DPR,0,0,DPR,0,0);ctx.clearRect(0,0,W,H);T=4.2;var B=isB(),GG=isG(),rows,gap;
  if(GG){rows=[[0,1,2,3,4,5,6,7].map(function(i){return {x:i*43,s:1,paper:[0,3,5,7,1,9,13,2][i],fv:i,c:COLORS[i]}}),   /* 1.20.0: bags: 16 papers, 8 faces, bubble wrap, a winner with the crown */
    [8,10,11,12,14,15,4,6].map(function(p,i){var q={x:i*44+(i>5?(i-5)*6:0),paper:p,fv:(i+3)%8,c:COLORS[(i+8)%COLORS.length],armor:i==2,w:i>5?(i-5)*3:0};q.s=1+q.w*.06;if(i==7)q.crown=1;return q})];gap=128}
  else if(B){rows=[[0,1,2,3,4,5,6].map(function(i){return {x:i*41,s:1.12,fur:i,c:COLORS[i]}}),
    [{fur:0,armor:1},{fur:4,w:1},{fur:6,w:2,armor:1},{fur:2,w:3},{fur:5,w:4},{fur:1,w:5,crown:1}].map(function(q,i){q.x=[0,47,95,145,198,257][i];q.s=Math.min(1.5,1+(q.w||0)*.1);q.c=COLORS[(i+7)%COLORS.length];return q})];gap=136}
  else{rows=[[0,1,2,3,4,5].map(function(i){return {x:i*47.5,s:1,pal:[0,3,5,1,6,2][i],pt:i%3,skin:i,c:COLORS[i]}}),
    [{pal:4,pt:0,skin:0},{pal:7,pt:1,skin:3},{pal:8,pt:2,skin:4},{pal:2,pt:1,skin:1,armor:1},{pal:0,pt:2,skin:2,w:3,s:1.2},{pal:3,pt:0,skin:5,w:6,s:1.42,crown:1}].map(function(q,i){q.x=[0,47.5,95,142.5,195,256][i];q.s=q.s||1;q.c=COLORS[(i+6)%COLORS.length];return q})];gap=131}
  var span=function(r){return r[r.length-1].x},wide=Math.max(span(rows[0]),span(rows[1]))+(B?62:GG?60:52)*1.5,tall=gap+TOP*1.12+30;
  var k=Math.min(W/wide,H/tall)*.96,y1=(H-tall*k)/2+(TOP*1.12+22)*k;
  rows.forEach(function(r,ri){var x0=W/2-span(r)*k/2,y=y1+ri*gap*k;
    r.forEach(function(q){var e=mk(q);ctx.save();ctx.translate(x0+q.x*k,y);
      if(!GG){soft(0,2*k,(B?34:23)*q.s*k,(B?8:6.5)*q.s*k,.5);soft(0,2*k,(B?18:12)*q.s*k,(B?4:3.4)*q.s*k,.35)}
      ctx.scale(q.s*k,q.s*k);if(GG)BAG.draw(e);else if(B)BEAR.draw(e);else outlined(e);if(q.crown){if(GG)ctx.translate(0,14);crown(e)}ctx.restore()})})}
if(ALINE){CFG.kind=['bears','bags'].indexOf(q.get('kind'))>=0?q.get('kind'):'soldiers';CFG.blood=q.get('blood')!='0';addEventListener('resize',lineup);setTimeout(lineup,30)}
else{fit();addEventListener('resize',fit)}
var last=performance.now(),idle=true;
(function loop(now){var dt=Math.min(.05,(now-last)/1000);last=now;
  if(HS>0){HS-=dt;dt*=.04}   /* 1.20.0: hit-stop */
  if(CFG.on&&(ents.length||parts.length||floats.length)){step(dt);draw();idle=false}
  else if(!idle){ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,cv.width,cv.height);idle=true}
  requestAnimationFrame(loop)})(last);
})();
function napping(){if(window.parent===window)return false;try{return document.hidden||!!(parent.asleep&&parent.asleep())}catch(e){return false}}   // 1.19.0: the preview inside the app rests while the app is minimised (OBS never does)
async function tick(){if(ALINE)return;if(napping()){setTimeout(tick,1500);return}try{var r=await fetch("/api/overlay"+(q.get("only")?"?only="+encodeURIComponent(q.get("only")):(CBONLY?"?edit=1&cb=1":CHATONLY?"?chat=1":EDIT?"?edit=1":ADEMO?"?edit=1":"")).replace(/^([^?]*)$/,"$1?x=1")+"&ar="+ARENA_AFTER(),{cache:"no-store"});
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
