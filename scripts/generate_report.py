"""data.json → report.html : MSTR 매일 자동 기술적 점검."""
import json, sys, os
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from indicators import sma, bb, rsi, vixfix

KST = timezone(timedelta(hours=9))
D = json.load(open("data.json"))
O = D["ohlc"]

def cols(key):
    r = O.get(key, [])
    return r, [x[2] for x in r], [x[3] for x in r], [x[4] for x in r]
def ym(ts): return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y.%m")
def ymd(ts): return datetime.fromtimestamp(ts, timezone.utc).strftime("%y.%m.%d")
def f(v, d=2): return f"{v:,.{d}f}"
def pct(a, b): return (a / b - 1) * 100
def clamp(x): return max(0, min(100, x))

def green_clusters(r, sig, min_len=3, gap=2):
    out, start, cnt, miss = [], None, 0, 0
    for i, s in enumerate(sig):
        if s:
            if start is None: start, cnt = i, 0
            cnt += 1; miss = 0
        elif start is not None:
            miss += 1
            if miss > gap:
                if cnt >= min_len: out.append(ym(r[start][0]))
                start = None
    if start is not None and cnt >= min_len: out.append(ym(r[start][0]))
    return out

# ── 월봉 ──
mr, mh, ml, mc = cols("MSTR_1mo")
bm, bu, bl = bb(mc); mrs = rsi(mc); mw, _, mrh, msig = vixfix(mh, ml, mc)
M = dict(m=bm[-1], u=bu[-1], lo=bl[-1], rsi=mrs[-1], rsi_prev=mrs[-2], w=mw[-1], rh=mrh[-1], sig=msig[-1],
         g12=sum(msig[-12:]), clusters=green_clusters(mr, msig), mclose=mc[-1], mprev=mc[-2])
M["pb"] = (mc[-1] - M["lo"]) / (M["u"] - M["lo"])

# ── 일봉 ──
dr, dh, dl, dc = cols("MSTR_1d")
c = dc[-1]
ma218 = sma(dc, 218)[-1]; env = ma218 * 1.07   # 218일선 기준
s200 = sma(dc, 200); disp = c / s200[-1] * 100
disp_hist = [x / y * 100 for x, y in zip(dc[-250:], s200[-250:]) if y]
disp_min, disp_max = min(disp_hist), max(disp_hist)
ai = max(range(len(dh)), key=lambda i: dh[i]); ath, ath_d = max(dh[ai], max(mh)), ymd(dr[ai][0])
li = min(range(max(0, len(dl) - 400), len(dl)), key=lambda i: dl[i]); low, low_d = dl[li], ymd(dr[li][0])
swing = max(dh[-120:])
above218, above_env = c > ma218, c > env

# ── 맥락: BTC · M2 ──
br, bh, bl_, bc = cols("BTC_1mo")
btc = dict(c=bc[-1], prev=bc[-2], rsi=rsi(bc)[-1]) if len(bc) > 20 else None
M2 = D.get("m2", {}); m2r = M2.get("rows", [])
if len(m2r) > 70:
    n = len(m2r) - 1
    m2_now, m2_3m = m2r[n], m2r[n - 63]
    pk = max(range(max(0, n - 260), n + 1), key=lambda k: m2r[k][1])
    m2_peak = m2r[pk]
    m2_chg3, m2_from_pk = pct(m2_now[1], m2_3m[1]), pct(m2_now[1], m2_peak[1])
    m2_chg1 = pct(m2_now[1], m2r[n - 21][1])
    m2_dir = "하락" if (m2_from_pk <= -0.7 and m2_chg1 < 0) or m2_chg1 < -0.7 else ("상승" if m2_chg1 > 0.5 else "횡보")
else:
    m2_now = None; m2_chg3 = m2_chg1 = m2_from_pk = 0.0; m2_dir = "—"

# ── 판단 ──
if c > M["m"]:
    pill, cls, head = "추세 전환 확인", "p-turn", "월봉 BB 중심선 위로 올라섰습니다. 하락 추세 안의 반등을 넘어 추세 전환 쪽으로 무게가 실립니다."
elif M["g12"] >= 3 and above218:
    pill, cls, head = "바닥 신호 출현", "p-turn", "월봉 Vix Fix 녹색 군집(투매) 뒤 일봉 218일선을 회복했습니다. 다만 월봉 BB 중심선 아래라 아직 \"하락 추세 안의 반등\"입니다."
