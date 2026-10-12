"""data.json → report.html : 매일 자동 기술적 점검 리포트."""
import json, sys, os
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from indicators import sma, bb, rsi, vixfix

KST = timezone(timedelta(hours=9))
D = json.load(open("data.json"))
O = D["ohlc"]

def merge_live(r, iv):
    if len(r) < 2: return r
    a, b = r[-2], r[-1]
    da, db = datetime.fromtimestamp(a[0], timezone.utc), datetime.fromtimestamp(b[0], timezone.utc)
    same = ((iv == "1mo" and (da.year, da.month) == (db.year, db.month)) or
            (iv == "1wk" and (db - da).days < 7) or (iv == "1d" and da.date() == db.date()))
    return r[:-2] + [[a[0], a[1], max(a[2], b[2]), min(a[3], b[3]), b[4]]] if same else r

def cols(key, iv):
    r = merge_live(O.get(key, []), iv)
    return r, [x[2] for x in r], [x[3] for x in r], [x[4] for x in r]

def ym(ts): return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y.%m")
def ymd(ts): return datetime.fromtimestamp(ts, timezone.utc).strftime("%y.%m.%d")
def f(v, d=2): return f"{v:,.{d}f}"
def pct(a, b): return (a / b - 1) * 100
def sp(p): return f'<span class="{"up" if p >= 0 else "dn"}">{p:+.1f}%</span>'
def clamp(x, lo=0, hi=100): return max(lo, min(hi, x))

def green_clusters(r, sig, min_len=3, gap=2):
    """연속(또는 1~2개월 끊김) 녹색 3개 이상 구간의 시작월 목록"""
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

# ───────── TQQQ 월봉 ─────────
tr, th, tl, tc = cols("TQQQ_1mo", "1mo")
tm, tu, tlo = bb(tc); tw, _, trh, tsig = vixfix(th, tl, tc)
t = dict(c=tc[-1], prev=tc[-2], m=tm[-1], u=tu[-1], lo=tlo[-1], w=tw[-1], rh=trh[-1], sig=tsig[-1])
t["pb"] = (t["c"] - t["lo"]) / (t["u"] - t["lo"])
t["clusters"] = green_clusters(tr, tsig)
t["last_green"] = next((ym(tr[i][0]) for i in range(len(tsig) - 1, -1, -1) if tsig[i]), None)
if t["sig"]:
    t_pill, t_cls, t_line = "공포 구간", "p-turn", "월봉 Vix Fix 투매 신호가 켜졌습니다. 이 지표 기준으로는 과거 다음 상승의 출발점이 됐던 자리입니다. 추세는 약하니 분할로 접근할 구간입니다."
elif t["pb"] >= 0.8 and t["w"] < t["rh"] * 0.3:
    t_pill, t_cls, t_line = "과열권", "p-hot", "월봉 BB 상단 근처이고 Vix Fix는 바닥(공포 없음)입니다. 추세는 강하지만 새로 사기엔 유리한 자리가 아니고, 보유 중이면 지킬 선을 정해둘 구간입니다."
elif t["c"] < t["m"]:
    t_pill, t_cls, t_line = "추세 이탈 경계", "p-mix", "월봉 BB 중심선 아래로 내려왔습니다. 강세장 조정 범위를 벗어나는 중이라 비중 관리가 우선입니다."
else:
    t_pill, t_cls, t_line = "상승 추세", "p-mix", "월봉 BB 중심선 위에서 상승 추세가 유지되고 있습니다. 과열 신호는 아직 강하지 않습니다."

