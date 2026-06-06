from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Relationships
    p1_pick = db.relationship("Project1Pick", backref="user", uselist=False)
    p3_pick = db.relationship("Project2Pick", backref="user", uselist=False)  # display: 项目三 (四强)
    group_stage_picks = db.relationship("GroupStagePick", backref="user", lazy="dynamic")
    match_predictions = db.relationship("MatchPrediction", backref="user", lazy="dynamic")
    daily_stars = db.relationship("DailyStar", backref="user", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_total_score(self):
        p1 = self.get_p1_score()
        p2 = self.get_p2_score()
        p3 = self.get_p3_score()
        p4 = self.get_p4_score()
        return p1 + p2 + p3 + p4

    def get_p1_score(self):
        return self.p1_pick.score if self.p1_pick else 0

    def get_p2_score(self):
        """Project 2: Group stage ranking score"""
        return sum(gp.score or 0 for gp in self.group_stage_picks)

    def get_p3_score(self):
        """Project 3: Semifinal prediction score (四强)"""
        return self.p3_pick.score if self.p3_pick else 0

    def get_p4_score(self):
        """Project 4: Match prediction score"""
        return sum(mp.points or 0 for mp in self.match_predictions)

    def get_daily_star_count(self):
        return self.daily_stars.count()


class Match(db.Model):
    __tablename__ = "matches"

    id = db.Column(db.Integer, primary_key=True)
    round_name = db.Column(db.String(10), nullable=False)  # R32/R16/QF/SF/3RD/FINAL
    match_order = db.Column(db.Integer, nullable=False)  # 1-32
    team_a = db.Column(db.String(100), nullable=False)
    team_b = db.Column(db.String(100), nullable=False)
    match_time = db.Column(db.DateTime, nullable=False)  # Beijing time
    score_a = db.Column(db.Integer, nullable=True)  # real score, NULL before match
    score_b = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default="upcoming")  # upcoming/open/closed

    # Relationships
    predictions = db.relationship("MatchPrediction", backref="match", lazy="dynamic")

    @property
    def is_final(self):
        return self.round_name == "FINAL"

    @property
    def is_third_place(self):
        return self.round_name == "3RD"

    @property
    def multiplier(self):
        """Final match: x2 points"""
        return 2 if self.is_final else 1

    @property
    def total_goals(self):
        if self.score_a is None or self.score_b is None:
            return None
        return self.score_a + self.score_b

    @property
    def goal_diff(self):
        if self.score_a is None or self.score_b is None:
            return None
        return abs(self.score_a - self.score_b)

    @property
    def is_big_match(self):
        """Total goals >= 5 or goal diff >= 3"""
        tg = self.total_goals
        gd = self.goal_diff
        if tg is None or gd is None:
            return False
        return tg >= 5 or gd >= 3


class Project1Pick(db.Model):
    __tablename__ = "project1_picks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    champion_team = db.Column(db.String(100), nullable=False)
    golden_boot_player = db.Column(db.String(100), nullable=False)
    golden_ball_player = db.Column(db.String(100), nullable=False)
    score = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


class GroupStagePick(db.Model):
    """Project 2: Group stage ranking prediction — predict 1st & 2nd for each group."""
    __tablename__ = "group_stage_picks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_name = db.Column(db.String(2), nullable=False)  # A-L
    first_place = db.Column(db.String(100), nullable=False)
    second_place = db.Column(db.String(100), nullable=False)
    score = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "group_name", name="uq_user_group"),
    )


class Project2Pick(db.Model):
    """Project 3 (display): Semifinal prediction — pick 1 team from each of 4 zones."""
    __tablename__ = "project2_picks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    zone_a_team = db.Column(db.String(100), nullable=False)
    zone_b_team = db.Column(db.String(100), nullable=False)
    zone_c_team = db.Column(db.String(100), nullable=False)
    zone_d_team = db.Column(db.String(100), nullable=False)
    score = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


class MatchPrediction(db.Model):
    __tablename__ = "match_predictions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey("matches.id"), nullable=False)
    pred_score_a = db.Column(db.Integer, nullable=False)
    pred_score_b = db.Column(db.Integer, nullable=False)
    points = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "match_id", name="uq_user_match"),
    )


class DailyStar(db.Model):
    __tablename__ = "daily_stars"

    id = db.Column(db.Integer, primary_key=True)
    match_date = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    points_that_day = db.Column(db.Integer, default=0)
    awarded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
