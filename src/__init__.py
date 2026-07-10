import os
from datetime import datetime, timezone, timedelta, date as date_type

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

from .config import Config
from .models import db, User, Match, Project1Pick, Project2Pick, GroupStagePick, MatchPrediction, DailyStar, Team, SystemSetting
from .scoring import (
    score_match_prediction, score_project1, score_project2, score_group_stage,
    calculate_daily_stars, get_leaderboard, snapshot_leaderboard_ranks,
    normalize_team_name,
)


def create_app():
    _root = os.path.dirname(os.path.dirname(__file__))
    instance_path = os.path.join(_root, 'instance')
    template_path = os.path.join(_root, 'templates')
    static_path = os.path.join(_root, 'static')
    app = Flask(
        __name__,
        instance_path=os.path.abspath(instance_path),
        template_folder=os.path.abspath(template_path),
        static_folder=os.path.abspath(static_path),
    )
    app.config.from_object(Config)

    # Ensure instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

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

    # ── Jinja2 filter: flag image from country code ──
    @app.template_filter("flag_img")
    def flag_img_filter(country_code):
        """Convert a country code to a flag <img> tag using flagcdn.com.
        Falls back to a generic flag if country_code is empty."""
        if not country_code:
            return '<span class="flag-img" aria-hidden="true">🏳️</span>'
        return (
            f'<img src="https://flagcdn.com/w40/{country_code.lower()}.png"'
            f' width="24" height="16"'
            f' class="flag-img" alt="{country_code}"'
            f' loading="lazy"'
            f' onerror="this.style.display=\'none\'">'
        )

    @app.template_filter("team_flag")
    def team_flag_filter(team_name):
        """Render a team name with its flag image.
        Looks up the team by name in the DB (cached per request via SQLAlchemy).
        Usage: {{ match.team_a | team_flag | safe }}"""
        if not team_name:
            return ""
        team = Team.query.filter_by(name=team_name).first()
        if team and team.country_code:
            return flag_img_filter(team.country_code) + " " + team_name
        return team_name

    # ── Helper: get/update system settings ──
    def _get_setting(key, default=""):
        s = SystemSetting.query.filter_by(key=key).first()
        return s.value if s else default

    def _set_setting(key, value):
        s = SystemSetting.query.filter_by(key=key).first()
        if s:
            s.value = value
            s.updated_at = utcnow()
        else:
            s = SystemSetting(key=key, value=value)
            db.session.add(s)
        db.session.commit()

    def _is_project_closed_by_admin(project_key):
        """Check if admin has manually closed a project."""
        return _get_setting(project_key) == "closed"

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
        full_leaderboard = get_leaderboard()
        leaderboard = full_leaderboard[:5]

        # Latest daily star
        latest_star_date = db.session.query(
            db.func.max(DailyStar.match_date)
        ).scalar()
        latest_stars = []
        if latest_star_date:
            latest_stars = DailyStar.query.filter_by(
                match_date=latest_star_date
            ).all()

        # "收米界最长的河" leader (use full leaderboard, not just top 5)
        star_leader = None
        if full_leaderboard:
            max_stars = max(u["star_count"] for u in full_leaderboard)
            if max_stars > 0:
                candidates = [u for u in full_leaderboard if u["star_count"] == max_stars]
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

        # All teams for search dropdowns
        all_teams = Team.query.order_by(Team.group_name, Team.name).all()

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
            all_teams=all_teams,
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

        # For closed or started matches (and admins always), get all predictions
        beijing_now = utcnow() + timedelta(hours=Config.BEIJING_UTC_OFFSET_HOURS)
        match_predictions_map = {}
        for m in all_matches:
            if m.status == "closed" or beijing_now >= m.match_time or current_user.is_admin:
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
            beijing_now=beijing_now,
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

    @app.route("/stats")
    @login_required
    def stats_page():
        """Statistics page: view all users' predictions for P1/P2/P3 after deadlines."""
        if current_user.is_admin:
            pass  # admin can always view
        # Non-admin users can only view projects that have passed deadline

        p1_deadline = _is_p1_deadline_passed()
        p2_deadline = _is_p2_deadline_passed()
        p3_deadline = _is_p3_deadline_passed()

        # Get all non-admin users
        users = User.query.filter_by(is_admin=False).order_by(User.nickname).all()

        # ── P1 data ──
        p1_picks = []
        champion_counts = {}
        if p1_deadline or current_user.is_admin:
            for u in users:
                pick = Project1Pick.query.filter_by(user_id=u.id).first()
                if pick:
                    p1_picks.append({
                        "nickname": u.nickname,
                        "champion": pick.champion_team,
                        "golden_boot": pick.golden_boot_player,
                        "golden_ball": pick.golden_ball_player,
                        "golden_glove": pick.golden_glove_player,
                        "best_young": pick.best_young_player,
                        "score": pick.score,
                    })
                    champion_counts[pick.champion_team] = champion_counts.get(pick.champion_team, 0) + 1

        # ── P2 data ──
        p2_picks = []
        p2_group_data = {}  # {group_name: {first_place: {team: count}, second_place: {team: count}}}
        if p2_deadline or current_user.is_admin:
            for g in "ABCDEFGHIJKL":
                p2_group_data[g] = {"first": {}, "second": {}}
            for u in users:
                gp_picks = GroupStagePick.query.filter_by(user_id=u.id).order_by(
                    GroupStagePick.group_name
                ).all()
                if gp_picks:
                    user_data = {"nickname": u.nickname, "groups": {}}
                    for gp in gp_picks:
                        user_data["groups"][gp.group_name] = {
                            "first": gp.first_place,
                            "second": gp.second_place,
                            "score": gp.score,
                        }
                        # Aggregate stats
                        if gp.first_place:
                            p2_group_data[gp.group_name]["first"][gp.first_place] = \
                                p2_group_data[gp.group_name]["first"].get(gp.first_place, 0) + 1
                        if gp.second_place:
                            p2_group_data[gp.group_name]["second"][gp.second_place] = \
                                p2_group_data[gp.group_name]["second"].get(gp.second_place, 0) + 1
                    p2_picks.append(user_data)

        # ── P3 data ──
        p3_picks = []
        zone_counts = {"A": {}, "B": {}, "C": {}, "D": {}}
        if p3_deadline or current_user.is_admin:
            for u in users:
                pick = Project2Pick.query.filter_by(user_id=u.id).first()
                if pick:
                    p3_picks.append({
                        "nickname": u.nickname,
                        "zone_a": pick.zone_a_team,
                        "zone_b": pick.zone_b_team,
                        "zone_c": pick.zone_c_team,
                        "zone_d": pick.zone_d_team,
                        "score": pick.score,
                    })
                    for zone, team in [("A", pick.zone_a_team), ("B", pick.zone_b_team),
                                        ("C", pick.zone_c_team), ("D", pick.zone_d_team)]:
                        zone_counts[zone][team] = zone_counts[zone].get(team, 0) + 1

        # Get team info for labels (flag + name)
        teams_map = {t.name: t for t in Team.query.all()}

        return render_template(
            "stats.html",
            p1_deadline=p1_deadline,
            p2_deadline=p2_deadline,
            p3_deadline=p3_deadline,
            p1_picks=p1_picks,
            p2_picks=p2_picks,
            p3_picks=p3_picks,
            champion_counts=champion_counts,
            p2_group_data=p2_group_data,
            zone_counts=zone_counts,
            teams_map=teams_map,
            user_count=len(users),
        )

    @app.route("/admin")
    @login_required
    def admin():
        if not current_user.is_admin:
            flash("无权访问管理后台", "error")
            return redirect(url_for("index"))

        matches = Match.query.order_by(Match.match_time.asc()).all()
        all_teams = Team.query.order_by(Team.group_name, Team.name).all()

        # Current project status settings
        project_settings = {
            "p1_status": _get_setting("p1_status"),
            "p2_status": _get_setting("p2_status"),
            "p3_status": _get_setting("p3_status"),
        }

        return render_template(
            "admin.html",
            matches=matches,
            all_teams=all_teams,
            project_settings=project_settings,
        )

    @app.route("/users")
    @login_required
    def users_page():
        if not current_user.is_admin:
            flash("无权访问用户管理", "error")
            return redirect(url_for("index"))

        users = User.query.filter_by(is_admin=False).order_by(User.nickname).all()
        all_teams = Team.query.order_by(Team.group_name, Team.name).all()

        return render_template(
            "users.html",
            users=users,
            all_teams=all_teams,
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
        golden_glove = data.get("golden_glove", "").strip()
        best_young_player = data.get("best_young_player", "").strip()

        if not all([champion, golden_boot, golden_ball, golden_glove, best_young_player]):
            return jsonify({"ok": False, "msg": "五项预测不能为空"}), 400

        # Normalize champion team name against Team table
        team_names = [t.name for t in Team.query.all()]
        champion = normalize_team_name(champion, team_names)

        # Validate champion is a real team
        if champion not in team_names:
            return jsonify({"ok": False, "msg": f"「{champion}」不是有效球队，请从列表中选择"}), 400

        pick = Project1Pick.query.filter_by(user_id=current_user.id).first()
        if pick:
            pick.champion_team = champion
            pick.golden_boot_player = golden_boot
            pick.golden_ball_player = golden_ball
            pick.golden_glove_player = golden_glove
            pick.best_young_player = best_young_player
            pick.updated_at = utcnow()
        else:
            pick = Project1Pick(
                user_id=current_user.id,
                champion_team=champion,
                golden_boot_player=golden_boot,
                golden_ball_player=golden_ball,
                golden_glove_player=golden_glove,
                best_young_player=best_young_player,
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

        # Build team name lookup for normalization + group validation
        all_teams = Team.query.all()
        team_names = [t.name for t in all_teams]
        team_group_map = {t.name: t.group_name for t in all_teams}  # canonical name → group

        for g in groups:
            group_name = g.get("group_name", "").strip().upper()
            first = g.get("first_place", "").strip()
            second = g.get("second_place", "").strip()

            if not first or not second:
                return jsonify({"ok": False, "msg": f"小组{group_name}的第一和第二名不能为空"}), 400

            if first == second:
                return jsonify({"ok": False, "msg": f"小组{group_name}的第一和第二名不能相同"}), 400

            # Normalize team names
            first = normalize_team_name(first, team_names)
            second = normalize_team_name(second, team_names)

            # Validate teams exist and belong to the correct group
            for label, val in [("第一名", first), ("第二名", second)]:
                if val not in team_names:
                    return jsonify({"ok": False, "msg": f"「{val}」不是有效球队（{group_name}组{label}）"}), 400
                if team_group_map.get(val) != group_name:
                    return jsonify({"ok": False, "msg": f"「{val}」不属于{group_name}组，请从{group_name}组球队中选择"}), 400

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

        # Normalize team names
        all_teams = Team.query.all()
        team_names = [t.name for t in all_teams]
        team_zone_map = {t.name: t.zone for t in all_teams}  # canonical name → zone
        zone_a = normalize_team_name(zone_a, team_names)
        zone_b = normalize_team_name(zone_b, team_names)
        zone_c = normalize_team_name(zone_c, team_names)
        zone_d = normalize_team_name(zone_d, team_names)

        # Validate each zone pick is a real team AND belongs to the correct zone
        for label, zone_key, val in [("A区", "A", zone_a), ("B区", "B", zone_b),
                                      ("C区", "C", zone_c), ("D区", "D", zone_d)]:
            if val not in team_names:
                return jsonify({"ok": False, "msg": f"「{val}」不是有效球队（{label}），请从列表中选择"}), 400
            if team_zone_map.get(val) != zone_key:
                return jsonify({"ok": False, "msg": f"「{val}」不属于{label}，请从{label}球队列表中选择"}), 400

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

        # Check kickoff time (convert UTC to Beijing time for comparison)
        beijing_now = utcnow() + timedelta(hours=Config.BEIJING_UTC_OFFSET_HOURS)
        if beijing_now >= match.match_time:
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

        # Validate team names
        team_names = [t.name for t in Team.query.all()]
        team_a = normalize_team_name(team_a, team_names)
        team_b = normalize_team_name(team_b, team_names)
        for label, val in [("主队", team_a), ("客队", team_b)]:
            if val not in team_names:
                return jsonify({"ok": False, "msg": f"「{val}」不是有效球队（{label}），请从列表中选择"}), 400

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

    @app.route("/api/admin/match/<int:match_id>/delete", methods=["POST"])
    @login_required
    def api_admin_delete_match(match_id):
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        match = Match.query.get(match_id)
        if not match:
            return jsonify({"ok": False, "msg": "比赛不存在或已被删除"}), 404

        # Count and delete associated predictions
        pred_count = MatchPrediction.query.filter_by(match_id=match.id).count()
        MatchPrediction.query.filter_by(match_id=match.id).delete()

        db.session.delete(match)
        db.session.commit()

        return jsonify({
            "ok": True,
            "msg": f"比赛「{match.team_a} vs {match.team_b}」已删除（连带 {pred_count} 条预测）",
        })

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

        # Snapshot ranks before scoring
        snapshot_leaderboard_ranks(db)

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
        real_golden_glove = data.get("golden_glove", "").strip()
        real_best_young_player = data.get("best_young_player", "").strip()

        # Validate champion is a real team
        team_names = [t.name for t in Team.query.all()]
        real_champion = normalize_team_name(real_champion, team_names)
        if real_champion not in team_names:
            return jsonify({"ok": False, "msg": f"「{real_champion}」不是有效球队，请从列表中选择"}), 400

        # Snapshot ranks before scoring
        snapshot_leaderboard_ranks(db)

        picks = Project1Pick.query.all()
        count = 0
        for pick in picks:
            pick.score = score_project1(pick, real_champion, real_golden_boot,
                                        real_golden_ball, real_golden_glove,
                                        real_best_young_player)
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

        if not groups or len(groups) < 1:
            return jsonify({"ok": False, "msg": "请至少提供一个小组的结果"}), 400

        # Build team lookup for validation
        all_teams = Team.query.all()
        team_names = [t.name for t in all_teams]
        team_group_map = {t.name: t.group_name for t in all_teams}

        # Build lookup: group_name → {first, second}
        results = {}
        for g in groups:
            gn = g.get("group_name", "").strip().upper()
            first = g.get("first_place", "").strip()
            second = g.get("second_place", "").strip()
            if not gn or not first or not second:
                return jsonify({"ok": False, "msg": "每个小组需提供组名、第一和第二名"}), 400

            first = normalize_team_name(first, team_names)
            second = normalize_team_name(second, team_names)

            for label, val in [("第一名", first), ("第二名", second)]:
                if val not in team_names:
                    return jsonify({"ok": False, "msg": f"「{val}」不是有效球队（{gn}组{label}）"}), 400
                if team_group_map.get(val) != gn:
                    return jsonify({"ok": False, "msg": f"「{val}」不属于{gn}组，请从{gn}组球队中选择"}), 400

            results[gn] = (first, second)

        # Snapshot ranks before scoring
        snapshot_leaderboard_ranks(db)

        picks = GroupStagePick.query.all()
        count = 0
        for pick in picks:
            actual = results.get(pick.group_name)
            if actual:
                pick.score = score_group_stage(pick, actual[0], actual[1])
                count += 1

        db.session.commit()
        submitted_groups = list(results.keys())
        submitted_groups.sort()
        return jsonify({"ok": True, "msg": f"项目二（小组赛排名）已结算 {', '.join(submitted_groups)} 组，{count} 条预测已更新"})

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

        # Normalize and validate team names (each slot maps to zone A/B/C/D)
        all_teams = Team.query.all()
        team_names = [t.name for t in all_teams]
        team_zone_map = {t.name: t.zone for t in all_teams}
        zone_labels = ["A区", "B区", "C区", "D区"]
        zone_keys = ["A", "B", "C", "D"]
        normalized = []
        for i, t in enumerate(semifinal_teams):
            nt = normalize_team_name(t.strip(), team_names)
            if nt not in team_names:
                return jsonify({"ok": False, "msg": f"「{t}」不是有效球队，请从列表中选择"}), 400
            if team_zone_map.get(nt) != zone_keys[i]:
                return jsonify({"ok": False, "msg": f"「{nt}」不属于{zone_labels[i]}，请从{zone_labels[i]}球队中选择"}), 400
            normalized.append(nt)
        semifinal_teams = normalized

        # Snapshot ranks before scoring
        snapshot_leaderboard_ranks(db)

        picks = Project2Pick.query.all()
        count = 0
        for pick in picks:
            pick.score = score_project2(pick, semifinal_teams)
            count += 1

        db.session.commit()
        return jsonify({"ok": True, "msg": f"项目三（四强预测）已结算，{count} 位群友的分数已更新"})

    # ── API Routes: Admin Project Status Control ──

    @app.route("/api/admin/settings/<key>", methods=["GET", "POST"])
    @login_required
    def api_admin_settings(key):
        """GET: read a setting value. POST: update a setting value."""
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        allowed = {"p1_status", "p2_status", "p3_status"}
        if key not in allowed:
            return jsonify({"ok": False, "msg": "无效的设置项"}), 400

        if request.method == "GET":
            val = _get_setting(key)
            return jsonify({"ok": True, "key": key, "value": val})

        # POST: toggle or set
        data = request.get_json()
        value = data.get("value", "").strip()
        if value not in ("open", "closed", ""):
            return jsonify({"ok": False, "msg": "值必须为 open / closed / 空字符串"}), 400

        _set_setting(key, value)
        labels = {"p1_status": "项目一", "p2_status": "项目二", "p3_status": "项目三"}
        status_labels = {"open": "已开放", "closed": "已截止", "": "自动（默认）"}
        return jsonify({
            "ok": True,
            "msg": f"{labels.get(key, key)} → {status_labels.get(value, value)}",
            "key": key,
            "value": value,
        })

    # ── API Routes: Admin Team Management ──

    @app.route("/api/admin/teams", methods=["GET"])
    @login_required
    def api_admin_get_teams():
        """List all teams"""
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        teams = Team.query.order_by(Team.group_name, Team.name).all()
        return jsonify({
            "ok": True,
            "teams": [{
                "id": t.id,
                "name": t.name,
                "name_en": t.name_en,
                "group_name": t.group_name,
                "zone": t.zone,
                "flag_emoji": t.flag_emoji,
            } for t in teams]
        })

    @app.route("/api/admin/team/<int:team_id>", methods=["POST"])
    @login_required
    def api_admin_update_team(team_id):
        """Update a team's zone or group"""
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        team = Team.query.get(team_id)
        if not team:
            return jsonify({"ok": False, "msg": "球队不存在"}), 404

        data = request.get_json()
        if "zone" in data:
            zone = data["zone"].strip().upper()
            if zone not in ("A", "B", "C", "D", ""):
                return jsonify({"ok": False, "msg": "分区必须为A/B/C/D或空"}), 400
            team.zone = zone if zone else None
        if "group_name" in data:
            gn = data["group_name"].strip().upper()
            if gn not in "ABCDEFGHIJKL":
                return jsonify({"ok": False, "msg": "小组必须为A-L"}), 400
            team.group_name = gn

        db.session.commit()
        return jsonify({"ok": True, "msg": f"球队「{team.name}」已更新"})

    # ── API Routes: Admin Edit User Picks ──

    @app.route("/api/admin/user/<int:user_id>/p1", methods=["GET", "POST"])
    @login_required
    def api_admin_user_p1(user_id):
        """GET: view user's P1 pick. POST: update user's P1 pick."""
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        user = User.query.get(user_id)
        if not user or user.is_admin:
            return jsonify({"ok": False, "msg": "用户不存在"}), 404

        if request.method == "GET":
            pick = Project1Pick.query.filter_by(user_id=user_id).first()
            if not pick:
                return jsonify({"ok": True, "pick": None, "msg": "该用户尚未提交项目一"})
            return jsonify({
                "ok": True,
                "pick": {
                    "champion": pick.champion_team,
                    "golden_boot": pick.golden_boot_player,
                    "golden_ball": pick.golden_ball_player,
                    "golden_glove": pick.golden_glove_player,
                    "best_young_player": pick.best_young_player,
                    "score": pick.score,
                }
            })

        # POST: update
        data = request.get_json()
        pick = Project1Pick.query.filter_by(user_id=user_id).first()
        if not pick:
            return jsonify({"ok": False, "msg": "该用户尚未提交项目一，无法编辑"}), 400

        if "champion" in data:
            team_names = [t.name for t in Team.query.all()]
            pick.champion_team = normalize_team_name(data["champion"].strip(), team_names)
        if "golden_boot" in data:
            pick.golden_boot_player = data["golden_boot"].strip()
        if "golden_ball" in data:
            pick.golden_ball_player = data["golden_ball"].strip()
        if "golden_glove" in data:
            pick.golden_glove_player = data["golden_glove"].strip()
        if "best_young_player" in data:
            pick.best_young_player = data["best_young_player"].strip()

        pick.updated_at = utcnow()
        db.session.commit()
        return jsonify({"ok": True, "msg": f"已更新 {user.nickname} 的项目一预测"})

    @app.route("/api/admin/user/<int:user_id>/p2", methods=["GET", "POST"])
    @login_required
    def api_admin_user_p2(user_id):
        """GET: view user's P2 picks. POST: update user's P2 picks."""
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        user = User.query.get(user_id)
        if not user or user.is_admin:
            return jsonify({"ok": False, "msg": "用户不存在"}), 404

        if request.method == "GET":
            picks = GroupStagePick.query.filter_by(user_id=user_id).order_by(
                GroupStagePick.group_name
            ).all()
            return jsonify({
                "ok": True,
                "groups": [{
                    "group_name": p.group_name,
                    "first_place": p.first_place,
                    "second_place": p.second_place,
                    "score": p.score,
                } for p in picks]
            })

        # POST: update
        data = request.get_json()
        groups = data.get("groups", [])

        if not groups:
            return jsonify({"ok": False, "msg": "请提供小组数据"}), 400

        team_names = [t.name for t in Team.query.all()]

        for g in groups:
            group_name = g.get("group_name", "").strip().upper()
            first = g.get("first_place", "").strip()
            second = g.get("second_place", "").strip()

            if not group_name or not first or not second:
                continue

            first = normalize_team_name(first, team_names)
            second = normalize_team_name(second, team_names)

            pick = GroupStagePick.query.filter_by(
                user_id=user_id, group_name=group_name
            ).first()
            if pick:
                pick.first_place = first
                pick.second_place = second
                pick.updated_at = utcnow()
            else:
                pick = GroupStagePick(
                    user_id=user_id,
                    group_name=group_name,
                    first_place=first,
                    second_place=second,
                )
                db.session.add(pick)

        db.session.commit()
        return jsonify({"ok": True, "msg": f"已更新 {user.nickname} 的项目二预测"})

    @app.route("/api/admin/user/<int:user_id>/p3", methods=["GET", "POST"])
    @login_required
    def api_admin_user_p3(user_id):
        """GET: view user's P3 pick. POST: update user's P3 pick."""
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        user = User.query.get(user_id)
        if not user or user.is_admin:
            return jsonify({"ok": False, "msg": "用户不存在"}), 404

        if request.method == "GET":
            pick = Project2Pick.query.filter_by(user_id=user_id).first()
            if not pick:
                return jsonify({"ok": True, "pick": None, "msg": "该用户尚未提交项目三"})
            return jsonify({
                "ok": True,
                "pick": {
                    "zone_a": pick.zone_a_team,
                    "zone_b": pick.zone_b_team,
                    "zone_c": pick.zone_c_team,
                    "zone_d": pick.zone_d_team,
                    "score": pick.score,
                }
            })

        # POST: update
        data = request.get_json()
        pick = Project2Pick.query.filter_by(user_id=user_id).first()
        if not pick:
            return jsonify({"ok": False, "msg": "该用户尚未提交项目三，无法编辑"}), 400

        all_teams = Team.query.all()
        team_names = [t.name for t in all_teams]
        team_zone_map = {t.name: t.zone for t in all_teams}

        zone_updates = {}
        if "zone_a" in data:
            zone_updates["A"] = ("zone_a", "A区", data["zone_a"].strip())
        if "zone_b" in data:
            zone_updates["B"] = ("zone_b", "B区", data["zone_b"].strip())
        if "zone_c" in data:
            zone_updates["C"] = ("zone_c", "C区", data["zone_c"].strip())
        if "zone_d" in data:
            zone_updates["D"] = ("zone_d", "D区", data["zone_d"].strip())

        for zone_key, (attr, label, val) in zone_updates.items():
            val = normalize_team_name(val, team_names)
            if val not in team_names:
                return jsonify({"ok": False, "msg": f"「{val}」不是有效球队（{label}）"}), 400
            if team_zone_map.get(val) != zone_key:
                return jsonify({"ok": False, "msg": f"「{val}」不属于{label}，请从{label}球队列表中选择"}), 400
            setattr(pick, attr + "_team", val)

        pick.updated_at = utcnow()
        db.session.commit()
        return jsonify({"ok": True, "msg": f"已更新 {user.nickname} 的项目三预测"})

    @app.route("/api/admin/user/<int:user_id>/delete", methods=["POST"])
    @login_required
    def api_admin_delete_user(user_id):
        """Delete a user account and all their related data."""
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        user = User.query.get(user_id)
        if not user:
            return jsonify({"ok": False, "msg": "用户不存在"}), 404

        if user.is_admin:
            return jsonify({"ok": False, "msg": "不能删除管理员账户"}), 400

        nickname = user.nickname

        # Delete all related data (SQLite doesn't enforce FK cascade)
        Project1Pick.query.filter_by(user_id=user_id).delete()
        GroupStagePick.query.filter_by(user_id=user_id).delete()
        Project2Pick.query.filter_by(user_id=user_id).delete()
        MatchPrediction.query.filter_by(user_id=user_id).delete()
        DailyStar.query.filter_by(user_id=user_id).delete()

        db.session.delete(user)
        db.session.commit()

        return jsonify({
            "ok": True,
            "msg": f"用户「{nickname}」及其所有竞猜数据已删除",
        })

    @app.route("/api/admin/user/<int:user_id>/reset-password", methods=["POST"])
    @login_required
    def api_admin_reset_password(user_id):
        """Reset a user's password (admin only)."""
        if not current_user.is_admin:
            return jsonify({"ok": False, "msg": "无权操作"}), 403

        user = User.query.get(user_id)
        if not user:
            return jsonify({"ok": False, "msg": "用户不存在"}), 404

        if user.is_admin:
            return jsonify({"ok": False, "msg": "不能重置管理员密码"}), 400

        data = request.get_json()
        new_password = data.get("password", "").strip()

        if not new_password or len(new_password) < 3:
            return jsonify({"ok": False, "msg": "新密码至少3位"}), 400

        user.set_password(new_password)
        db.session.commit()

        return jsonify({
            "ok": True,
            "msg": f"用户「{user.nickname}」的密码已重置为「{new_password}」",
            "nickname": user.nickname,
            "password": new_password,
        })

    @app.route("/api/match/<int:match_id>/predictions")
    def api_match_predictions(match_id):
        """Get all predictions for a match (public after match started/closed, or admin always)"""
        match = Match.query.get_or_404(match_id)
        beijing_now = utcnow() + timedelta(hours=Config.BEIJING_UTC_OFFSET_HOURS)
        if match.status != "closed" and beijing_now < match.match_time and not current_user.is_admin:
            return jsonify({"ok": False, "msg": "比赛尚未开始"}), 400

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
        """P1 deadline: only when admin explicitly closes it."""
        return _is_project_closed_by_admin("p1_status")

    def _is_p2_deadline_passed():
        """P2 deadline: only when admin explicitly closes it."""
        return _is_project_closed_by_admin("p2_status")

    def _is_p3_open():
        """P3 is always open unless admin explicitly closes it."""
        return not _is_project_closed_by_admin("p3_status")

    def _is_p3_deadline_passed():
        """P3 deadline: only when admin explicitly closes it."""
        return _is_project_closed_by_admin("p3_status")

    # ── CLI Commands ──

    @app.cli.command("init-db")
    def init_db():
        """Initialize database with tables, admin user, and 48 teams."""
        db.create_all()

        # Admin user
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

        # Seed 48 teams (2026 World Cup)
        if Team.query.first() is None:
            # Zone mapping (group winner path → QF zone):
            #   A区 (QF1 Boston): E, F, I
            #   B区 (QF2 LA):     D, G, H
            #   C区 (QF4 KC):     A, C, L
            #   D区 (QF3 Miami):  B, J, K
            zone_map = {
                "A": "C", "B": "D", "C": "C", "D": "B",
                "E": "A", "F": "A", "G": "B", "H": "B",
                "I": "A", "J": "D", "K": "D", "L": "C",
            }
            teams_data = [
                # Group A
                ("墨西哥", "Mexico", "A", "🇲🇽", "mx"),
                ("南非", "South Africa", "A", "🇿🇦", "za"),
                ("韩国", "South Korea", "A", "🇰🇷", "kr"),
                ("捷克", "Czechia", "A", "🇨🇿", "cz"),
                # Group B
                ("加拿大", "Canada", "B", "🇨🇦", "ca"),
                ("波黑", "Bosnia and Herzegovina", "B", "🇧🇦", "ba"),
                ("卡塔尔", "Qatar", "B", "🇶🇦", "qa"),
                ("瑞士", "Switzerland", "B", "🇨🇭", "ch"),
                # Group C
                ("巴西", "Brazil", "C", "🇧🇷", "br"),
                ("摩洛哥", "Morocco", "C", "🇲🇦", "ma"),
                ("海地", "Haiti", "C", "🇭🇹", "ht"),
                ("苏格兰", "Scotland", "C", "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "gb-sct"),
                # Group D
                ("美国", "United States", "D", "🇺🇸", "us"),
                ("巴拉圭", "Paraguay", "D", "🇵🇾", "py"),
                ("澳大利亚", "Australia", "D", "🇦🇺", "au"),
                ("土耳其", "Türkiye", "D", "🇹🇷", "tr"),
                # Group E
                ("德国", "Germany", "E", "🇩🇪", "de"),
                ("库拉索", "Curaçao", "E", "🇨🇼", "cw"),
                ("科特迪瓦", "Côte d'Ivoire", "E", "🇨🇮", "ci"),
                ("厄瓜多尔", "Ecuador", "E", "🇪🇨", "ec"),
                # Group F
                ("荷兰", "Netherlands", "F", "🇳🇱", "nl"),
                ("日本", "Japan", "F", "🇯🇵", "jp"),
                ("瑞典", "Sweden", "F", "🇸🇪", "se"),
                ("突尼斯", "Tunisia", "F", "🇹🇳", "tn"),
                # Group G
                ("比利时", "Belgium", "G", "🇧🇪", "be"),
                ("埃及", "Egypt", "G", "🇪🇬", "eg"),
                ("伊朗", "Iran", "G", "🇮🇷", "ir"),
                ("新西兰", "New Zealand", "G", "🇳🇿", "nz"),
                # Group H
                ("西班牙", "Spain", "H", "🇪🇸", "es"),
                ("佛得角", "Cape Verde", "H", "🇨🇻", "cv"),
                ("沙特", "Saudi Arabia", "H", "🇸🇦", "sa"),
                ("乌拉圭", "Uruguay", "H", "🇺🇾", "uy"),
                # Group I
                ("法国", "France", "I", "🇫🇷", "fr"),
                ("塞内加尔", "Senegal", "I", "🇸🇳", "sn"),
                ("伊拉克", "Iraq", "I", "🇮🇶", "iq"),
                ("挪威", "Norway", "I", "🇳🇴", "no"),
                # Group J
                ("阿根廷", "Argentina", "J", "🇦🇷", "ar"),
                ("阿尔及利亚", "Algeria", "J", "🇩🇿", "dz"),
                ("奥地利", "Austria", "J", "🇦🇹", "at"),
                ("约旦", "Jordan", "J", "🇯🇴", "jo"),
                # Group K
                ("葡萄牙", "Portugal", "K", "🇵🇹", "pt"),
                ("刚果(金)", "DR Congo", "K", "🇨🇩", "cd"),
                ("乌兹别克斯坦", "Uzbekistan", "K", "🇺🇿", "uz"),
                ("哥伦比亚", "Colombia", "K", "🇨🇴", "co"),
                # Group L
                ("英格兰", "England", "L", "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "gb-eng"),
                ("克罗地亚", "Croatia", "L", "🇭🇷", "hr"),
                ("加纳", "Ghana", "L", "🇬🇭", "gh"),
                ("巴拿马", "Panama", "L", "🇵🇦", "pa"),
            ]
            for name, name_en, group_name, flag, country_code in teams_data:
                team = Team(
                    name=name,
                    name_en=name_en,
                    group_name=group_name,
                    zone=zone_map.get(group_name),
                    flag_emoji=flag,
                    country_code=country_code,
                )
                db.session.add(team)
            db.session.commit()
            print(f"Seeded {len(teams_data)} teams.")
        else:
            print("Teams already exist, skipping seed.")

        print("Database initialized.")

    return app
