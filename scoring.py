"""
Scoring engine for World Cup Guess game.

Rules:
  Project 1: Champion (8pts) + Golden Boot (3pts) + Golden Ball (3pts)
              + Golden Glove (3pts) + Best Young Player (3pts), max 20pts
  Project 2: Group stage ranking — 12 groups, predict 1st & 2nd,
              both correct + correct order → 1pt per group, max 12pts
  Project 3: 4 zones, pick 1 team each, 2pts per correct, max 8pts
  Project 4: Exact score = 3pts, correct result = 1pt.
              Big match (goals>=5 or diff>=3): exact = 5pts.
              Final: multiplier x2.
"""


def score_match_prediction(pred_score_a, pred_score_b, real_score_a, real_score_b, is_final=False, is_big_match=False):
    """
    Score a single match prediction.

    Returns:
        int: points awarded
    """
    if real_score_a is None or real_score_b is None:
        return 0

    exact_match = (pred_score_a == real_score_a and pred_score_b == real_score_b)

    if exact_match:
        base = 5 if is_big_match else 3
    else:
        # Check result (win/loss/draw)
        pred_result = _get_result(pred_score_a, pred_score_b)
        real_result = _get_result(real_score_a, real_score_b)
        base = 1 if pred_result == real_result else 0

    # Final multiplier
    if is_final:
        base *= 2

    return base


def score_project1(pick, real_champion, real_golden_boot, real_golden_ball,
                   real_golden_glove, real_best_young_player):
    """
    Score project 1 picks.

    Args:
        pick: Project1Pick object
        real_champion: actual champion team name
        real_golden_boot: actual golden boot winner name
        real_golden_ball: actual golden ball winner name
        real_golden_glove: actual golden glove winner name
        real_best_young_player: actual best young player winner name

    Returns:
        int: total points
    """
    from config import Config

    total = 0
    if real_champion and pick.champion_team == real_champion:
        total += Config.P1_CHAMPION_PTS
    if real_golden_boot and pick.golden_boot_player == real_golden_boot:
        total += Config.P1_GOLDEN_BOOT_PTS
    if real_golden_ball and pick.golden_ball_player == real_golden_ball:
        total += Config.P1_GOLDEN_BALL_PTS
    if real_golden_glove and pick.golden_glove_player == real_golden_glove:
        total += Config.P1_GOLDEN_GLOVE_PTS
    if real_best_young_player and pick.best_young_player == real_best_young_player:
        total += Config.P1_BEST_YOUNG_PLAYER_PTS

    return total


def score_project2(pick, semifinal_teams):
    """
    Score project 3 (display) / project 2 picks (DB model).

    Args:
        pick: Project2Pick object
        semifinal_teams: list of 4 actual semifinalist team names

    Returns:
        int: total points
    """
    from config import Config

    if not semifinal_teams or len(semifinal_teams) < 4:
        return 0

    predicted = {pick.zone_a_team, pick.zone_b_team, pick.zone_c_team, pick.zone_d_team}
    actual = set(semifinal_teams)

    correct = len(predicted & actual)
    return correct * Config.P3_PER_TEAM_PTS


def score_group_stage(pick, actual_first, actual_second):
    """
    Score a single group stage prediction.

    Both first AND second place must be correct (order matters).
    Returns 1 point if both are correct, 0 otherwise.

    Args:
        pick: GroupStagePick object
        actual_first: actual first place team name
        actual_second: actual second place team name

    Returns:
        int: 2 if both correct, 0 otherwise
    """
    from config import Config

    if not actual_first or not actual_second:
        return 0

    if pick.first_place == actual_first and pick.second_place == actual_second:
        return Config.P2_GROUP_PTS

    return 0


def calculate_daily_stars(db, match_date):
    """
    Calculate "收米之星" for a given match date.

    Finds users with the highest total points from matches on that date.
    Awards DailyStar to all users tied for the top.

    Args:
        db: SQLAlchemy db session
        match_date: datetime.date object

    Returns:
        list of DailyStar objects created
    """
    from models import User, Match, MatchPrediction, DailyStar
    from datetime import datetime, timezone

    # Find all closed matches on this date
    day_matches = Match.query.filter(
        db.func.date(Match.match_time) == match_date,
        Match.status == "closed"
    ).all()

    if not day_matches:
        return []

    match_ids = [m.id for m in day_matches]

    # Get all users who made predictions for these matches
    users = User.query.filter(User.is_admin == False).all()

    user_scores = {}
    for user in users:
        total = db.session.query(
            db.func.coalesce(db.func.sum(MatchPrediction.points), 0)
        ).filter(
            MatchPrediction.user_id == user.id,
            MatchPrediction.match_id.in_(match_ids)
        ).scalar()
        user_scores[user.id] = total

    if not user_scores:
        return []

    max_score = max(user_scores.values())
    if max_score == 0:
        return []

    # Award to all users with max score (shared)
    stars = []
    for user_id, score in user_scores.items():
        if score == max_score:
            # Check if already awarded for this date
            existing = DailyStar.query.filter_by(
                match_date=match_date, user_id=user_id
            ).first()
            if not existing:
                star = DailyStar(
                    match_date=match_date,
                    user_id=user_id,
                    points_that_day=score,
                    awarded_at=datetime.now(timezone.utc).replace(tzinfo=None)
                )
                db.session.add(star)
                stars.append(star)

    db.session.commit()
    return stars


def snapshot_leaderboard_ranks(db):
    """Copy current ranks to users.previous_rank before scoring changes."""
    leaderboard = get_leaderboard()
    from models import User
    try:
        for entry in leaderboard:
            user = User.query.get(entry["user_id"])
            if user and hasattr(user, 'previous_rank'):
                user.previous_rank = entry["rank"]
        db.session.commit()
    except Exception:
        pass  # Column may not exist yet; run init_db.py to migrate


def get_leaderboard():
    """
    Get current leaderboard sorted by total score desc.

    Returns:
        list of dicts with user info and scores
    """
    from models import User

    users = User.query.filter_by(is_admin=False).all()
    leaderboard = []

    for user in users:
        leaderboard.append({
            "nickname": user.nickname,
            "user_id": user.id,
            "p1": user.get_p1_score(),
            "p2": user.get_p2_score(),
            "p3": user.get_p3_score(),
            "p4": user.get_p4_score(),
            "total": user.get_total_score(),
            "star_count": user.get_daily_star_count(),
            "previous_rank": getattr(user, 'previous_rank', None),
        })

    leaderboard.sort(key=lambda x: (-x["total"], x["nickname"]))

    # Add rank
    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1

    return leaderboard


def _get_result(score_a, score_b):
    """Return 'win_a', 'draw', or 'win_b'"""
    if score_a > score_b:
        return "win_a"
    elif score_a < score_b:
        return "win_b"
    else:
        return "draw"