elif M["g12"] >= 3:
    pill, cls, head = "바닥 다지기", "p-mix", "최근 1년 안에 월봉 Vix Fix 투매 신호가 나왔지만 일봉 218일선 아래입니다. 바닥 확인 전 단계입니다."
elif not above218 and M["rsi"] < 45:
    pill, cls, head = "하락 추세", "p-hot", "일봉 218일선 아래, 월봉 RSI 45 미만입니다. 추세가 아래쪽입니다."
else:
    pill, cls, head = "중립", "p-mix", "뚜렷한 바닥·전환 신호 없이 중간 지대에 있습니다."
if disp >= 160: head += " 이격도가 160을 넘어 단기 과열 구간입니다."
elif disp <= 50: head += " 이격도가 50 아래로 과매도 구간입니다."
if m2_now and m2_dir == "하락": head += " Global M2가 하락 중이라 유동성 측면은 역풍입니다."

def gauge(label, val, pos, caps, ticks=(), vix=False):
    tk = "".join(f'<span class="tick" style="left:{x}%"></span>' for x in ticks)
    return (f'<div class="g"><div class="g-top"><span>{label}</span><span>{val}</span></div>'
            f'<div class="track{" vix" if vix else ""}">{tk}<span class="mark" style="left:{clamp(pos):.1f}%"></span></div>'
            f'<div class="g-cap">{"".join(f"<span>{x}</span>" for x in caps)}</div></div>')

def row(name, price, note):
    p = pct(price, c)
    return f'<tr><td>{name}</td><td class="r">{f(price)}</td><td class="r {"up" if p >= 0 else "dn"}">{p:+.1f}%</td><td>{note}</td></tr>'

levels = sorted([
    (ath, f"사상 최고가 ({ath_d})", f"현재 고점 대비 {pct(c, ath):.0f}%"),
    (M["m"], "월봉 BB 중심", "추세 전환 확인선. 여기 위 월봉 마감이 핵심"),
    (swing, "최근 120일 고점", "직전 스윙 고점. 1차 저항"),
    (env, "218일선 +7% 엔벨로프", "이 위에서 버티면 추세 강화"),
    (ma218, "218일선", "장기 추세선. " + ("깨지면 반등 실패 신호" if above218 else "회복해야 바닥 확인")),
    (low, f"최근 저점 ({low_d})", "바닥 신호가 무효가 되는 선"),
], key=lambda t: -t[0])
rows_html, placed = [], False
for p, nm, note in levels:
    if not placed and p < c:
        rows_html.append(f'<tr class="cur"><td>현재가</td><td class="r">{f(c)}</td><td class="r">—</td><td></td></tr>'); placed = True
    if nm.startswith("최근 120일 고점") and p <= c: continue
    rows_html.append(row(nm, p, note))
if not placed: rows_html.append(f'<tr class="cur"><td>현재가</td><td class="r">{f(c)}</td><td class="r">—</td><td></td></tr>')

read = []
read.append(f"<b>일봉: 218일선 {f(ma218)} · +7% 엔벨로프 {f(env)}.</b> 현재가는 " +
            ("엔벨로프 상단까지 넘어선 상태로, 장기 추세선을 확실히 회복했습니다." if above_env else ("218일선 위, 엔벨로프 아래입니다. 회복 초입입니다." if above218 else "218일선 아래입니다. 장기 추세는 아직 하락입니다.")) +
            "")
read.append(f"<b>이격도(200) {disp:.0f}.</b> 최근 1년 범위 {disp_min:.0f}~{disp_max:.0f}. " +
            ("160 이상 과열 구간으로, 과거 이 수준은 단기 고점 부근이었습니다." if disp >= 160 else
             "50 이하 과매도 구간으로, 과거 이 수준은 바닥권이었습니다." if disp <= 50 else
             f"과열선 160까지 {160 - disp:.0f}포인트, 과매도선 50과는 {disp - 50:.0f}포인트 떨어져 있습니다."))
if M["g12"] >= 3:
    read.append(f"<b>월봉 Vix Fix: 최근 12개월 중 {M['g12']}개월이 녹색(투매).</b> 과거 녹색 군집 시작: {', '.join(M['clusters'][-3:])}. 2022년 군집 뒤에는 바닥을 잡고 2023~24년 대세 상승으로 갔습니다. " +
                ("이번 달도 녹색으로 공포가 진행 중입니다." if M["sig"] else f"이번 달은 {M['w']:.1f}로 기준선 {M['rh']:.1f} 아래(빨강), 공포가 빠지는 중입니다."))
