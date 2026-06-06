import os
from datetime import datetime, timezone, date as date_type

def utcnow():
    """Return naive UTC datetime for SQLite compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, session,
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required,
    current_user,
)
from werkzeug.security import check_password_hash

from config import Config
from models import db, User, Match, Project1Pick, Project2Pick, GroupStagePick, MatchPrediction, DailyStar
from scoring import (
    score_match_prediction, score_project1, score_project2, score_group_stage,
    calculate_daily_stars, get_leaderboard,
)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure instance folder exists
    os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)

    db.init_app(app)

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "login_page"
    login_manager.login_message = "请先登录后再操作"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ── Context processor: inject current datetime ──
    @app.context_processor
    def inject_now():
        return {"now": utcnow()}

    # ── Page Routes ──

    @app.route("/")
    def index():
        # Upcoming matches
        upcoming = Match.query.filter(
            Match.status.in_(["upcoming", "open"])
        ).order_by(Match.match_time.asc()).limit(5).all()

        # Recent completed
        recent = Match.query.filter_by(status="closed").order_by(
            Match.match_time.desc()
        ).limit(5).all()

        # Leaderboard top 5
        leaderboard = get_leaderboard()[:5]

        # Latest daily star
        latest_star_date = db.session.query(
            db.func.max(DailyStar.match_date)
        ).scalar()
        latest_stars = []
        if latest_star_date:
            latest_stars = DailyStar.query.filter_by(
                match_date=latest_star_date
            ).all()

        # "收米界最长的河" leader
        star_leader = None
        if leaderboard:
            max_stars = max(u["star_count"] for u in leaderboard)
            if max_stars > 0:
                candidates = [u for u in leaderboard if u["star_count"] == max_stars]
                star_leader = candidates

        return render_template(
            "index.html",
            upcoming=upcoming,
            recent=recent,
            leaderboard=leaderboard,
            latest_stars=latest_stars,
            star_leader=star_leader,
        )

    @app.route("/login")
    def login_page():
        return render_template("login.html")

    @app.route("/rules")
    def rules():
        return render_template("rules.html")

    @app.route("/predict")
    @login_required
    def predict_page():
        if current_user.is_admin:
            flash("管理员账号不需要参与竞猜", "info")
            return redirect(url_for("admin"))

        # Project 1 status
        p1_pick = Project1Pick.query.filter_by(user_id=current_user.id).first()
        p1_deadline_passed = _is_p1_deadline_passed()

        # Project 2 status (Group stage ranking - NEW)
        p2_group_picks = GroupStagePick.query.filter_by(
            user_id=current_user.id
        ).order_by(GroupStagePick.group_name).all()
        p2_group_picks_map = {gp.group_name: gp for gp in p2_group_picks}
        p2_deadline_passed = _is_p2_deadline_passed()

        # Project 3 status (Semifinal - was P2)
        p3_pick = Project2Pick.query.filter_by(user_id=current_user.id).first()
        p3_open = _is_p3_open()
        p3_deadline_passed = _is_p3_deadline_passed()

        # Project 4: Match predictions (was P3)
        open_matches = Match.query.filter_by(status="open").order_by(
            Match.match_time.asc()
        ).all()

        # Get existing predictions for open matches
        user_predictions = {}
        for m in open_matches:
            pred = MatchPrediction.query.filter_by(
                user_id=current_user.id, match_id=m.id
            ).first()
            if pred:
                user_predictions[m.id] = pred

        return render_template(
            "predict.html",
            p1_pick=p1_pick,
            p1_deadline_passed=p1_deadline_passed,
            p2_group_picks_map=p2_group_picks_map,
            p2_deadline_passed=p2_deadline_passed,
            p3_pick=p3_pick,
            p3_open=p3_open,
            p3_deadline_passed=p3_deadline_passed,
            open_matches=open_matches,
            user_predictions=user_predictions,
        )

    @app.route("/matches")
    def matches_page():
        all_matches = Match.query.order_by(Match.match_time.asc()).all()

        # Get user predictions if logged in
        user_preds = {}
        if current_user.is_authenticated and not current_user.is_admin:
            for m in all_matches:
                pred = MatchPrediction.query.filter_by(
                    user_id=current_user.id, match_id=m.id
                ).first()
                if pred:
                    user_preds[m.id] = pred

        # For closed matches, get all predictions for transparency
        match_predictions_map = {}
        for m in all_matches:
            if m.status == "closed":
                preds = MatchPrediction.query.filter_by(match_id=m.id).all()
                match_predictions_map[m.id] = [
                    {"nickname": User.query.get(p.user_id).nickname,
                     "pred_a": p.pred_score_a, "pred_b": p.pred_score_b,
                     "points": p.points}
                    for p in preds
                ]

        return render_template(
            "matches.html",
            matches=all_matches,
            user_preds=user_preds,
            match_predictions_map=match_predictions_map,
        )

    @app.route("/rankings")
    def rankings():
        leaderboard = get_leaderboard()

        # Get all daily stars for display
        stars = DailyStar.query.order_by(DailyStar.match_date.desc()).all()
        star_map = {}
        for s in stars:
            star_map.setdefault(s.match_date, []).append(
                User.query.get(s.user_id).nickname
            )

        return render_template(
            "rankings.html",
            leaderboard=leaderboard,
            star_map=star_map,
        )

    @app.route("/admin")
    @login_required
    def admin():
        if not current_user.is_admin:
            flash("无权访问管理后台", "error")
            return redirect(url_for("index"))

        matches = Match.query.order_by(Match.match_time.asc()).all()
        users = User.query.filter_by(is_admin=False).order_by(User.nickname).all()

        return render_template(
            "admin.html",
            matches=matches,
            users=users,
        )

    # ── API Routes: Auth ──

    @app.route("/api/register", methods=["POST"])
    def api_register():
        data = request.get_json()
        nickname = data.get("nickname", "").strip()
        password = data.get("password", "").strip()

        if not nickname or not password:
            return jsonify({"ok": False, "msg": "昵称和密码不能为空"}), 400

        if len(nickname) > 20:
            return jsonify({"ok": False, "msg": "昵称不能超过20个字"}), 400

        if len(password) < 3:
            return jsonify({"ok": False, "msg": "密码至少3位"}), 400

        if User.query.filter_by(nickname=nickname).first():
            return jsonify({"ok": False, "msg": "该昵称已被注册"}), 400

        user = User(nickname=nickname)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        return jsonify({"ok": True, "msg": "注册成功", "nickname": nickname})

    @app.route("/api/login", methods=["POST"])
    def api_login():
        data = request.get_json()
        nickname = data.get("nickname", "").strip()
        password = data.get("password", "").strip()

        user = User.query.filter_by(nickname=nickname).first()
        if not user or not user.check_password(password):
            return jsonify({"ok": False, "msg": "昵称或密码错误"}), 401

        login_user(user)
        return jsonify({"ok": True, "msg": "登录成功", "nickname": nickname, "is_admin": user.is_admin})

    @app.route("/api/logout", methods=["POST"])
    @login_required
    def api_logout():
        logout_user()
        return jsonify({"ok": True, "msg": "已登出"})

    # ── API Routes: Predictions ──

    @app.route("/api/predict/p1", methods=["POST"])
    @login_required
    def api_predict_p1():
        if current_user.is_admin:
            return jsonify({"ok": False, "msg": "管理员不参与竞猜"}), 400

        if _is_p1_deadline_passed():
            return jsonify({"ok": False, "msg": "项目一已截止，不能提交"}), 400

        data = request.get_json()
        champion = data.get("champion", "").strip()
        golden_boot = data.get("golden_boot", "").strip()
        golden_ball = data.get("golden_ball", "").strip()

        if not champion or not golden_boot or not golden_ball:
            return jsonify({"ok": False, "msg": "三项预测不能为空"}), 400

        pick = Project1Pick.query.filter_by(user_id=current_user.id).first()
        if pick:
            pick.champion_team = champion
            pick.golden_boot_player = golden_boot
            pick.golden_ball_player = golden_ball
            pick.updated_at = utcnow()
        else:
            pick = Project1Pick(
                user_id=current_user.id,
                champion_team=champion,
                golden_boot_player=golden_boot,
                golden_ball_player=golden_ball,
            )
            db.session.add(pick)

        db.session.commit()
        return jsonify({"ok": True, "msg": "项目一预测已保存"})

    @app.route("/api/predict/p2", methods=["POST"])
    @login_required
    def api_predict_p2():
        """Project 2: Group stage ranking prediction"""
        if current_user.is_admin:
            return jsonify({"ok": False, "msg": "管理员不参与竞猜"}), 400

        if _is_p2_deadline_passed():
            return jsonify({"ok": False, "msg": "项目二已截止（小组赛已开始），不能提交"}), 400

        data = request.get_json()
        groups = data.get("groups", [])  # [{group_name, first_place, second_place}, ...]

        if not groups or len(groups) != 12:
            return jsonify({"ok": False, "msg": "请填写全部12个小组的预测"}), 400

        # Validate all groups A-L are present
        group_names = {g.get("group_name", "").strip().upper() for g in groups}
        expected = set("ABCDEFGHIJKL")
        if group_names != expected:
            return jsonify({"ok": False, "msg": "小组名称必须为A-L共12个"}), 400

        for g in groups:
            group_name = g.get("group_name", "").strip().upper()
            first = g.get("first_place", "").strip()
            second = g.get("second_place", "").strip()

            if not first or not second:
                return jsonify({"ok": False, "msg": f"小组{group_name}的第一和第二名不能为空"}), 400

            if first == second:
                return jsonify({"ok": False, "msg": f"小组{group_name}的第一和第二名不能相同"}), 400

            # Upsert this group's pick
            pick = GroupStagePick.query.filter_by(
                user_id=current_user.id, group_name=group_name
            ).first()
            if pick:
                pick.first_place = first
                pick.second_place = second
                pick.updated_at = utcnow()
            else:
                pick = GroupStagePick(
                    user_id=current_user.id,
                    group_name=group_name,
                    first_place=first,
                    second_place=second,
                )
                db.session.add(pick)

        db.session.commit()
        return jsonify({"ok": True, "msg": "项目二（小组赛排名）已保存"})

    @app.route("/api/predict/p3", methods=["POST"])
    @login_required
    def api_predict_p3():
        """Project 3: Semifinal prediction (四强, was P2)"""
        if current_user.is_admin:
            return jsonify({"ok": False, "msg": "管理员不参与竞猜"}), 400

        if not _is_p3_open():
            return jsonify({"ok": False, "msg": "项目三暂未开放"}), 400

        if _is_p3_deadline_passed():
            return jsonify({"ok": False, "msg": "项目三已截止，不能提交"}), 400

        data = request.get_json()
        zone_a = data.get("zone_a", "").strip()
        zone_b = data.get("zone_b", "").strip()
        zone_c = data.get("zone_c", "").strip()
        zone_d = data.get("zone_d", "").strip()

        if not zone_a or not zone_b or not zone_c or not zone_d:
            return jsonify({"ok": False, "msg": "四个分区的选择不能为空"}), 400

        if len({zone_a, zone_b, zone_c, zone_d}) < 4:
            return jsonify({"ok": False, "msg": "四个分区不能选重复球队"}), 400

        pick = Project2Pick.query.filter_by(user_id=current_user.id).first()
        if pick:
            pick.zone_a_team = zone_a
            pick.zone_b_team = zone_b
            pick.zone_c_team = zone_c
            pick.zone_d_team = zone_d
            pick.updated_at = utcnow()
        else:
            pick = Project2Pick(
                user_id=current_user.id,
                zone_a_team=zone_a,
                zone_b_team=zone_b,
                zone_c_team=zone_c,
                zone_d_team=zone_d,
            )
            db.session.add(pick)

        db.session.commit()
        return jsonify({"ok": True, "msg": "项目三（四强预测）已保存"})

    @app.route("/api/predict/match/<int:match_id>", methods=["POST"])
    @login_required
    def api_predict_match(match_id):
        if current_user.is_admin:
            return jsonify({"ok": False, "msg": "管理员不参与竞猜"}), 400

        match = Match.query.get_or_404(match_id)

        if match.status not in ("open", "upcoming"):
            return jsonify({"ok": False, "msg": "该场比赛已截止预测"}), 400

        # Check kickoff time
        if utcnow() >= match.match_time.replace(tzinfo=None):
            return jsonify({"ok": False, "msg": "比赛已开始，不能提交预测"}), 400

        data = request.get_json()
        try:
            score_a = int(data.get("score_a", -1))
            score_b = int(data.get("score_b", -1))
        except (ValueError, TypeError):
            return jsonify({"ok": False, "msg": "请输入有效比分"}), 400

        if score_a < 0 or score_b < 0:
            return jsonify({"ok": False, "msg": "比分不能为负数"}), 400

        # Upsert
        pred = MatchPrediction.query.filter_by(
            user_id=current_user.id, match_id=match_id
        ).first()
        if pred:
            pred.pred_score_a = score_a
            pred.pred_score_b = score_b
            pred.updated_at = utcnow()
        else:
            pred = MatchPrediction(
                user_id=current_user.id,
                match_id=match_id,
                pred_score_a=score_a,
                pred_score_b=score_b,
            )
            db.session.add(pred)

        db.session.commit()
        return jsonify({"ok": True, "msg": f"预测已保存: {match.team_a} {score_a}-{score_b} {match.team_b}"})

    # ── API Routes: Admin ──

    @app.route("/api/admin/match", methods=["POST"])
    @login_required
    def api_admin_match():
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        data = request.get_json()
        round_name = data.get("round", "").strip()
        match_order = data.get("match_order", 0)
        team_a = data.get("team_a", "").strip()
        team_b = data.get("team_b", "").strip()
        match_time_str = data.get("match_time", "").strip()

        if not all([round_name, team_a, team_b, match_time_str]):
            return jsonify({"ok": False, "msg": "请填写所有字段"}), 400

        try:
            match_time = datetime.strptime(match_time_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            return jsonify({"ok": False, "msg": "日期格式错误"}), 400

        match = Match(
            round_name=round_name,
            match_order=int(match_order),
            team_a=team_a,
            team_b=team_b,
            match_time=match_time,
        )
        db.session.add(match)
        db.session.commit()

        return jsonify({"ok": True, "msg": f"比赛已添加: {team_a} vs {team_b}"})

    @app.route("/api/admin/toggle-match/<int:match_id>", methods=["POST"])
    @login_required
    def api_admin_toggle_match(match_id):
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        match = Match.query.get_or_404(match_id)
        if match.status == "upcoming":
            match.status = "open"
        elif match.status == "open":
            match.status = "closed"
        elif match.status == "closed":
            match.status = "open"
        db.session.commit()

        return jsonify({"ok": True, "msg": f"比赛状态已更新为: {match.status}"})

    @app.route("/api/admin/result", methods=["POST"])
    @login_required
    def api_admin_result():
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        data = request.get_json()
        match_id = data.get("match_id")
        score_a = data.get("score_a")
        score_b = data.get("score_b")

        if match_id is None or score_a is None or score_b is None:
            return jsonify({"ok": False, "msg": "请提供比赛ID和比分"}), 400

        match = Match.query.get_or_404(match_id)

        try:
            score_a = int(score_a)
            score_b = int(score_b)
        except (ValueError, TypeError):
            return jsonify({"ok": False, "msg": "比分必须是整数"}), 400

        match.score_a = score_a
        match.score_b = score_b
        match.status = "closed"

        # Score all predictions for this match
        preds = MatchPrediction.query.filter_by(match_id=match.id).all()
        scored_count = 0
        for pred in preds:
            old_points = pred.points
            pred.points = score_match_prediction(
                pred.pred_score_a,
                pred.pred_score_b,
                match.score_a,
                match.score_b,
                is_final=match.is_final,
                is_big_match=match.is_big_match,
            )
            if pred.points != old_points:
                scored_count += 1

        db.session.commit()

        # Calculate daily stars for this match's date
        match_date = match.match_time.date()
        stars = calculate_daily_stars(db, match_date)

        return jsonify({
            "ok": True,
            "msg": f"比分已录入，{scored_count} 条预测已更新",
            "stars_awarded": len(stars),
        })

    @app.route("/api/admin/score-p1", methods=["POST"])
    @login_required
    def api_admin_score_p1():
        """Score all project 1 picks"""
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        data = request.get_json()
        real_champion = data.get("champion", "").strip()
        real_golden_boot = data.get("golden_boot", "").strip()
        real_golden_ball = data.get("golden_ball", "").strip()

        picks = Project1Pick.query.all()
        count = 0
        for pick in picks:
            pick.score = score_project1(pick, real_champion, real_golden_boot, real_golden_ball)
            count += 1

        db.session.commit()
        return jsonify({"ok": True, "msg": f"项目一已结算，{count} 位群友的分数已更新"})

    @app.route("/api/admin/score-p2", methods=["POST"])
    @login_required
    def api_admin_score_p2():
        """Score all project 2 picks (Group stage ranking)"""
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        data = request.get_json()
        groups = data.get("groups", [])  # [{group_name, first_place, second_place}, ...]

        if not groups or len(groups) != 12:
            return jsonify({"ok": False, "msg": "请提供全部12个小组的结果"}), 400

        # Build lookup: group_name → {first, second}
        results = {}
        for g in groups:
            gn = g.get("group_name", "").strip().upper()
            first = g.get("first_place", "").strip()
            second = g.get("second_place", "").strip()
            if not gn or not first or not second:
                return jsonify({"ok": False, "msg": "每个小组需提供组名、第一和第二名"}), 400
            results[gn] = (first, second)

        picks = GroupStagePick.query.all()
        count = 0
        for pick in picks:
            actual = results.get(pick.group_name)
            if actual:
                pick.score = score_group_stage(pick, actual[0], actual[1])
                count += 1

        db.session.commit()
        return jsonify({"ok": True, "msg": f"项目二（小组赛排名）已结算，{count} 条预测已更新"})

    @app.route("/api/admin/score-p3", methods=["POST"])
    @login_required
    def api_admin_score_p3():
        """Score all project 3 picks (Semifinal prediction, was P2)"""
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        data = request.get_json()
        semifinal_teams = data.get("semifinal_teams", [])

        if len(semifinal_teams) != 4:
            return jsonify({"ok": False, "msg": "请提供4支四强球队"}), 400

        picks = Project2Pick.query.all()
        count = 0
        for pick in picks:
            pick.score = score_project2(pick, semifinal_teams)
            count += 1

        db.session.commit()
        return jsonify({"ok": True, "msg": f"项目三（四强预测）已结算，{count} 位群友的分数已更新"})

    @app.route("/api/match/<int:match_id>/predictions")
    def api_match_predictions(match_id):
        """Get all predictions for a match (public after match closed)"""
        match = Match.query.get_or_404(match_id)
        if match.status != "closed":
            return jsonify({"ok": False, "msg": "比赛尚未结束"}), 400

        preds = MatchPrediction.query.filter_by(match_id=match.id).all()
        result = []
        for p in preds:
            user = User.query.get(p.user_id)
            result.append({
                "nickname": user.nickname,
                "pred_a": p.pred_score_a,
                "pred_b": p.pred_score_b,
                "points": p.points,
            })

        return jsonify({"ok": True, "predictions": result})

    # ── Helper Functions ──

    def _is_p1_deadline_passed():
        """P1 deadline: first knockout match kickoff"""
        first_ko = Match.query.filter(
            Match.round_name.in_(["R32", "R16", "QF", "SF", "3RD", "FINAL"])
        ).order_by(Match.match_time.asc()).first()
        if first_ko:
            return utcnow() >= first_ko.match_time.replace(tzinfo=None)
        return False

    def _is_p2_deadline_passed():
        """P2 (group stage) deadline: group stage start date (2026-06-11)"""
        from config import Config
        gs_start = datetime.strptime(Config.GROUP_STAGE_START, "%Y-%m-%d")
        return utcnow() >= gs_start

    def _is_p3_open():
        """P3 (semifinal) opens when R32 teams are set (first R32 match exists)"""
        r32_match = Match.query.filter_by(round_name="R32").first()
        return r32_match is not None

    def _is_p3_deadline_passed():
        """P3 (semifinal) deadline: first R32 match kickoff"""
        first_r32 = Match.query.filter_by(round_name="R32").order_by(
            Match.match_time.asc()
        ).first()
        if first_r32:
            return utcnow() >= first_r32.match_time.replace(tzinfo=None)
        return False

    # ── CLI Commands ──

    @app.cli.command("init-db")
    def init_db():
        """Initialize database with tables and admin user."""
        db.create_all()
        admin = User.query.filter_by(nickname=Config.ADMIN_NICKNAME).first()
        if not admin:
            admin = User(
                nickname=Config.ADMIN_NICKNAME,
                is_admin=True,
            )
            admin.set_password(Config.ADMIN_PASSWORD)
            db.session.add(admin)
            db.session.commit()
            print(f"Admin user created: {Config.ADMIN_NICKNAME}")
        else:
            print(f"Admin user already exists: {Config.ADMIN_NICKNAME}")
        print("Database initialized.")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