# ───────── MSTR 월봉·일봉 ─────────
mr, mh, ml, mc = cols("MSTR_1mo", "1mo")
mm, mu, mlo = bb(mc); mrs = rsi(mc); mw, _, mrh, msig = vixfix(mh, ml, mc)
m = dict(c=mc[-1], prev=mc[-2], m=mm[-1], u=mu[-1], lo=mlo[-1], rsi=mrs[-1], rsi_prev=mrs[-2], w=mw[-1], rh=mrh[-1], sig=msig[-1])
m["pb"] = (m["c"] - m["lo"]) / (m["u"] - m["lo"])
m["g12"] = sum(msig[-12:])
m["clusters"] = green_clusters(mr, msig)
ath_i = max(range(len(mh)), key=lambda i: mh[i]); m["ath"], m["ath_d"] = mh[ath_i], ymd(mr[ath_i][0])
dr, dh, dl, dc = cols("MSTR_1d", "1d")
have_d = len(dc) > 220
if have_d:
    ma218 = sma(dc, 218)[-1]; env = ma218 * 1.07; ma200 = sma(dc, 200)[-1]
    disp = dc[-1] / ma200 * 100
    disp_min = min(x / y * 100 for x, y in zip(dc[-250:], sma(dc, 200)[-250:]) if y)
    low_i = min(range(max(0, len(dl) - 400), len(dl)), key=lambda i: dl[i])
    cyc_low, cyc_low_d = dl[low_i], ymd(dr[low_i][0])
    swing_hi = max(dh[-120:])
    m["c"] = dc[-1]  # 일봉 종가가 가장 최신
    di = max(range(len(dh)), key=lambda i: dh[i])
    if dh[di] >= m["ath"] - 0.01: m["ath"], m["ath_d"] = dh[di], ymd(dr[di][0])
else:
    ma218 = env = disp = disp_min = swing_hi = None
    low_i = min(range(len(ml) - 18, len(ml)), key=lambda i: ml[i]); cyc_low, cyc_low_d = ml[low_i], ym(mr[low_i][0])
c = m["c"]
above218 = have_d and c > ma218
if c > m["m"]:
    m_pill, m_cls, m_line = "추세 전환 확인", "p-turn", "월봉 BB 중심선 위로 올라섰습니다. 하락 추세 안의 반등을 넘어 추세 전환 쪽으로 무게가 실립니다."
elif m["g12"] >= 3 and above218:
    m_pill, m_cls, m_line = "바닥 신호 출현", "p-turn", "월봉 Vix Fix 녹색 군집(투매)이 나왔고, 일봉 218일선도 회복했습니다. 다만 월봉 BB 중심선 아래라 아직 \"하락 추세 안의 반등\"입니다."
elif m["g12"] >= 3:
    m_pill, m_cls, m_line = "바닥 다지기", "p-mix", "최근 1년 안에 월봉 Vix Fix 투매 신호가 나왔지만 일봉 218일선 아래입니다. 바닥 확인 전 단계입니다."
elif have_d and c < ma218 and m["rsi"] < 45:
    m_pill, m_cls, m_line = "하락 추세", "p-hot", "일봉 218일선 아래, 월봉 RSI 45 미만입니다. 추세가 아래쪽입니다."
else:
    m_pill, m_cls, m_line = "중립", "p-mix", "뚜렷한 바닥·전환 신호 없이 중간 지대에 있습니다."

# ───────── NDX · BTC · M2 ─────────
nr, nh, nl, nc = cols("NDX_1mo", "1mo")
n_rsi = rsi(nc)[-1] if len(nc) > 20 else None
nw = cols("NDX_1wk", "1wk")[3]; n_c = nw[-1] if nw else (nc[-1] if nc else None)
if n_rsi is None: n_pill, n_cls, n_line = "데이터 없음", "p-mix", "NDX 월봉 데이터를 받지 못했습니다."
elif n_rsi >= 70: n_pill, n_cls, n_line = "고점 경계", "p-mix", f"월봉 RSI {n_rsi:.0f}로 과매수입니다. 추세는 살아 있지만 TQQQ 3배 레버리지에 그대로 증폭되는 위험입니다."
elif n_rsi >= 50: n_pill, n_cls, n_line = "상승 추세", "p-turn", f"월봉 RSI {n_rsi:.0f}로 상승 모멘텀 구간입니다. 과매수는 아닙니다."
else: n_pill, n_cls, n_line = "약세", "p-hot", f"월봉 RSI {n_rsi:.0f}로 50 아래입니다. 지수 모멘텀이 꺾였습니다."
br, bh, bl, bc = cols("BTC_1mo", "1mo")
btc = dict(c=bc[-1], prev=bc[-2], rsi=rsi(bc)[-1]) if len(bc) > 20 else None
M2 = D.get("m2", {}); m2r = M2.get("rows", [])
if len(m2r) >= 4:
    m2_last, m2_3m = m2r[-1], m2r[-4]
    m2_dir = "상승" if m2_last[1] > m2_3m[1] * 1.003 else ("하락" if m2_last[1] < m2_3m[1] * 0.997 else "횡보")
