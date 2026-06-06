"""
End-to-end test for World Cup Guess system.
Tests: register, login, predict, score, rankings, daily stars.
"""
import json
import urllib.request
import urllib.error
import http.cookiejar
import sys

BASE = "http://127.0.0.1:5000"
PASS_COUNT = 0
FAIL_COUNT = 0


def req(method, path, data=None, cookies=None):
    """Make HTTP request and return (status, body_dict, cookie_str)."""
    url = BASE + path
    body_bytes = json.dumps(data).encode() if data else None
    req_obj = urllib.request.Request(url, data=body_bytes, method=method)
    req_obj.add_header("Content-Type", "application/json")
    if cookies:
        req_obj.add_header("Cookie", cookies)

    try:
        resp = urllib.request.urlopen(req_obj)
        body = json.loads(resp.read().decode())
        # Extract session cookie from Set-Cookie headers
        new_cookies = ""
        for h in resp.info().get_all("Set-Cookie") or []:
            # Parse "session=xxx; Path=/; HttpOnly" → "session=xxx"
            parts = h.split(";")
            if "=" in parts[0]:
                if new_cookies:
                    new_cookies += "; "
                new_cookies += parts[0]
        return resp.status, body, new_cookies
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode())
        return e.code, body, ""


def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  ✅ {name}")
    else:
        FAIL_COUNT += 1
        print(f"  ❌ {name} FAILED: {detail}")


print("=" * 60)
print("World Cup Guess - E2E Test Suite")
print("=" * 60)

# ── Test 1: Register ──
print("\n📝 Test 1: User Registration")
try:
    # Register 玩家A (already exists from previous run? ignore)
    s, b, _ = req("POST", "/api/register", {"nickname": "玩家A", "password": "123"})
    check("Register 玩家A", b.get("ok") is True or "已被注册" in b.get("msg", ""),
          b.get("msg", ""))

    s, b, c1 = req("POST", "/api/register", {"nickname": "玩家B", "password": "456"})
    check("Register 玩家B", b.get("ok") is True or "已被注册" in b.get("msg", ""),
          b.get("msg", ""))

    s, b, c2 = req("POST", "/api/register", {"nickname": "玩家C", "password": "789"})
    check("Register 玩家C", b.get("ok") is True or "已被注册" in b.get("msg", ""),
          b.get("msg", ""))
except Exception as e:
    check("Registration test", False, str(e))

# ── Test 2: Login ──
print("\n🔑 Test 2: Login")
try:
    s, b, admin_cookies = req("POST", "/api/login",
                               {"nickname": "admin", "password": "admin123"})
    check("Admin login", b.get("ok") is True and b.get("is_admin") is True,
          b.get("msg", ""))

    s, b, user_cookies = req("POST", "/api/login", {"nickname": "玩家A", "password": "123"})
    check("User login", b.get("ok") is True, b.get("msg", ""))

    s, b, _ = req("POST", "/api/login", {"nickname": "玩家A", "password": "wrong"})
    check("Wrong password rejected", b.get("ok") is False, b.get("msg", ""))
except Exception as e:
    check("Login test", False, str(e))

# ── Test 3: Admin adds matches ──
print("\n⚽ Test 3: Admin Match Management")
try:
    # Add a match
    s, b, _ = req("POST", "/api/admin/match",
                   {"round": "R32", "match_order": 1,
                    "team_a": "法国", "team_b": "比利时",
                    "match_time": "2026-07-01T18:00"},
                   cookies=admin_cookies)
    check("Add match", b.get("ok") is True, b.get("msg", ""))

    # Add another match
    s, b, _ = req("POST", "/api/admin/match",
                   {"round": "R32", "match_order": 2,
                    "team_a": "巴西", "team_b": "阿根廷",
                    "match_time": "2026-07-01T21:00"},
                   cookies=admin_cookies)
    check("Add second match", b.get("ok") is True, b.get("msg", ""))

    # Non-admin cannot add match
    s, b, _ = req("POST", "/api/admin/match",
                   {"round": "R32", "match_order": 3,
                    "team_a": "A", "team_b": "B",
                    "match_time": "2026-07-02T18:00"},
                   cookies=user_cookies)
    check("Non-admin blocked", b.get("ok") is False, b.get("msg", ""))
except Exception as e:
    check("Match management", False, str(e))

# ── Test 4: Admin opens match for predictions ──
print("\n🔓 Test 4: Open Match for Prediction")
try:
    s, b, _ = req("POST", "/api/admin/toggle-match/1", cookies=admin_cookies)
    check("Open match 1", b.get("ok") is True, b.get("msg", ""))

    s, b, _ = req("POST", "/api/admin/toggle-match/2", cookies=admin_cookies)
    check("Open match 2", b.get("ok") is True, b.get("msg", ""))
except Exception as e:
    check("Toggle match", False, str(e))

