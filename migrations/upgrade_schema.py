"""
Idempotent Database Schema Upgrade Script for Mythic 3.0.
Ensures new columns and tables are created safely without altering or deleting existing data.
Supports multi-pos features including Pos Hardware and Pos Networking.
"""
import logging
from sqlalchemy import text
from models import db

logger = logging.getLogger("schema_upgrade")


def upgrade_database_schema(app=None):
    """
    Apply safe schema additions to SQLite database:
    1. Migrate 'questions' and 'answers' tables if check constraints restrict new question types.
    2. Check and add missing columns to 'sessions' and 'submissions'.
    3. Run create_all() to construct new tables if they do not yet exist (networking_submissions, etc).
    """
    def _execute_upgrade():
        with db.engine.connect() as conn:
            # 1. Check if questions table has restrictive check constraint
            res_q = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='questions';")).fetchone()
            if res_q and res_q[0] and "ck_question_correct_answer" in res_q[0]:
                logger.info("Migrating questions table to support multiple_choice A-E, true_false, and short_text...")
                conn.execute(text("PRAGMA foreign_keys = OFF;"))
                conn.execute(text("""
                    CREATE TABLE _new_questions (
                        id INTEGER NOT NULL, 
                        question_set_id INTEGER NOT NULL, 
                        question_type VARCHAR(30) DEFAULT 'multiple_choice' NOT NULL,
                        stage INTEGER DEFAULT 1 NOT NULL,
                        text TEXT NOT NULL, 
                        case_study TEXT,
                        option_a TEXT, 
                        option_b TEXT, 
                        option_c TEXT, 
                        option_d TEXT, 
                        option_e TEXT, 
                        correct_answer VARCHAR(255) NOT NULL, 
                        accepted_answers JSON,
                        weight FLOAT NOT NULL, 
                        order_number INTEGER NOT NULL, 
                        is_active BOOLEAN NOT NULL, 
                        external_id VARCHAR(64), 
                        category VARCHAR(100), 
                        member_number INTEGER, 
                        created_at DATETIME NOT NULL, 
                        updated_at DATETIME NOT NULL, 
                        PRIMARY KEY (id), 
                        CONSTRAINT uq_question_set_order UNIQUE (question_set_id, order_number), 
                        CONSTRAINT ck_question_weight_nonnegative CHECK (weight >= 0), 
                        CONSTRAINT ck_question_order_positive CHECK (order_number > 0), 
                        FOREIGN KEY(question_set_id) REFERENCES question_sets (id) ON DELETE RESTRICT
                    );
                """))
                
                # Check existing columns in questions
                info_q = {row[1] for row in conn.execute(text("PRAGMA table_info(questions);")).fetchall()}
                q_type_expr = "question_type" if "question_type" in info_q else "'multiple_choice'"
                stage_expr = "stage" if "stage" in info_q else "1"
                case_expr = "case_study" if "case_study" in info_q else "NULL"
                opt_e_expr = "option_e" if "option_e" in info_q else "NULL"
                acc_expr = "accepted_answers" if "accepted_answers" in info_q else "NULL"

                conn.execute(text(f"""
                    INSERT INTO _new_questions (
                        id, question_set_id, question_type, stage, text, case_study,
                        option_a, option_b, option_c, option_d, option_e,
                        correct_answer, accepted_answers, weight, order_number, is_active,
                        external_id, category, member_number, created_at, updated_at
                    )
                    SELECT 
                        id, question_set_id, {q_type_expr}, {stage_expr}, text, {case_expr},
                        option_a, option_b, option_c, option_d, {opt_e_expr},
                        correct_answer, {acc_expr}, weight, order_number, is_active,
                        external_id, category, member_number, created_at, updated_at
                    FROM questions;
                """))
                conn.execute(text("DROP TABLE questions;"))
                conn.execute(text("ALTER TABLE _new_questions RENAME TO questions;"))
                conn.execute(text("PRAGMA foreign_keys = ON;"))
                logger.info("Questions table migrated successfully.")
            else:
                # Ensure columns exist if table was already updated
                res = conn.execute(text("PRAGMA table_info(questions);")).fetchall()
                if res:
                    cols = {row[1] for row in res}
                    if "question_type" not in cols:
                        conn.execute(text("ALTER TABLE questions ADD COLUMN question_type VARCHAR(30) DEFAULT 'multiple_choice';"))
                    if "stage" not in cols:
                        conn.execute(text("ALTER TABLE questions ADD COLUMN stage INTEGER DEFAULT 1;"))
                    if "case_study" not in cols:
                        conn.execute(text("ALTER TABLE questions ADD COLUMN case_study TEXT;"))
                    if "option_e" not in cols:
                        conn.execute(text("ALTER TABLE questions ADD COLUMN option_e TEXT;"))
                    if "accepted_answers" not in cols:
                        conn.execute(text("ALTER TABLE questions ADD COLUMN accepted_answers JSON;"))

            # 2. Check if answers table has restrictive check constraint
            res_a = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='answers';")).fetchone()
            if res_a and res_a[0] and "ck_answer_selected_answer" in res_a[0]:
                logger.info("Migrating answers table to support arbitrary answer strings and review status...")
                conn.execute(text("PRAGMA foreign_keys = OFF;"))
                conn.execute(text("""
                    CREATE TABLE _new_answers (
                        id INTEGER NOT NULL, 
                        submission_id INTEGER NOT NULL, 
                        question_id INTEGER NOT NULL, 
                        selected_answer VARCHAR(255), 
                        text_answer TEXT,
                        review_status VARCHAR(30) DEFAULT 'AUTO_GRADED' NOT NULL,
                        facilitator_notes TEXT,
                        is_correct BOOLEAN, 
                        points_awarded FLOAT, 
                        created_at DATETIME NOT NULL, 
                        updated_at DATETIME NOT NULL, 
                        PRIMARY KEY (id), 
                        CONSTRAINT uq_answer_submission_question UNIQUE (submission_id, question_id), 
                        FOREIGN KEY(submission_id) REFERENCES submissions (id) ON DELETE CASCADE, 
                        FOREIGN KEY(question_id) REFERENCES questions (id) ON DELETE RESTRICT
                    );
                """))
                conn.execute(text("""
                    INSERT INTO _new_answers (
                        id, submission_id, question_id, selected_answer, is_correct, points_awarded, created_at, updated_at
                    )
                    SELECT id, submission_id, question_id, selected_answer, is_correct, points_awarded, created_at, updated_at
                    FROM answers;
                """))
                conn.execute(text("DROP TABLE answers;"))
                conn.execute(text("ALTER TABLE _new_answers RENAME TO answers;"))
                conn.execute(text("PRAGMA foreign_keys = ON;"))
                logger.info("Answers table migrated successfully.")
            else:
                res = conn.execute(text("PRAGMA table_info(answers);")).fetchall()
                if res:
                    cols = {row[1] for row in res}
                    if "text_answer" not in cols:
                        conn.execute(text("ALTER TABLE answers ADD COLUMN text_answer TEXT;"))
                    if "review_status" not in cols:
                        conn.execute(text("ALTER TABLE answers ADD COLUMN review_status VARCHAR(30) DEFAULT 'AUTO_GRADED';"))
                    if "facilitator_notes" not in cols:
                        conn.execute(text("ALTER TABLE answers ADD COLUMN facilitator_notes TEXT;"))

            # 3. Check sessions table
            res = conn.execute(text("PRAGMA table_info(sessions);")).fetchall()
            if res:
                cols = {row[1] for row in res}
                if "package_id" not in cols:
                    logger.info("Adding package_id column to sessions table")
                    conn.execute(text("ALTER TABLE sessions ADD COLUMN package_id INTEGER REFERENCES challenge_packages(id);"))
                if "rotation_number" not in cols:
                    logger.info("Adding rotation_number column to sessions table")
                    conn.execute(text("ALTER TABLE sessions ADD COLUMN rotation_number INTEGER DEFAULT 1;"))

            # 4. Check submissions table
            res = conn.execute(text("PRAGMA table_info(submissions);")).fetchall()
            if res:
                cols = {row[1] for row in res}
                if "package_id" not in cols:
                    logger.info("Adding package_id column to submissions table")
                    conn.execute(text("ALTER TABLE submissions ADD COLUMN package_id INTEGER REFERENCES challenge_packages(id);"))
                if "package_snapshot" not in cols:
                    logger.info("Adding package_snapshot column to submissions table")
                    conn.execute(text("ALTER TABLE submissions ADD COLUMN package_snapshot JSON;"))
                if "submission_type" not in cols:
                    logger.info("Adding submission_type column to submissions table")
                    conn.execute(text("ALTER TABLE submissions ADD COLUMN submission_type VARCHAR(50) DEFAULT 'quiz';"))

            conn.commit()

        # Create any newly defined tables (networking_submissions, networking_submission_audits, etc)
        db.create_all()
        logger.info("Idempotent schema upgrade completed successfully.")

    if app:
        with app.app_context():
            _execute_upgrade()
    else:
        _execute_upgrade()


if __name__ == "__main__":
    from quiz_app import create_app
    app = create_app()
    with app.app_context():
        upgrade_database_schema(app)
        print("Upgrade database schema selesai.")