else:
    m2_last = m2_dir = None

# ───────── HTML ─────────
now = datetime.now(KST)
upd = datetime.fromisoformat(D["updated"]).astimezone(KST)

def gauge(label, val_txt, pos, caps, ticks=(), vix=False):
    tk = "".join(f'<span class="tick" style="left:{x}%"></span>' for x in ticks)
    cp = "".join(f"<span>{x}</span>" for x in caps)
    return f'''<div class="g"><div class="g-top"><span>{label}</span><span>{val_txt}</span></div>
<div class="track{' vix' if vix else ''}">{tk}<span class="mark" style="left:{clamp(pos):.1f}%"></span></div><div class="g-cap">{cp}</div></div>'''

def row(name, price, cur, note, d=2):
    if price is None: return ""
    p = pct(price, cur)
    return f'<tr><td>{name}</td><td class="r">{f(price, d)}</td><td class="r {"up" if p >= 0 else "dn"}">{p:+.1f}%</td><td>{note}</td></tr>'

# TQQQ 해석
t_read = []
if t["clusters"]:
    t_read.append(f"<b>월봉 Vix Fix 녹색 구간</b>은 과거 {', '.join(t['clusters'][-3:])}에 시작됐습니다. " +
                  ("지금 그 신호가 켜져 있습니다. 이 지표 기준으로는 공포가 큰 \"살 자리\" 후보입니다." if t["sig"] else
                   (f"마지막 녹색 달은 {t['last_green']}입니다. " if t["last_green"] and t["last_green"] not in t["clusters"] else "") + f"지금 Vix Fix는 {t['w']:.1f}로 기준선 {t['rh']:.1f}의 {t['w']/t['rh']*100:.0f}% 수준입니다. " +
                   ("공포가 거의 없는 상태라 이 지표로는 \"조심할 때\"에 가깝습니다." if t["w"] < t["rh"] * 0.3 else "공포가 조금씩 올라오는 중입니다.")))
up_d, mid_d = pct(t["u"], t["c"]), pct(t["m"], t["c"])
t_read.append(f"<b>위로 남은 거리 {up_d:+.0f}%, 아래 BB 중심선까지 {mid_d:+.0f}%.</b> " +
              ("손익비가 불리한 자리입니다. " if up_d < abs(mid_d) / 2 else "") + "3배 레버리지는 나스닥이 −10%만 빠져도 대략 −30% 가까이 움직입니다.")
if t["c"] > t["u"]:
    t_read.append("<b>월봉 BB 상단 위에 있습니다.</b> \"밴드 워킹\"은 몇 달씩 이어지기도 해서 과열이 곧 하락을 뜻하지는 않습니다. 월말 종가가 상단 위에 남는지가 관건입니다.")
elif t["pb"] >= 0.8:
    t_read.append("<b>추세 자체는 상승입니다.</b> 월봉 BB 상단을 타고 오르는 흐름은 몇 달씩 이어지기도 합니다. 과열이 곧바로 하락을 뜻하지는 않습니다.")

# MSTR 해석
m_read = []
if m["g12"] >= 3:
    m_read.append(f"<b>최근 12개월 중 {m['g12']}개월이 월봉 Vix Fix 녹색(투매)</b>이었습니다. 과거 녹색 군집은 {', '.join(m['clusters'][-3:])}에 시작됐고, 2022년 군집 뒤에는 바닥을 잡고 2023~24년 대세 상승으로 갔습니다. " +
                  ("이번 달은 아직 녹색입니다. 공포가 진행 중입니다." if m["sig"] else "이번 달은 기준선 아래(빨강)로, 공포가 빠지기 시작했다는 뜻입니다."))
