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


class PackageStatus(enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    ARCHIVED = "ARCHIVED"


class ChallengeType(enum.Enum):
    QUIZ = "quiz"
    HARDWARE_BUILD_CHALLENGE = "hardware_build_challenge"


class MappingStrategy(enum.Enum):
    SAME_FOR_ALL = "SAME_FOR_ALL"
    BY_GROUP = "BY_GROUP"
    MANUAL_PER_SESSION = "MANUAL_PER_SESSION"
    RANDOM_BALANCED = "RANDOM_BALANCED"


class HardwareVerificationStatus(enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    SCORED = "SCORED"


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
    challenge_packages: Mapped[list["ChallengePackage"]] = relationship(back_populates="station")


class Group(TimestampMixin, db.Model):
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(db.String(10), unique=True, nullable=False)
    teams: Mapped[list["Team"]] = relationship(back_populates="group")
    sessions: Mapped[list["CompetitionSession"]] = relationship(back_populates="group")
    mappings: Mapped[list["GroupPackageMapping"]] = relationship(back_populates="group")


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
        CheckConstraint("order_number > 0", name="ck_question_order_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    question_set_id: Mapped[int] = mapped_column(db.ForeignKey("question_sets.id", ondelete="RESTRICT"), index=True, nullable=False)
    question_type: Mapped[str] = mapped_column(db.String(30), default="multiple_choice", nullable=False)
    stage: Mapped[int] = mapped_column(db.Integer, default=1, nullable=False)
    text: Mapped[str] = mapped_column(db.Text, nullable=False)
    case_study: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    option_a: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    option_b: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    option_c: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    option_d: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    option_e: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    correct_answer: Mapped[str] = mapped_column(db.String(255), nullable=False)
    accepted_answers: Mapped[list | None] = mapped_column(db.JSON, nullable=True)
    weight: Mapped[float] = mapped_column(default=1.0, nullable=False)
    order_number: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, index=True, nullable=False)
    external_id: Mapped[str | None] = mapped_column(db.String(64), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(db.String(100), nullable=True)
    member_number: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    question_set: Mapped["QuestionSet"] = relationship(back_populates="questions")
    answers: Mapped[list["Answer"]] = relationship(back_populates="question")


class ChallengePackage(TimestampMixin, db.Model):
    __tablename__ = "challenge_packages"
    __table_args__ = (
        UniqueConstraint("station_id", "package_code", name="uq_challenge_package_station_code"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(db.ForeignKey("stations.id", ondelete="RESTRICT"), index=True, nullable=False)
    package_code: Mapped[str] = mapped_column(db.String(30), nullable=False)  # Contoh: 'Paket 01', 'Paket 02'
    title: Mapped[str] = mapped_column(db.String(200), nullable=False)
    description: Mapped[str] = mapped_column(db.Text, nullable=False)  # Studi kasus / narasi
    instructions: Mapped[str] = mapped_column(db.Text, nullable=False)  # Petunjuk pengerjaan
    challenge_type: Mapped[str] = mapped_column(db.String(50), default="hardware_build_challenge", nullable=False)
    external_tool_url: Mapped[str | None] = mapped_column(db.String(500), nullable=True)  # URL BuildCores
    rules_config: Mapped[dict | None] = mapped_column(db.JSON, nullable=True)  # Batasan build PC
    scoring_config: Mapped[dict | None] = mapped_column(db.JSON, nullable=True)  # Konfigurasi pembobotan nilai
    duration_minutes: Mapped[int] = mapped_column(default=30, nullable=False)
    status: Mapped[PackageStatus] = mapped_column(db.Enum(PackageStatus), default=PackageStatus.DRAFT, index=True, nullable=False)
    question_set_id: Mapped[int | None] = mapped_column(db.ForeignKey("question_sets.id", ondelete="SET NULL"), nullable=True)

    station: Mapped["Station"] = relationship(back_populates="challenge_packages")
    question_set: Mapped["QuestionSet | None"] = relationship()
    mappings: Mapped[list["GroupPackageMapping"]] = relationship(back_populates="package")
    sessions: Mapped[list["CompetitionSession"]] = relationship(back_populates="package")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="package")


class GroupPackageMapping(TimestampMixin, db.Model):
    __tablename__ = "group_package_mappings"
    __table_args__ = (
        UniqueConstraint("station_id", "group_id", "session_id", name="uq_group_package_station_group_session"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(db.ForeignKey("stations.id", ondelete="RESTRICT"), index=True, nullable=False)
    group_id: Mapped[int] = mapped_column(db.ForeignKey("groups.id", ondelete="RESTRICT"), index=True, nullable=False)
    package_id: Mapped[int] = mapped_column(db.ForeignKey("challenge_packages.id", ondelete="RESTRICT"), index=True, nullable=False)
    session_id: Mapped[int | None] = mapped_column(db.ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=True)
    strategy: Mapped[str] = mapped_column(db.String(30), default="BY_GROUP", nullable=False)

    station: Mapped["Station"] = relationship()
    group: Mapped["Group"] = relationship(back_populates="mappings")
    package: Mapped["ChallengePackage"] = relationship(back_populates="mappings")
    session: Mapped["CompetitionSession | None"] = relationship()


class CompetitionSession(TimestampMixin, db.Model):
    __tablename__ = "sessions"
    __table_args__ = (CheckConstraint("duration_seconds > 0", name="ck_session_duration_positive"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(db.ForeignKey("stations.id", ondelete="RESTRICT"), index=True, nullable=False)
    group_id: Mapped[int] = mapped_column(db.ForeignKey("groups.id", ondelete="RESTRICT"), index=True, nullable=False)
    question_set_id: Mapped[int | None] = mapped_column(db.ForeignKey("question_sets.id", ondelete="RESTRICT"), index=True, nullable=True)
    package_id: Mapped[int | None] = mapped_column(db.ForeignKey("challenge_packages.id", ondelete="RESTRICT"), index=True, nullable=True)
    status: Mapped[SessionStatus] = mapped_column(db.Enum(SessionStatus), default=SessionStatus.WAITING, index=True, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[int] = mapped_column(nullable=False)
    rotation_number: Mapped[int | None] = mapped_column(db.Integer, default=1, nullable=True)

    station: Mapped["Station"] = relationship(back_populates="sessions")
    group: Mapped["Group"] = relationship(back_populates="sessions")
    question_set: Mapped["QuestionSet | None"] = relationship(back_populates="sessions")
    package: Mapped["ChallengePackage | None"] = relationship(back_populates="sessions")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="session")


class Submission(TimestampMixin, db.Model):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("session_id", "team_id", name="uq_submission_session_team"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(db.ForeignKey("sessions.id", ondelete="RESTRICT"), index=True, nullable=False)
    team_id: Mapped[int] = mapped_column(db.ForeignKey("teams.id", ondelete="RESTRICT"), index=True, nullable=False)
    package_id: Mapped[int | None] = mapped_column(db.ForeignKey("challenge_packages.id", ondelete="RESTRICT"), index=True, nullable=True)
    package_snapshot: Mapped[dict | None] = mapped_column(db.JSON, nullable=True)
    submission_type: Mapped[str] = mapped_column(db.String(50), default="quiz", nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(db.Enum(SubmissionStatus), default=SubmissionStatus.IN_PROGRESS, nullable=False)
    current_member: Mapped[int] = mapped_column(default=1, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    session: Mapped["CompetitionSession"] = relationship(back_populates="submissions")
    team: Mapped["Team"] = relationship(back_populates="submissions")
    package: Mapped["ChallengePackage | None"] = relationship(back_populates="submissions")
    answers: Mapped[list["Answer"]] = relationship(back_populates="submission")
    score: Mapped["Score | None"] = relationship(back_populates="submission", uselist=False)
    hardware_submission: Mapped["HardwareSubmission | None"] = relationship(back_populates="submission", uselist=False, cascade="all, delete-orphan")
    networking_submission: Mapped["NetworkingSubmission | None"] = relationship(back_populates="submission", uselist=False, cascade="all, delete-orphan")


class HardwareSubmission(TimestampMixin, db.Model):
    __tablename__ = "hardware_submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(db.ForeignKey("submissions.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    buildcores_url: Mapped[str | None] = mapped_column(db.String(500), nullable=True)
    total_price: Mapped[float | None] = mapped_column(nullable=True)
    currency: Mapped[str] = mapped_column(db.String(10), default="USD", nullable=False)
    cpu_name: Mapped[str | None] = mapped_column(db.String(150), nullable=True)
    cpu_score: Mapped[float | None] = mapped_column(nullable=True)
    gpu_name: Mapped[str | None] = mapped_column(db.String(150), nullable=True)
    gpu_score: Mapped[float | None] = mapped_column(nullable=True)
    ram_capacity_gb: Mapped[float | None] = mapped_column(nullable=True)
    storage_capacity_gb: Mapped[float | None] = mapped_column(nullable=True)
    psu_name: Mapped[str | None] = mapped_column(db.String(150), nullable=True)
    components_summary: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    build_rationale: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    confirmation_checked: Mapped[bool] = mapped_column(default=False, nullable=False)
    verification_status: Mapped[str] = mapped_column(db.String(30), default="DRAFT", index=True, nullable=False)
    is_compatible: Mapped[bool | None] = mapped_column(nullable=True)
    budget_compliant: Mapped[bool | None] = mapped_column(nullable=True)
    cpu_target_met: Mapped[bool | None] = mapped_column(nullable=True)
    gpu_target_met: Mapped[bool | None] = mapped_column(nullable=True)
    completeness_score: Mapped[float | None] = mapped_column(nullable=True)
    efficiency_score: Mapped[float | None] = mapped_column(nullable=True)
    provisional_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    verified_score: Mapped[float | None] = mapped_column(nullable=True)
    score_breakdown: Mapped[dict | None] = mapped_column(db.JSON, nullable=True)
    reviewer_notes: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    verified_by_admin_id: Mapped[int | None] = mapped_column(db.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)

    submission: Mapped["Submission"] = relationship(back_populates="hardware_submission")
    verified_by_admin: Mapped["Admin | None"] = relationship()
    audits: Mapped[list["HardwareSubmissionAudit"]] = relationship(back_populates="hardware_submission", cascade="all, delete-orphan", order_by="HardwareSubmissionAudit.created_at.desc()")

    @property
    def final_score(self) -> float | None:
        return self.verified_score

    @final_score.setter
    def final_score(self, value: float | None):
        self.verified_score = value

    @property
    def screenshot_filename(self) -> str | None:
        return self.screenshot_path

    @screenshot_filename.setter
    def screenshot_filename(self, value: str | None):
        self.screenshot_path = value

    @property
    def team_id(self) -> int | None:
        return self.submission.team_id if self.submission else None

    @property
    def session_id(self) -> int | None:
        return self.submission.session_id if self.submission else None

    @property
    def package_id(self) -> int | None:
        return self.submission.package_id if self.submission else None


class HardwareSubmissionAudit(TimestampMixin, db.Model):
    __tablename__ = "hardware_submission_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    hardware_submission_id: Mapped[int] = mapped_column(db.ForeignKey("hardware_submissions.id", ondelete="CASCADE"), index=True, nullable=False)
    admin_id: Mapped[int | None] = mapped_column(db.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(db.String(50), nullable=False)
    old_values: Mapped[dict | None] = mapped_column(db.JSON, nullable=True)
    new_values: Mapped[dict | None] = mapped_column(db.JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(db.Text, nullable=True)

    hardware_submission: Mapped["HardwareSubmission"] = relationship(back_populates="audits")
    admin: Mapped["Admin | None"] = relationship()

    @property
    def changed_by(self) -> int | None:
        return self.admin_id

    @property
    def new_score(self) -> float | None:
        return (self.new_values or {}).get("verified_score")

    @property
    def old_score(self) -> float | None:
        return (self.old_values or {}).get("verified_score")

    @property
    def submission_id(self) -> int:
        return self.hardware_submission_id


class Answer(TimestampMixin, db.Model):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("submission_id", "question_id", name="uq_answer_submission_question"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(db.ForeignKey("submissions.id", ondelete="CASCADE"), index=True, nullable=False)
    question_id: Mapped[int] = mapped_column(db.ForeignKey("questions.id", ondelete="RESTRICT"), index=True, nullable=False)
    selected_answer: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    text_answer: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    review_status: Mapped[str] = mapped_column(db.String(30), default="AUTO_GRADED", nullable=False)
    facilitator_notes: Mapped[str | None] = mapped_column(db.Text, nullable=True)
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


class NetworkingSubmission(TimestampMixin, db.Model):
    __tablename__ = "networking_submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(db.ForeignKey("submissions.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    current_stage: Mapped[int] = mapped_column(default=1, nullable=False)

    stage_1_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stage_1_submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stage_1_duration_seconds: Mapped[int] = mapped_column(default=300, nullable=False)
    stage_1_score: Mapped[float] = mapped_column(default=0.0, nullable=False)

    stage_2_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stage_2_submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stage_2_duration_seconds: Mapped[int] = mapped_column(default=600, nullable=False)
    stage_2_score: Mapped[float] = mapped_column(default=0.0, nullable=False)

    stage_3_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stage_3_submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stage_3_duration_seconds: Mapped[int] = mapped_column(default=900, nullable=False)
    stage_3_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    stage_3_correct_count: Mapped[int] = mapped_column(default=0, nullable=False)

    time_bonus: Mapped[float] = mapped_column(default=0.0, nullable=False)
    penalty: Mapped[float] = mapped_column(default=0.0, nullable=False)
    provisional_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    final_score: Mapped[float | None] = mapped_column(nullable=True)

    has_stamp: Mapped[bool] = mapped_column(default=False, nullable=False)
    verification_status: Mapped[str] = mapped_column(db.String(30), default="LOBBY", index=True, nullable=False)

    session_token: Mapped[str | None] = mapped_column(db.String(64), nullable=True)
    facilitator_notes: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    verified_by_admin_id: Mapped[int | None] = mapped_column(db.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)

    submission: Mapped["Submission"] = relationship(back_populates="networking_submission")
    verified_by_admin: Mapped["Admin | None"] = relationship()
    audits: Mapped[list["NetworkingSubmissionAudit"]] = relationship(back_populates="networking_submission", cascade="all, delete-orphan", order_by="NetworkingSubmissionAudit.created_at.desc()")


class NetworkingSubmissionAudit(TimestampMixin, db.Model):
    __tablename__ = "networking_submission_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    networking_submission_id: Mapped[int] = mapped_column(db.ForeignKey("networking_submissions.id", ondelete="CASCADE"), index=True, nullable=False)
    admin_id: Mapped[int | None] = mapped_column(db.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(db.String(50), nullable=False)
    old_values: Mapped[dict | None] = mapped_column(db.JSON, nullable=True)
    new_values: Mapped[dict | None] = mapped_column(db.JSON, nullable=True)
    reason: Mapped[str] = mapped_column(db.Text, nullable=False)

    networking_submission: Mapped["NetworkingSubmission"] = relationship(back_populates="audits")
    admin: Mapped["Admin | None"] = relationship()
