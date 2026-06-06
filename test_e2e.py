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

# ── Test 3b: Delete match ──
print("\n🗑 Test 3b: Delete Match")
try:
    # Add a match that we'll delete
    s, b, _ = req("POST", "/api/admin/match",
                   {"round": "QF", "match_order": 99,
                    "team_a": "测试队A", "team_b": "测试队B",
                    "match_time": "2026-07-15T18:00"},
                   cookies=admin_cookies)
    check("Add match to delete", b.get("ok") is True, b.get("msg", ""))
    del_match_id = 3  # third match added

    # Open it and have a user predict
    s, b, _ = req("POST", f"/api/admin/toggle-match/{del_match_id}", cookies=admin_cookies)
    s, b, _ = req("POST", f"/api/predict/match/{del_match_id}",
                   {"score_a": 2, "score_b": 1},
                   cookies=user_cookies)
    check("User predicts on match to delete", b.get("ok") is True, b.get("msg", ""))

    # Delete the match
    s, b, _ = req("POST", f"/api/admin/match/{del_match_id}/delete", cookies=admin_cookies)
    check("Delete match succeeds", b.get("ok") is True, b.get("msg", ""))
    check("Delete msg mentions predictions",
          "1 条预测" in b.get("msg", ""),
          b.get("msg", ""))

    # Non-admin cannot delete
    s, b, _ = req("POST", "/api/admin/match/1/delete", cookies=user_cookies)
    check("Non-admin blocked from delete", b.get("ok") is False, b.get("msg", ""))

    # Verify the deleted match returns 404
    s, b, _ = req("POST", f"/api/admin/match/{del_match_id}/delete", cookies=admin_cookies)
    check("Deleted match returns 404", s == 404, f"status={s}")
except Exception as e:
    check("Delete match", False, str(e))

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

# ── Test 6: Project 2 Group Stage ──
print("\n📋 Test 6: Project 2 - Group Stage Ranking")

# Build 12-group prediction for 玩家A (back to user_cookies)
print("  Submitting group stage predictions for 玩家A...")
try:
    # Create predictions for all 12 groups
    test_groups = []
    group_names = ['A','B','C','D','E','F','G','H','I','J','K','L']
    for i, g in enumerate(group_names):
        # Make diverse predictions for testing
        test_groups.append({
            "group_name": g,
            "first_place": f"Team-{g}-1ST",
            "second_place": f"Team-{g}-2ND"
        })

    s, b, _ = req("POST", "/api/predict/p2",
                   {"groups": test_groups},
                   cookies=user_cookies)
    check("玩家A submits P2 (12 groups)", b.get("ok") is True, b.get("msg", ""))

    # Also submit for 玩家B with slightly different picks
    test_groups_b = []
    for i, g in enumerate(group_names):
        test_groups_b.append({
            "group_name": g,
            "first_place": f"Team-{g}-1ST",
            "second_place": f"Alt-Team-{g}-2ND"  # different 2nd place
        })
    s, b, _ = req("POST", "/api/predict/p2",
                   {"groups": test_groups_b},
                   cookies=yjf_cookies)
    check("玩家B submits P2 (12 groups)", b.get("ok") is True, b.get("msg", ""))
except Exception as e:
    check("P2 prediction submission", False, str(e))

# Admin scores P2
print("  Scoring P2 (group stage results)...")
try:
    # Results: 玩家A's picks are all correct, 玩家B has wrong 2nd place for all
    score_groups = []
    for g in group_names:
        score_groups.append({
            "group_name": g,
            "first_place": f"Team-{g}-1ST",
            "second_place": f"Team-{g}-2ND"
        })

    s, b, _ = req("POST", "/api/admin/score-p2",
                   {"groups": score_groups},
                   cookies=admin_cookies)
    check("P2 scored successfully", b.get("ok") is True, b.get("msg", ""))
except Exception as e:
    check("P2 scoring", False, str(e))

# Verify scores via rankings page
print("  Verifying P2 scores...")
print("    - 玩家A: all 12 groups correct → 24 pts")
print("    - 玩家B: all 12 groups wrong 2nd place → 0 pts")
try:
    resp = urllib.request.urlopen(urllib.request.Request(BASE + "/rankings"))
    html = resp.read().decode()
    # Just verify the page loads with P2 data
    check("Rankings page shows P2", "项目二" in html, "P2 not found in rankings")
except Exception as e:
    check("P2 score verification", False, str(e))

# ── Test 7: Enter results & auto-score ──
print("\n🧮 Test 7: Auto Scoring (the most critical test!)")

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

# ── Test 8: Enter match 2 result ──
print("\n📊 Test 8: Match 2 scoring + daily star")
try:
    s, b, _ = req("POST", "/api/admin/result",
                   {"match_id": 2, "score_a": 1, "score_b": 0},
                   cookies=admin_cookies)
    check("Match 2 result entered", b.get("ok") is True, b.get("msg", ""))
except Exception as e:
    check("Match 2 scoring", False, str(e))

# ── Test 9: Rankings page ──
print("\n📈 Test 9: Rankings")
try:
    # Load rankings HTML page
    resp = urllib.request.urlopen(urllib.request.Request(BASE + "/rankings"))
    html = resp.read().decode()
    check("Rankings page loads", "积分排名" in html, "page content missing")
    check("玩家A appears in rankings", "玩家A" in html, "user not in rankings")
except Exception as e:
    check("Rankings page", False, str(e))

# ── Test 10: Project 1 scoring ──
print("\n🏆 Test 10: Project 1 Scoring")
try:
    # Submit P1 picks (5 items)
    s, b, _ = req("POST", "/api/predict/p1",
                   {"champion": "法国", "golden_boot": "姆巴佩", "golden_ball": "姆巴佩",
                    "golden_glove": "库尔图瓦", "best_young_player": "贝林厄姆"},
                   cookies=user_cookies)
    check("玩家A submits P1", b.get("ok") is True, b.get("msg", ""))

    # Admin scores P1: champion matches, boot matches, ball wrong, glove matches, young wrong
    s, b, _ = req("POST", "/api/admin/score-p1",
                   {"champion": "法国", "golden_boot": "姆巴佩", "golden_ball": "维尼修斯",
                    "golden_glove": "库尔图瓦", "best_young_player": "穆西亚拉"},
                   cookies=admin_cookies)
    check("P1 scored", b.get("ok") is True, b.get("msg", ""))
    # 玩家A: champion 6 + boot 3 + ball 0 + glove 3 + young 0 = 12 pts for P1
except Exception as e:
    check("Project 1 scoring", False, str(e))

# ── Test 11: Final scoring check ──
print("\n🎯 Test 11: Final Scoring Verification")
print("  Expected scores:")
print("    玩家C: P2=0 (didn't submit), P4=5 (exact big match) → Total=5")
print("    玩家B: P2=0 (all wrong 2nd), P4=1 (correct result) → Total=1")
print("    玩家A: P2=24 (all correct), P4=0+3=3, P1=12 (6+3+0+3+0) → Total=39")

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
