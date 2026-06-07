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

    # Scoring rules
    # Project 1: Champion + 4 individual awards (Golden Boot/Ball/Glove, Best Young Player)
    P1_CHAMPION_PTS = 8
    P1_GOLDEN_BOOT_PTS = 3
    P1_GOLDEN_BALL_PTS = 3
    P1_GOLDEN_GLOVE_PTS = 3
    P1_BEST_YOUNG_PLAYER_PTS = 3
    P1_MAX_PTS = 20  # 8 + 3*4

    # Project 2: Group stage ranking (12 groups, 1pt per group)
    P2_GROUP_PTS = 1
    P2_MAX_PTS = 12  # 12 groups x 1 pt

    # Project 3: Semifinal predictions (4 zones, was P2)
    P3_PER_TEAM_PTS = 2
    P3_MAX_PTS = 8

    # Project 4: Match predictions (was P3)
    P4_EXACT_PTS = 3
    P4_RESULT_PTS = 1
    P4_FINAL_MULTIPLIER = 2
    P4_BIG_MATCH_GOALS = 5  # total goals >= this
    P4_BIG_MATCH_DIFF = 3  # goal diff >= this
    P4_BIG_MATCH_PTS = 5  # exact prediction bonus points