if have_d:
    m_read.append(f"<b>일봉 218일선 {f(ma218)} / +7% 엔벨로프 {f(env)}.</b> 현재가는 " +
                  ("218일선 위" + (", 엔벨로프 상단까지 넘어선 상태" if c > env else "") + "입니다. " if above218 else "218일선 아래입니다. ") +
                  f"이격도(200)는 {disp:.0f}" + (f" (최근 1년 최저 {disp_min:.0f})" if disp_min else "") + ". 과열선 160, 과매도 50 기준입니다.")
rsi_dir = "반등 중" if m["rsi"] > m["rsi_prev"] else "하락 중"
m_read.append(f"<b>월봉 RSI {m['rsi']:.1f}, 전월 {m['rsi_prev']:.1f}에서 {rsi_dir}.</b> " +
              ("50 위라 월봉 모멘텀은 상승 쪽입니다." if m["rsi"] >= 50 else "50을 넘으면 월봉 모멘텀이 상승 쪽으로 넘어갑니다."))
if m2_last and m2_dir:
    m_read.append(f"<b>Global M2는 최근 3개월 {m2_dir}</b> (${m2_last[1]:.1f}조, {m2_last[0][:7]}, {'+'.join(M2.get('countries', []))}). MSTR은 고점 대비 {pct(c, m['ath']):.0f}%로, " +
                  ("M2와 괴리가 큽니다. \"유동성 따라잡기\" 기대와 \"비트코인·프리미엄(mNAV) 축소가 더 크게 작용한다\"는 해석이 공존합니다." if pct(c, m["ath"]) < -40 else "M2와 같은 방향입니다."))
if btc:
    m_read.append(f"<b>비트코인 월봉 {f(btc['c'], 0)}달러, 이번 달 {pct(btc['c'], btc['prev']):+.1f}%, RSI {btc['rsi']:.0f}.</b> MSTR은 비트코인의 레버리지 성격이라 BTC가 꺾이면 위 신호들이 쉽게 무효가 됩니다. BTC 대비 프리미엄(mNAV)은 이 페이지에 없으니 따로 확인하세요.")

css = open(os.path.join(os.path.dirname(__file__), "report.css")).read()
html = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>MSTR · TQQQ 기술적 점검</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>{css}</style></head><body><div class="wrap">
<header><span class="eyebrow">{now:%Y.%m.%d %H:%M} 자동 생성 · 시세 {upd:%m.%d %H:%M} KST 기준 · <a href="./">차트 보기</a></span>
<h1>MSTR · TQQQ 기술적 점검</h1></header>

<div class="bl"><h3>한 줄 판단</h3>
<div class="bl-row"><span class="tag">TQQQ</span><p><span class="pill {t_cls}">{t_pill}</span>{t_line}</p></div>
<div class="bl-row"><span class="tag">MSTR</span><p><span class="pill {m_cls}">{m_pill}</span>{m_line}</p></div>
<div class="bl-row"><span class="tag">NDX</span><p><span class="pill {n_cls}">{n_pill}</span>{n_line}</p></div></div>