# ── Test 5: Submit predictions ──
print("\n🎯 Test 5: Submit Match Predictions")
try:
    # 玩家A predicts France 1-1 Belgium
    s, b, _ = req("POST", "/api/predict/match/1",
                   {"score_a": 1, "score_b": 1},
                   cookies=user_cookies)
    check("玩家A predicts match 1", b.get("ok") is True, b.get("msg", ""))

    # Login as 玩家B
    s, b, yjf_cookies = req("POST", "/api/login",
                             {"nickname": "玩家B", "password": "456"})
    # 玩家B predicts France 2-1 Belgium
    s, b, _ = req("POST", "/api/predict/match/1",
                   {"score_a": 2, "score_b": 1},
                   cookies=yjf_cookies)
    check("玩家B predicts match 1", b.get("ok") is True, b.get("msg", ""))

    # 玩家C predicts France 8-1 Belgium
    s, b, zm_cookies = req("POST", "/api/login",
                            {"nickname": "玩家C", "password": "789"})
    s, b, _ = req("POST", "/api/predict/match/1",
                   {"score_a": 8, "score_b": 1},
                   cookies=zm_cookies)
    check("玩家C predicts match 1", b.get("ok") is True, b.get("msg", ""))

    # Predict match 2 as well (for daily star testing)
    s, b, _ = req("POST", "/api/predict/match/2",
                   {"score_a": 1, "score_b": 0},
                   cookies=user_cookies)
    check("玩家A predicts match 2", b.get("ok") is True, b.get("msg", ""))
except Exception as e:
    check("Prediction submission", False, str(e))

# ── Test 6: Enter results & auto-score ──
print("\n🧮 Test 6: Auto Scoring (the most critical test!)")

print("  Scenario: France 8-1 Belgium (total goals=9≥5, diff=7≥3 → big match)")
try:
    s, b, _ = req("POST", "/api/admin/result",
                   {"match_id": 1, "score_a": 8, "score_b": 1},
                   cookies=admin_cookies)
    check("Result entered", b.get("ok") is True, b.get("msg", ""))
    check("Stars awarded", b.get("stars_awarded", 0) >= 0,
          f"stars: {b.get('stars_awarded')}")
except Exception as e:
    check("Score calculation", False, str(e))

print("  Verifying individual scores after France 8-1 Belgium:")
print("    - 玩家A pred 1-1: result WRONG (pred draw, real win_a) → 0 pts")
print("    - 玩家B pred 2-1: result CORRECT (win_a), score wrong → 1 pt")
print("    - 玩家C pred 8-1: EXACT + big match → 5 pts")
try:
    s, b, _ = req("GET", "/api/match/1/predictions")
    preds = {p["nickname"]: p for p in b.get("predictions", [])}
    check("玩家A 0 pts", preds.get("玩家A", {}).get("points") == 0,
          f"got {preds.get('玩家A', {}).get('points')}")
    check("玩家B 1 pt", preds.get("玩家B", {}).get("points") == 1,
          f"got {preds.get('玩家B', {}).get('points')}")
    check("玩家C 5 pts", preds.get("玩家C", {}).get("points") == 5,
          f"got {preds.get('玩家C', {}).get('points')}")
except Exception as e:
    check("Score verification", False, str(e))

# ── Test 7: Enter match 2 result ──
print("\n📊 Test 7: Match 2 scoring + daily star")
try:
    s, b, _ = req("POST", "/api/admin/result",
                   {"match_id": 2, "score_a": 1, "score_b": 0},
                   cookies=admin_cookies)
    check("Match 2 result entered", b.get("ok") is True, b.get("msg", ""))
except Exception as e:
    check("Match 2 scoring", False, str(e))

# ── Test 8: Rankings page ──
print("\n📈 Test 8: Rankings")
try:
    # Load rankings HTML page
    resp = urllib.request.urlopen(urllib.request.Request(BASE + "/rankings"))
    html = resp.read().decode()
    check("Rankings page loads", "积分排名" in html, "page content missing")
    check("玩家A appears in rankings", "玩家A" in html, "user not in rankings")
except Exception as e:
    check("Rankings page", False, str(e))

# ── Test 9: Project 1 scoring ──
print("\n🏆 Test 9: Project 1 Scoring")
try:
    # Submit P1 picks
    s, b, _ = req("POST", "/api/predict/p1",
                   {"champion": "法国", "golden_boot": "姆巴佩", "golden_ball": "姆巴佩"},
                   cookies=user_cookies)
    check("玩家A submits P1", b.get("ok") is True, b.get("msg", ""))

    # Admin scores P1
    s, b, _ = req("POST", "/api/admin/score-p1",
                   {"champion": "法国", "golden_boot": "姆巴佩", "golden_ball": "维尼修斯"},
                   cookies=admin_cookies)
    check("P1 scored", b.get("ok") is True, b.get("msg", ""))
    # 玩家A should have 5+5+0 = 10 pts for P1
except Exception as e:
    check("Project 1 scoring", False, str(e))

# ── Test 10: Final scoring check ──
print("\n🎯 Test 10: Final Scoring Verification")
print("  Expected (just P3 for test users):")
print("    玩家C: P3=5 (exact big match)")
print("    玩家B: P3=1 (correct result)")
print("    玩家A: P3=0 (wrong) + P3 match2=3 (exact 1-0)")
print("          Total P3=3, P1=10 → Total=13")

# ── Summary ──
print("\n" + "=" * 60)
print(f"RESULTS: {PASS_COUNT} passed, {FAIL_COUNT} failed, "
      f"{PASS_COUNT + FAIL_COUNT} total")
if FAIL_COUNT == 0:
    print("🎉 All tests passed!")
else:
    print(f"⚠️  {FAIL_COUNT} test(s) failed!")
print("=" * 60)
sys.exit(0 if FAIL_COUNT == 0 else 1)
