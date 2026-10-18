"""TradingView 'Global M2 Money Supply' 지표와 같은 방식으로 계산.
TradingView ECONOMICS 데이터(각국 M2) × FX_IDC 환율 → 달러 합계(조). 웹소켓(비로그인)으로 받음."""
import json, random, re, string, time
from datetime import datetime, timezone
from websocket import create_connection

# TradingView 공개 지표(Global M2 Money Supply)의 나라 구성
COUNTRIES = [("US", "ECONOMICS:USM2", None), ("EU", "ECONOMICS:EUM2", "FX_IDC:EURUSD"), ("CN", "ECONOMICS:CNM2", "FX_IDC:CNYUSD"),
    ("JP", "ECONOMICS:JPM2", "FX_IDC:JPYUSD"), ("GB", "ECONOMICS:GBM2", "FX_IDC:GBPUSD"), ("CA", "ECONOMICS:CAM2", "FX_IDC:CADUSD"),
    ("AU", "ECONOMICS:AUM3", "FX_IDC:AUDUSD"), ("IN", "ECONOMICS:INM2", "FX_IDC:INRUSD"), ("CH", "ECONOMICS:CHM2", "FX_IDC:CHFUSD"),
    ("RU", "ECONOMICS:RUM2", "FX_IDC:RUBUSD"), ("BR", "ECONOMICS:BRM2", "FX_IDC:BRLUSD"), ("KR", "ECONOMICS:KRM2", "FX_IDC:KRWUSD"),
    ("MX", "ECONOMICS:MXM2", "FX_IDC:MXNUSD"), ("ID", "ECONOMICS:IDM2", "FX_IDC:IDRUSD"), ("ZA", "ECONOMICS:ZAM2", "FX_IDC:ZARUSD"),
    ("MY", "ECONOMICS:MYM2", "FX_IDC:MYRUSD"), ("SE", "ECONOMICS:SEM2", "FX_IDC:SEKUSD")]

def _rid(p): return p + "".join(random.choice(string.ascii_lowercase) for _ in range(12))
def _msg(f, a):
    s = json.dumps({"m": f, "p": a}, separators=(",", ":")); return f"~m~{len(s)}~m~{s}"

def bars(symbol, interval="1D", n=3000):
    ws = create_connection("wss://data.tradingview.com/socket.io/websocket",
                           header={"Origin": "https://data.tradingview.com"}, timeout=20)
    cs = _rid("cs_")
    for f, a in (("set_auth_token", ["unauthorized_user_token"]), ("chart_create_session", [cs, ""]),
                 ("resolve_symbol", [cs, "sym", '={"symbol":"%s","adjustment":"splits"}' % symbol]),
                 ("create_series", [cs, "s1", "s1", "sym", interval, n])):
        ws.send(_msg(f, a))
    raw, t0 = "", time.time()
    while time.time() - t0 < 30:
        r = ws.recv()
        if re.match(r"~m~\d+~m~~h~", r): ws.send(r); continue      # heartbeat
        raw += r
        if "series_completed" in r or "symbol_error" in r or "series_error" in r: break
    ws.close()
    m = re.search(r'"s":\[(.*?\])\]', raw)
    if not m: raise ValueError(f"{symbol} 데이터 없음 ({raw[-160:]})")
    out = {}
    for b in json.loads("[" + m.group(1) + "]"):
        v = b["v"]; out[datetime.fromtimestamp(v[0], timezone.utc).strftime("%Y-%m-%d")] = v[4]
    return out

def global_m2(log=print):
    series, used = [], []
    for name, m2s, fx in COUNTRIES:
        try:
            m = bars(m2s); f = bars(fx) if fx else None
            series.append((name, m, f)); used.append(name)
            log(f"TV {name} ok {min(m)}~{max(m)} n={len(m)}")
        except Exception as e:
            log(f"TV {name} fail {type(e).__name__}: {str(e)[:120]}")
    if "US" not in used or "CN" not in used or len(used) < 10:
        raise RuntimeError(f"TradingView M2 부족: {used}")
    days = sorted(d for d in set().union(*[set(f) for _, _, f in series if f]) if d >= "2016-01-01")
    rows, last = [], {}
    for d in days:
        tot, ok = 0.0, True
        for name, m, f in series:
            for key, src in ((name + "m", m), (name + "f", f)):
                if src is None: continue
                if d in src: last[key] = src[d]
                elif key not in last:
                    ks = [k for k in src if k <= d]
                    if ks: last[key] = src[max(ks)]
            if (name + "m") not in last or (f is not None and (name + "f") not in last): ok = False; break
            tot += last[name + "m"] * (last[name + "f"] if f is not None else 1)
        if ok: rows.append([d, round(tot / 1e12, 3)])
    return {"rows": rows, "n": len(used), "countries": used, "notes": ["TradingView ECONOMICS 데이터 (Global M2 Money Supply 지표와 같은 구성)"], "freq": "daily", "src": "tradingview"}

if __name__ == "__main__":
    r = global_m2(); print(r["countries"], r["rows"][-3:])