<section class="card"><h2>TQQQ <span class="px">{f(t["c"])}</span><span class="eyebrow">월봉 · 이번 달 {pct(t["c"], t["prev"]):+.1f}%</span></h2>
<div class="gauges">
{gauge("BB 20/2 안의 위치 (%b)", f"{t['pb']:.2f}", t["pb"] * 100, [f"하단 {f(t['lo'])}", f"중심 {f(t['m'])}", f"상단 {f(t['u'])}"], ticks=(50,))}
{gauge("Williams Vix Fix (공포 지수)", f"{t['w']:.2f} / 기준 {t['rh']:.2f}" + (' <b class="on">신호 ON</b>' if t["sig"] else ""), t["w"] / max(t["rh"] / 0.85, 1) * 100, ["0 무관심", f"{t['rh']:.1f} 이상 = 투매 신호"], ticks=(85,), vix=True)}
</div>
<div class="levels"><table><thead><tr><th>가격대</th><th class="r">가격</th><th class="r">현재가 대비</th><th>의미</th></tr></thead><tbody>
{row("월봉 BB 상단", t["u"], t["c"], "추세가 이어질 때 1차 저항")}
<tr><td>현재가</td><td class="r">{f(t["c"])}</td><td class="r">—</td><td></td></tr>
{row("월봉 BB 중심", t["m"], t["c"], "강세장 조정의 통상적인 도착점")}
{row("월봉 BB 하단", t["lo"], t["c"], "2022년형 약세장 시나리오")}
</tbody></table></div>
<div class="read">{"".join(f"<p>{x}</p>" for x in t_read)}</div>
<div class="sc">
<div><span class="h b">상승 지속</span><span>월봉 종가가 BB 상단({f(t["u"], 0)}) 위에서 마감 → 밴드 워킹. 보유분은 추세 추종, 신규는 분할로만.</span></div>
<div><span class="h n">횡보·조정</span><span>BB 중심({f(t["m"], 0)})까지는 강세장 안의 정상 조정 범위.</span></div>
<div><span class="h s">추세 이탈</span><span>월봉 종가가 BB 중심 아래 + Vix Fix 녹색 전환. 2022년형. 대신 그 녹색 신호가 역사적으로 다음 매수 자리였습니다.</span></div>
</div></section>

<section class="card"><h2>MSTR <span class="px">{f(c)}</span><span class="eyebrow">월봉 · 일봉 · 이번 달 {pct(mc[-1], m["prev"]):+.1f}%</span></h2>
<div class="gauges">
{gauge("월봉 BB 20/2 안의 위치 (%b)", f"{m['pb']:.2f}", m["pb"] * 100, [f"하단 {f(m['lo'])}", f"중심 {f(m['m'])}", f"상단 {f(m['u'])}"], ticks=(50,))}
{gauge("월봉 RSI 14", f"{m['rsi']:.2f}", m["rsi"], ["0", "30", "50", "70", "100"], ticks=(30, 70))}
{gauge("월봉 Williams Vix Fix", f"{m['w']:.2f} / 기준 {m['rh']:.2f}" + (' <b class="on">신호 ON</b>' if m["sig"] else ""), m["w"] / max(m["rh"] / 0.85, 1) * 100, ["0", f"최근 12개월 녹색 {m['g12']}개월"], ticks=(85,), vix=True)}
</div>
<div class="levels"><table><thead><tr><th>가격대</th><th class="r">가격</th><th class="r">현재가 대비</th><th>의미</th></tr></thead><tbody>
{row(f"사상 최고가 ({m['ath_d']})", m["ath"], c, f"현재 고점 대비 {pct(c, m['ath']):.0f}%")}
{row("월봉 BB 중심", m["m"], c, "추세 전환을 확인하는 선. 여기 위 월봉 마감이 핵심")}
{row("최근 120일 고점", swing_hi, c, "직전 스윙 고점. 1차 저항") if swing_hi and swing_hi > c else ""}
<tr><td>현재가</td><td class="r">{f(c)}</td><td class="r">—</td><td></td></tr>
{row("일봉 +7% 엔벨로프", env, c, "218일선 위 7% 띠. 이 위에서 버티면 추세 강화") if env else ""}
{row("일봉 218일선", ma218, c, "장기 추세선. " + ("깨지면 반등 실패 신호" if above218 else "회복해야 바닥 확인")) if ma218 else ""}
{row(f"최근 저점 ({cyc_low_d})", cyc_low, c, "바닥 신호가 무효가 되는 선")}
</tbody></table></div>
<div class="read">{"".join(f"<p>{x}</p>" for x in m_read)}</div>
<div class="sc">
<div><span class="h b">추세 전환</span><span>{"218일선 지지 유지 → " if above218 else "218일선 회복 → "}{f(swing_hi, 0) if swing_hi else "직전 고점"} 돌파 → 월봉 BB 중심 {f(m["m"], 0)} 위 마감. RSI 50 돌파가 선행 신호.</span></div>
<div><span class="h n">박스권</span><span>{f(ma218, 0) if ma218 else "—"}~{f(swing_hi, 0) if swing_hi else "—"} 사이 등락. Vix Fix가 식으면서 바닥 다지기.</span></div>
<div><span class="h s">반등 실패</span><span>일봉 218일선 아래 안착 후 저점 {f(cyc_low)} 재시험. 이 저점이 깨지면 바닥 판단 자체가 무효.</span></div>
</div></section>

