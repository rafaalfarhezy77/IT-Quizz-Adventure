import enum
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


def utcnow():
    return datetime.now(timezone.utc)


class StationMode(enum.Enum):
    NORMAL = "NORMAL"
    MEMBER_ROTATION = "MEMBER_ROTATION"
    BELUM_DIKETAHUI = "BELUM_DIKETAHUI"


class QuestionSetStatus(enum.Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    LOCKED = "LOCKED"


class SessionStatus(enum.Enum):
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class SubmissionStatus(enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    GRADED = "GRADED"
    TIMED_OUT = "TIMED_OUT"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, nullable=False)


class Admin(TimestampMixin, db.Model):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(db.String(80), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(db.String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class Station(TimestampMixin, db.Model):
    __tablename__ = "stations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(100), unique=True, nullable=False)
    mode: Mapped[StationMode] = mapped_column(db.Enum(StationMode), default=StationMode.NORMAL, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    question_sets: Mapped[list["QuestionSet"]] = relationship(back_populates="station")
    sessions: Mapped[list["CompetitionSession"]] = relationship(back_populates="station")


class Group(TimestampMixin, db.Model):
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(db.String(10), unique=True, nullable=False)
    teams: Mapped[list["Team"]] = relationship(back_populates="group")
    sessions: Mapped[list["CompetitionSession"]] = relationship(back_populates="group")


class Team(TimestampMixin, db.Model):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    team_code: Mapped[str] = mapped_column(db.String(30), unique=True, index=True, nullable=False)
    team_name: Mapped[str] = mapped_column(db.String(120), nullable=False)
    school: Mapped[str] = mapped_column(db.String(160), nullable=False)
    group_id: Mapped[int] = mapped_column(db.ForeignKey("groups.id", ondelete="RESTRICT"), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    group: Mapped["Group"] = relationship(back_populates="teams")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="team")


class QuestionSet(TimestampMixin, db.Model):
    __tablename__ = "question_sets"
    __table_args__ = (UniqueConstraint("station_id", "code", name="uq_question_set_station_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(db.ForeignKey("stations.id", ondelete="RESTRICT"), index=True, nullable=False)
    code: Mapped[str] = mapped_column(db.String(20), nullable=False)
    name: Mapped[str] = mapped_column(db.String(100), nullable=False)
    status: Mapped[QuestionSetStatus] = mapped_column(db.Enum(QuestionSetStatus), default=QuestionSetStatus.DRAFT, nullable=False)
    station: Mapped["Station"] = relationship(back_populates="question_sets")
    questions: Mapped[list["Question"]] = relationship(back_populates="question_set", order_by="Question.order_number")
    sessions: Mapped[list["CompetitionSession"]] = relationship(back_populates="question_set")


class Question(TimestampMixin, db.Model):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("question_set_id", "order_number", name="uq_question_set_order"),
        CheckConstraint("weight >= 0", name="ck_question_weight_nonnegative"),
        CheckConstraint("correct_answer IN ('A', 'B', 'C', 'D')", name="ck_question_correct_answer"),
        CheckConstraint("order_number > 0", name="ck_question_order_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    question_set_id: Mapped[int] = mapped_column(db.ForeignKey("question_sets.id", ondelete="RESTRICT"), index=True, nullable=False)
    text: Mapped[str] = mapped_column(db.Text, nullable=False)
    option_a: Mapped[str] = mapped_column(db.Text, nullable=False)
    option_b: Mapped[str] = mapped_column(db.Text, nullable=False)
    option_c: Mapped[str] = mapped_column(db.Text, nullable=False)
    option_d: Mapped[str] = mapped_column(db.Text, nullable=False)
    correct_answer: Mapped[str] = mapped_column(db.String(1), nullable=False)
    weight: Mapped[float] = mapped_column(default=1.0, nullable=False)
    order_number: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, index=True, nullable=False)
    external_id: Mapped[str | None] = mapped_column(db.String(64), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(db.String(100), nullable=True)
    member_number: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    question_set: Mapped["QuestionSet"] = relationship(back_populates="questions")
    answers: Mapped[list["Answer"]] = relationship(back_populates="question")


class CompetitionSession(TimestampMixin, db.Model):
    __tablename__ = "sessions"
    __table_args__ = (CheckConstraint("duration_seconds > 0", name="ck_session_duration_positive"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(db.ForeignKey("stations.id", ondelete="RESTRICT"), index=True, nullable=False)
    group_id: Mapped[int] = mapped_column(db.ForeignKey("groups.id", ondelete="RESTRICT"), index=True, nullable=False)
    question_set_id: Mapped[int] = mapped_column(db.ForeignKey("question_sets.id", ondelete="RESTRICT"), index=True, nullable=False)
    status: Mapped[SessionStatus] = mapped_column(db.Enum(SessionStatus), default=SessionStatus.WAITING, index=True, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[int] = mapped_column(nullable=False)
    station: Mapped["Station"] = relationship(back_populates="sessions")
    group: Mapped["Group"] = relationship(back_populates="sessions")
    question_set: Mapped["QuestionSet"] = relationship(back_populates="sessions")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="session")


class Submission(TimestampMixin, db.Model):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("session_id", "team_id", name="uq_submission_session_team"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(db.ForeignKey("sessions.id", ondelete="RESTRICT"), index=True, nullable=False)
    team_id: Mapped[int] = mapped_column(db.ForeignKey("teams.id", ondelete="RESTRICT"), index=True, nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(db.Enum(SubmissionStatus), default=SubmissionStatus.IN_PROGRESS, nullable=False)
    current_member: Mapped[int] = mapped_column(default=1, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    session: Mapped["CompetitionSession"] = relationship(back_populates="submissions")
    team: Mapped["Team"] = relationship(back_populates="submissions")
    answers: Mapped[list["Answer"]] = relationship(back_populates="submission")
    score: Mapped["Score | None"] = relationship(back_populates="submission", uselist=False)


class Answer(TimestampMixin, db.Model):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("submission_id", "question_id", name="uq_answer_submission_question"),
        CheckConstraint(
            "selected_answer IS NULL OR selected_answer IN ('A', 'B', 'C', 'D')",
            name="ck_answer_selected_answer",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(db.ForeignKey("submissions.id", ondelete="CASCADE"), index=True, nullable=False)
    question_id: Mapped[int] = mapped_column(db.ForeignKey("questions.id", ondelete="RESTRICT"), index=True, nullable=False)
    selected_answer: Mapped[str | None] = mapped_column(db.String(1), nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(nullable=True)
    points_awarded: Mapped[float | None] = mapped_column(nullable=True)
    submission: Mapped["Submission"] = relationship(back_populates="answers")
    question: Mapped["Question"] = relationship(back_populates="answers")


class Score(TimestampMixin, db.Model):
    __tablename__ = "scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(db.ForeignKey("submissions.id", ondelete="CASCADE"), unique=True, nullable=False)
    raw_score: Mapped[float] = mapped_column(default=0, nullable=False)
    time_bonus: Mapped[float] = mapped_column(default=0, nullable=False)
    final_score: Mapped[float] = mapped_column(default=0, index=True, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(nullable=False)
    submission: Mapped["Submission"] = relationship(back_populates="score")
