"""매일 시세·M2를 받아 data.json으로 저장 (GitHub Actions에서 실행)."""
import csv, io, json, time, urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

LOG = []
def get(url, tries=2, uas=({"User-Agent": "curl/8.5.0"}, UA)):
    last = None
    for ua in uas:
        for i in range(tries):
            t0 = time.time()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=20) as r:
                    return r.read().decode()
            except Exception as e:
                last = e
                LOG.append(f"{url[:70]} ua={ua['User-Agent'][:12]} {type(e).__name__}:{e} {time.time()-t0:.0f}s")
                time.sleep(2)
    raise last

def yahoo(sym, iv):
    j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={"10y" if iv=="1wk" else "max"}&interval={iv}"))
    res = j["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(res["timestamp"]):
        if q["close"][i] is None:
            continue
        out.append([t, *(round(q[k][i], 4) if q[k][i] is not None else q["close"][i] for k in ("open", "high", "low", "close"))])
    return out  # [unix, o, h, l, c]

def fred(sid):
    rows = list(csv.reader(io.StringIO(get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"))))[1:]
    return {d[:7]: float(v) for d, v in rows if v not in (".", "")}

def ecb_m2():
    txt = get("https://data-api.ecb.europa.eu/service/data/BSI/M.U2.Y.V.M20.X.1.U2.2300.Z01.E?format=csvdata&startPeriod=2010-01")
    r = list(csv.DictReader(io.StringIO(txt)))
    return {x["TIME_PERIOD"][:7]: float(x["OBS_VALUE"]) for x in r if x.get("OBS_VALUE")}

def add_months(k, n):
    y, m = int(k[:4]), int(k[5:7]) + n
    y += (m - 1) // 12; m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"

def global_m2():
    # (이름, 후보 [(로더, 단위배수)], 환율 FRED id, 환율 나눗셈 여부)
    countries = [
        ("US", [(lambda: fred("M2SL"), 1e9)], None, False),
        ("EU", [(ecb_m2, 1e6), (lambda: fred("MABMM301EZM189S"), 1)], "EXUSEU", False),
        ("CN", [(lambda: fred("MABMM301CNM189S"), 1), (lambda: fred("MYAGM2CNM189N"), 1)], "EXCHUS", True),
        ("JP", [(lambda: fred("MABMM301JPM189S"), 1), (lambda: fred("MYAGM2JPM189N"), 1)], "EXJPUS", True),
    ]
    now = datetime.now(timezone.utc).strftime("%Y-%m")
    series, used = [], []
    for name, cands, fx, inv in countries:
        for loader, mul in cands:
            try:
                m = loader()
                last = max(m)
                LOG.append(f"M2 {name} last={last} n={len(m)}")
                if last < add_months(now, -9):   # 9개월 넘게 발표 없으면 끊긴 시리즈로 보고 제외
                    continue
                f = fred(fx) if fx else None
                s, lr = {}, None
                for k in sorted(m):
                    rate = 1
                    if f is not None:
                        rate = f.get(k, lr)
                        if rate is None:
                            continue
                        lr = rate
                    s[k] = m[k] * mul * (1 / rate if inv else rate)
                series.append(s); used.append(name)
                break
            except Exception as e:
                LOG.append(f"M2 {name} fail: {e}")
    if not series:
        return {"rows": [], "n": 0, "countries": []}
    first = max(min(s) for s in series)
    last = min(add_months(max(s), 2) for s in series)   # 발표 늦은 나라는 최대 2개월 직전값 유지
    last = min(last, max(max(s) for s in series))
    rows, k = [], first
    prev = [None] * len(series)
    while k <= last:
        vals = []
        for i, s in enumerate(series):
            if k in s: prev[i] = s[k]
            vals.append(prev[i])
        if all(v is not None for v in vals):
            rows.append([k + "-01", round(sum(vals) / 1e12, 3)])
        k = add_months(k, 1)
    return {"rows": rows, "n": len(series), "countries": used}

data = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "ohlc": {}}
for key, sym, iv in [("TQQQ_1mo", "TQQQ", "1mo"), ("MSTR_1wk", "MSTR", "1wk"),
                     ("MSTR_1mo", "MSTR", "1mo"), ("NDX_1wk", "%5ENDX", "1wk")]:
    try:
        data["ohlc"][key] = yahoo(sym, iv)
        print(key, len(data["ohlc"][key]))
    except Exception as e:
        print("FAIL", key, e)
data["m2"] = global_m2()
data["log"] = LOG[-20:]
print("M2 rows", len(data["m2"]["rows"]), data["m2"]["countries"])
if len(data["ohlc"]) < 4:
    raise SystemExit("일부 시세를 받지 못함 — 기존 data.json 유지")
with open("data.json", "w") as f:
    json.dump(data, f, separators=(",", ":"))
