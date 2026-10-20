"""MSTR 매수 타이밍 조건 점검 → 새로 충족되면 GitHub 이슈(=GitHub 앱 푸시 알림) 생성.

조건이 '꺼짐 → 켜짐'으로 바뀔 때만 알림. 같은 알림은 5일 안에 다시 보내지 않음.
결과는 alerts.json(페이지 표시용), alerts_state.json(직전 상태)에 저장.
"""
import json, os, sys, urllib.request
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from indicators import sma, bb, rsi, vixfix

KST = timezone(timedelta(hours=9))
D = json.load(open("data.json"))
O = D["ohlc"]
def col(key, i): return [x[i] for x in O[key]]

dc = col("MSTR_1d", 4)
mh, ml, mc = col("MSTR_1mo", 2), col("MSTR_1mo", 3), col("MSTR_1mo", 4)
c = dc[-1]
ma218 = sma(dc, 218)[-1]   # 218일선 (변수명은 알림 상태 유지를 위해 그대로)
env = ma218 * 1.07          # 218일선 +7% 엔벨로프
disp = c / sma(dc, 200)[-1] * 100
bmid = bb(mc)[0][-1]
mrsi = rsi(mc)[-1]
w, _, rh, sig = vixfix(mh, ml, mc)
vix_recent = sum(sig[-12:])

# (id, 종류, 이름, 충족 여부, 현재값 설명)
CONDS = [
    ("vix_on",   "buy",  "월봉 Vix Fix 투매 신호 점등",      sig[-1],          f"Vix Fix {w[-1]:.1f} / 기준 {rh[-1]:.1f}"),
    ("disp_50",  "buy",  "이격도(200) 50 이하 — 과매도",      disp <= 50,       f"이격도 {disp:.1f}"),
    ("above218", "buy",  "218일선 위로 회복",                 c > ma218,        f"{c:.2f} vs 218일선 {ma218:.2f}"),
    ("above_env","buy",  "218일선 +7% 엔벨로프 돌파",          c > env,          f"{c:.2f} vs 엔벨로프 {env:.2f}"),
    ("rsi50",    "buy",  "월봉 RSI 50 돌파",                  mrsi >= 50,       f"월봉 RSI {mrsi:.1f}"),
    ("bbmid",    "buy",  "월봉 BB 중심선 돌파 (추세 전환)",    c > bmid,         f"{c:.2f} vs BB 중심 {bmid:.2f}"),
    ("disp_160", "warn", "이격도(200) 160 이상 — 과열 경고",   disp >= 160,      f"이격도 {disp:.1f}"),
    ("below218", "warn", "218일선 이탈 — 반등 실패 경고",      c < ma218,        f"{c:.2f} vs 218일선 {ma218:.2f}"),
]
buy_on = [x for x in CONDS if x[1] == "buy" and x[3]]
score = len(buy_on)
# 단계: 투매(바닥 후보) → 회복 → 전환
if c > bmid and mrsi >= 50:
    stage, stage_txt = "전환", "추세 전환 확인 구간 — 월봉 BB 중심선과 RSI 50을 모두 넘었습니다."
elif (vix_recent >= 3 or disp <= 50) and c > ma218:
    stage, stage_txt = "회복", "투매 신호 이후 218일선을 회복한 구간 — 분할 매수 검토 구간입니다."
elif sig[-1] or disp <= 50:
    stage, stage_txt = "투매", "공포(투매) 구간 — 역사적으로 바닥 후보였던 자리입니다. 218일선 회복 확인 전입니다."
elif disp >= 160:
    stage, stage_txt = "과열", "과열 구간 — 신규 매수에 불리한 자리입니다."
else:
    stage, stage_txt = "관망", "뚜렷한 매수 조건이 겹치지 않은 구간입니다."

state_path = "alerts_state.json"
state = json.load(open(state_path)) if os.path.exists(state_path) else None
first_run = state is None
state = state or {"on": {}, "sent": {}, "stage": None}
now = datetime.now(timezone.utc)
new_alerts = []
for cid, kind, name, on, val in CONDS:
    was = state["on"].get(cid, False)
    last = state["sent"].get(cid)
    cool = last and (now - datetime.fromisoformat(last)) < timedelta(days=5)
    if on and not was and not first_run and not cool:
        new_alerts.append((cid, kind, name, val))
        state["sent"][cid] = now.isoformat(timespec="minutes")
    state["on"][cid] = bool(on)
stage_changed = state.get("stage") not in (None, stage)
state["stage"] = stage

def issue(title, body):
    tok, repo = os.environ.get("GH_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not tok or not repo:
        print("토큰 없음 — 알림 생략:", title); return
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/issues", method="POST",
        data=json.dumps({"title": title, "body": body}).encode(),
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "User-Agent": "mstr-alerts"})
    with urllib.request.urlopen(req, timeout=30) as r:
        print("이슈 생성:", json.loads(r.read())["html_url"])

site = "https://yoyopayoyopa1234-coder.github.io/dashboard/report.html"
status_lines = "\n".join(f"- {'✅' if on else '⬜'} {name} — {val}" for _, kind, name, on, val in CONDS if kind == "buy")
warn_lines = "\n".join(f"- {'⚠️' if on else '⬜'} {name} — {val}" for _, kind, name, on, val in CONDS if kind == "warn")
body_tail = (f"\n\n**현재 단계: {stage}** — {stage_txt}\n\n매수 조건 {score}/6 충족\n{status_lines}\n\n경고\n{warn_lines}\n\n"
             f"[오늘 분석 보기]({site})\n\n@yoyopayoyopa1234-coder\n\n_지표 조건 충족 알림이며 투자 자문이 아닙니다._")
ts = now.astimezone(KST).strftime("%m/%d %H:%M")
if first_run:
    issue(f"[MSTR] 알림 설정 완료 · 현재 {stage} 단계 ({score}/6)", f"매수 타이밍 알림이 켜졌습니다. 아래 조건이 새로 충족되면 이렇게 알림이 옵니다.{body_tail}")
for cid, kind, name, val in new_alerts:
    icon = "🟢" if kind == "buy" else "⚠️"
    issue(f"{icon} [MSTR {c:.2f}] {name} ({ts})", f"**{name}** 조건이 새로 충족됐습니다. ({val}){body_tail}")
if stage_changed and not new_alerts:
    issue(f"[MSTR {c:.2f}] 단계 변경 → {stage} ({ts})", f"매수 타이밍 단계가 **{stage}**(으)로 바뀌었습니다.{body_tail}")

json.dump(state, open(state_path, "w"), ensure_ascii=False, indent=1)
out = {"at": now.isoformat(timespec="minutes"), "price": round(c, 2), "stage": stage, "stage_txt": stage_txt, "score": score,
       "conds": [{"id": a, "kind": b, "name": n, "on": bool(o), "val": v} for a, b, n, o, v in CONDS],
       "sent": state["sent"]}
json.dump(out, open("alerts.json", "w"), ensure_ascii=False, indent=1)
print("단계", stage, "점수", score, "새 알림", [a[0] for a in new_alerts])