else:
    read.append(f"<b>월봉 Vix Fix {M['w']:.1f} / 기준 {M['rh']:.1f}.</b> " + ("투매 신호가 켜졌습니다." if M["sig"] else "투매 신호 없음."))
read.append(f"<b>월봉 RSI {M['rsi']:.1f} (전월 {M['rsi_prev']:.1f}).</b> " + ("50 위라 월봉 모멘텀이 상승 쪽입니다." if M["rsi"] >= 50 else "50을 넘으면 월봉 모멘텀이 상승 쪽으로 넘어갑니다. 2023년 상승 초입에도 RSI 50 돌파가 먼저 나왔습니다."))
read.append(f"<b>월봉 BB {f(M['u'])} / {f(M['m'])} / {f(M['lo'])}, %b {M['pb']:.2f}.</b> " + ("중심선 위입니다." if c > M["m"] else f"중심선까지 {pct(M['m'], c):+.0f}% 남았습니다. 중심선 위 월봉 마감 전까지는 반등 국면으로 봅니다."))
if m2_now:
    read.append(f"<b>Global M2 ${m2_now[1]:.1f}조 — {m2_peak[0]} 고점 대비 {m2_from_pk:+.1f}%, 최근 1개월 {m2_chg1:+.1f}%로 {m2_dir} 중.</b> " +
                ("유동성이 줄고 있어 MSTR 같은 고베타 자산에는 역풍입니다. 반등이 M2 반등 없이 이어질지가 관건입니다." if m2_dir == "하락" else
                 "유동성이 늘고 있어 우호적입니다." if m2_dir == "상승" else "유동성은 정체 상태입니다.") +
                f" MSTR은 고점 대비 {pct(c, ath):.0f}%로 M2와 괴리가 큽니다.")
if btc:
    read.append(f"<b>비트코인 {f(btc['c'], 0)}달러, 이번 달 {pct(btc['c'], btc['prev']):+.1f}%, 월봉 RSI {btc['rsi']:.0f}.</b> MSTR은 비트코인 레버리지 성격이라 BTC가 꺾이면 위 신호들이 쉽게 무효가 됩니다. BTC 대비 프리미엄(mNAV)은 따로 확인하세요.")


AL = json.load(open("alerts.json")) if os.path.exists("alerts.json") else None
if AL:
    al_rows = "".join(f'<li class="{"on" if x["on"] and x["kind"]=="buy" else ("warn" if x["on"] else "")}"><span>{"●" if x["on"] and x["kind"]=="buy" else ("▲" if x["on"] else "○")}</span> {x["name"]} <em>{x["val"]}</em></li>' for x in AL["conds"])
    al_html = f'''<section class="card"><h2>매수 타이밍 <span class="pill st-{AL["stage"]}">{AL["stage"]}</span><span class="eyebrow">조건 {AL["score"]}/6</span></h2>
<p>{AL["stage_txt"]}</p><ul class="alist">{al_rows}</ul><p class="fine">조건이 새로 켜지면 GitHub 앱 알림이 갑니다.</p></section>'''
else:
    al_html = ""