<section class="card"><h2>NDX · Global M2 <span class="px">{f(n_c) if n_c else "—"}</span><span class="eyebrow">월봉 RSI {f(n_rsi) if n_rsi else "—"}</span></h2>
<div class="read">
<p><b>NDX 월봉 RSI {f(n_rsi, 1) if n_rsi else "—"}.</b> {"70 위는 과매수입니다. \"곧 하락\"이 아니라 \"새로 들어가기엔 비싼 구간\"으로 읽는 편이 맞습니다." if n_rsi and n_rsi >= 70 else "과매수(70)는 아닙니다."}</p>
<p><b>Global M2 최근 3개월 {m2_dir or "—"}.</b> NDX는 2025~2026년 M2를 거의 그대로 따라 올랐습니다. {"M2가 꺾이면 지수 상승 동력이 약해질 수 있습니다." if m2_dir != "상승" else "M2가 계속 오르는 동안은 지수에 우호적입니다."}</p>
<p><b>금리.</b> FOMC 인하 확률이 높게 유지되면 M2·나스닥에 우호적이고, 확률이 급히 내려가면 과매수 상태의 TQQQ가 가장 먼저 흔들립니다. <a href="https://www.cmegroup.com/ko/markets/interest-rates/cme-fedwatch-tool.html">CME FedWatch</a>는 회의 2주 전부터 확인하세요.</p>
</div></section>

<section class="card"><h2>매일 볼 것</h2><ol class="check">
{f'<li>MSTR 일봉이 <span class="num">{f(ma218, 0)}~{f(env, 0)}</span>(218일선·엔벨로프) 위에서 버티는지</li>' if ma218 else ""}
{f'<li>MSTR <span class="num">{f(swing_hi, 0)}</span> 돌파 여부, 월말엔 월봉 종가가 <span class="num">{f(m["m"], 0)}</span>(BB 중심) 근처인지</li>' if swing_hi else ""}
<li>MSTR 월봉 RSI가 <span class="num">50</span>을 넘는지 (현재 {m["rsi"]:.1f})</li>
<li>TQQQ 월봉 Vix Fix가 녹색으로 바뀌는지 (현재 {t["w"]:.1f} / {t["rh"]:.1f})</li>
<li>TQQQ가 <span class="num">{f(t["u"], 0)}</span> 위로 마감하는지, <span class="num">{f(t["m"], 0)}</span> 쪽으로 밀리는지</li>
<li>Global M2 방향, FedWatch 다음 회의 인하 확률</li>
</ol></section>

<p class="fine">매일 Yahoo Finance·FRED·ECB 데이터로 TradingView와 같은 공식(BB 20/2, RSI 14, CM Williams Vix Fix 22/20/2/50/0.85, SMA 218 ±7%, 이격도 200)을 계산해 자동으로 쓰는 기술적 해석이며, 투자 자문이 아닙니다. 매매 시점과 비중은 본인의 자금 상황과 위험 감내도에 맞춰 직접 판단하세요. 진행 중인 월봉은 월말까지 값이 계속 바뀝니다.</p>
</div></body></html>'''
open("report.html", "w").write(html)
print("report.html", len(html), "bytes |", t_pill, "/", m_pill, "/", n_pill)
