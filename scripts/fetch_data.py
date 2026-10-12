"""매일 시세·M2를 받아 data.json으로 저장 (GitHub Actions에서 실행)."""
import csv, io, json, time, urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

LOG = []
def get(url, tries=2, uas=(UA, {"User-Agent": "curl/8.5.0"}, {"User-Agent": "python-requests/2.32"})):
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

def global_m2():
    parts = [("M2SL", 1e9, None, False), ("MYAGM2EZM196N", 1e6, "EXUSEU", False),
             ("MYAGM2CNM189N", 1, "EXCHUS", True), ("MYAGM2JPM189N", 1, "EXJPUS", True)]
    series = []
    for sid, mul, fx, inv in parts:
        try:
            m = fred(sid)
            f = fred(fx) if fx else None
            s, last = {}, None
            for k in sorted(m):
                rate = 1
                if f is not None:
                    rate = f.get(k, last)
                    if rate is None:
                        continue
                    last = rate
                s[k] = m[k] * mul * (1 / rate if inv else rate)
            series.append(s)
        except Exception as e:
            LOG.append(f"M2 skip {sid}: {e}")
    if not series:
        return {"rows": [], "n": 0}
    months = sorted(k for k in series[0] if all(k in s for s in series))
    return {"rows": [[k + "-01", round(sum(s[k] for s in series) / 1e12, 3)] for k in months], "n": len(series)}

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
print("M2 rows", len(data["m2"]["rows"]), "countries", data["m2"]["n"])
if len(data["ohlc"]) < 4:
    raise SystemExit("일부 시세를 받지 못함 — 기존 data.json 유지")
with open("data.json", "w") as f:
    json.dump(data, f, separators=(",", ":"))