css = open(os.path.join(os.path.dirname(__file__), "report.css")).read()
now = datetime.now(KST); upd = datetime.fromisoformat(D["updated"]).astimezone(KST)
html = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>MSTR 기술적 점검</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>{css} tr.cur td {{ color:var(--accent); font-weight:600; }} .alist {{ list-style:none; margin:0; padding:0; display:grid; gap:6px; font-size:14px; }} .alist li {{ color:var(--muted); }} .alist li.on {{ color:var(--fg); }} .alist li.on span {{ color:var(--ok); }} .alist li.warn span {{ color:var(--warn); }} .alist em {{ font-style:normal; font-family:var(--mono); font-size:12px; color:var(--muted); margin-left:6px; }} .st-투매,.st-회복 {{ background:rgba(90,212,69,.16); color:#8be37a; }} .st-전환 {{ background:rgba(41,98,255,.2); color:#8fb0ff; }} .st-과열 {{ background:rgba(229,72,77,.16); color:#ff8a8d; }} .st-관망 {{ background:rgba(139,148,162,.18); color:#c9cfd8; }}</style></head><body><div class="wrap">
<header><span class="eyebrow">{now:%Y.%m.%d %H:%M} 자동 생성 · 시세 {upd:%m.%d %H:%M} KST · <a href="./">차트 보기</a></span>
<h1>MSTR 기술적 점검</h1></header>

<div class="bl"><h3>한 줄 판단</h3>
<div class="bl-row"><span class="tag">{f(c)}</span><p><span class="pill {cls}">{pill}</span>{head}</p></div></div>

{al_html}

<section class="card"><h2>지표 <span class="px">{f(c)}</span><span class="eyebrow">전일 {pct(c, dc[-2]):+.2f}% · 이번 달 {pct(mc[-1], M["mprev"]):+.1f}%</span></h2>
<div class="gauges">
{gauge("일봉 이격도(200)", f"{disp:.1f}", disp / 200 * 100, ["0", "50 과매도", "100", "160 과열", "200"], ticks=(25, 50, 80))}
{gauge("월봉 BB 20/2 위치 (%b)", f"{M['pb']:.2f}", M["pb"] * 100, [f"하단 {f(M['lo'])}", f"중심 {f(M['m'])}", f"상단 {f(M['u'])}"], ticks=(50,))}
{gauge("월봉 RSI 14", f"{M['rsi']:.2f}", M["rsi"], ["0", "30", "50", "70", "100"], ticks=(30, 50, 70))}
{gauge("월봉 Williams Vix Fix", f"{M['w']:.2f} / 기준 {M['rh']:.2f}" + (' <b class="on">신호 ON</b>' if M["sig"] else ""), M["w"] / max(M["rh"] / 0.85, 1) * 100, ["0", f"최근 12개월 녹색 {M['g12']}개월"], ticks=(85,), vix=True)}
</div></section>

<section class="card"><h2>핵심 가격대</h2>
<div class="levels"><table><thead><tr><th>가격대</th><th class="r">가격</th><th class="r">현재가 대비</th><th>의미</th></tr></thead><tbody>
{"".join(rows_html)}
</tbody></table></div></section>

<section class="card"><h2>해석</h2><div class="read">{"".join(f"<p>{x}</p>" for x in read)}</div></section>

<section class="card"><h2>시나리오</h2><div class="sc">
<div><span class="h b">추세 전환</span><span>{"218일선 지지 유지" if above218 else "218일선 " + f(ma218, 0) + " 회복"} → {f(swing, 0)} 돌파 → 월봉 BB 중심 {f(M["m"], 0)} 위 마감. 월봉 RSI 50 돌파가 선행 신호.</span></div>
<div><span class="h n">박스권</span><span>{f(min(ma218, c), 0)}~{f(swing, 0)} 사이 등락. Vix Fix가 식으면서 바닥 다지기.</span></div>
<div><span class="h s">반등 실패</span><span>218일선 아래 안착 후 저점 {f(low)} 재시험. 이 저점이 깨지면 바닥 판단 자체가 무효.</span></div>
</div></section>

<section class="card"><h2>매일 볼 것</h2><ol class="check">
<li>일봉이 218일선 <span class="num">{f(ma218, 0)}</span> · 엔벨로프 <span class="num">{f(env, 0)}</span> 위에서 버티는지</li>
<li>이격도(200) <span class="num">{disp:.0f}</span> — <span class="num">160</span> 위 과열, <span class="num">50</span> 아래 과매도</li>
<li><span class="num">{f(swing, 0)}</span> 돌파 여부, 월말엔 월봉 종가가 BB 중심 <span class="num">{f(M["m"], 0)}</span> 근처인지</li>
<li>월봉 RSI <span class="num">50</span> 돌파 (현재 {M["rsi"]:.1f})</li>
<li>Global M2 방향 (현재 {m2_dir if m2_now else "—"}, 고점 대비 {m2_from_pk if m2_now else 0:+.1f}%)</li>
</ol></section>

<p class="fine">Yahoo Finance·FRED·ECB·일본은행·영란은행 데이터로 TradingView와 같은 공식(SMA 200, 엔벨로프 200 +7%, 이격도 200, BB 20/2, RSI 14, CM Williams Vix Fix 22/20/2/50/0.85)을 계산해 자동으로 쓰는 기술적 해석이며, 투자 자문이 아닙니다. 매매 시점과 비중은 본인의 자금 상황과 위험 감내도에 맞춰 직접 판단하세요. 진행 중인 월봉은 월말까지 값이 계속 바뀝니다.</p>
</div></body></html>'''
open("report.html", "w").write(html)
print("report.html", len(html), "bytes |", pill)
