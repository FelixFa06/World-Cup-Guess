import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "world-cup-guess-2026-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'guess.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Admin account
    ADMIN_NICKNAME = os.environ.get("ADMIN_NICKNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

    # Tournament config
    TOURNAMENT_START = "2026-06-11"
    TOURNAMENT_END = "2026-07-19"

    # Scoring rules
    P1_CHAMPION_PTS = 5
    P1_GOLDEN_BOOT_PTS = 5
    P1_GOLDEN_BALL_PTS = 5
    P2_PER_TEAM_PTS = 2
    P2_MAX_PTS = 8
    P3_EXACT_PTS = 3
    P3_RESULT_PTS = 1
    P3_FINAL_MULTIPLIER = 2
    P3_BIG_MATCH_GOALS = 5  # total goals >= this
    P3_BIG_MATCH_DIFF = 3  # goal diff >= this
    P3_BIG_MATCH_PTS = 5  # exact prediction bonus points
