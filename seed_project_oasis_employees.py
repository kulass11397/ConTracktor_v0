"""Idempotently add ten synthetic employees to Project Oasis for feature testing."""

from __future__ import annotations

import argparse
from pathlib import Path

from app import Database, hash_pin


DEMO_EMPLOYEES = (
    ("OASIS-DEMO-001", "Miguel Santos", "Site Foreman", "Skilled", "1987-02-14", "09170001001", 120000),
    ("OASIS-DEMO-002", "Carlo Mendoza", "Carpenter", "Skilled", "1991-06-22", "09170001002", 95000),
    ("OASIS-DEMO-003", "Ramon Villanueva", "Electrician", "Skilled", "1989-11-05", "09170001003", 110000),
    ("OASIS-DEMO-004", "Joel Navarro", "Plumber", "Skilled", "1993-03-18", "09170001004", 105000),
    ("OASIS-DEMO-005", "Dennis Bautista", "Mason", "Skilled", "1985-08-30", "09170001005", 100000),
    ("OASIS-DEMO-006", "Paolo Garcia", "Painter", "Skilled", "1996-01-12", "09170001006", 90000),
    ("OASIS-DEMO-007", "Arnold Reyes", "Steelman", "Skilled", "1990-09-09", "09170001007", 98000),
    ("OASIS-DEMO-008", "Luis Dela Cruz", "General Laborer", "Labor", "1998-04-27", "09170001008", 75000),
    ("OASIS-DEMO-009", "Mark Flores", "General Laborer", "Labor", "2000-07-16", "09170001009", 70000),
    ("OASIS-DEMO-010", "Eric Ramos", "Helper", "Labor", "1999-12-03", "09170001010", 68000),
)


def seed(db_path: Path) -> tuple[int, int]:
    db = Database(db_path)
    try:
        project = db.one(
            "SELECT id,name FROM projects WHERE LOWER(TRIM(name))='project oasis' ORDER BY id LIMIT 1"
        )
        if not project:
            raise RuntimeError("Project Oasis was not found. Create it first, then run this seeder again.")
        added = skipped = 0
        salt, digest = hash_pin("0000")
        with db.conn:
            for number, name, position, employee_class, birthday, contact, daily_rate in DEMO_EMPLOYEES:
                exists = db.conn.execute(
                    "SELECT 1 FROM employees WHERE employee_no=?", (number,)
                ).fetchone()
                if exists:
                    skipped += 1
                    continue
                db.conn.execute(
                    """INSERT INTO employees(
                           project_id,employee_no,pin_salt,pin_hash,name,position,class,
                           pay_basis,rate_cents,standard_hours,birthday,contact_number,
                           daily_rate_cents,active
                       ) VALUES(?,?,?,?,?,?,?,'Daily',?,8,?,?,?,1)""",
                    (project["id"], number, salt, digest, name, position, employee_class,
                     daily_rate, birthday, contact, daily_rate),
                )
                added += 1
        return added, skipped
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "db", nargs="?", type=Path,
        default=Path(__file__).resolve().with_name("contractor_tracker.db"),
        help="SQLite database to seed (defaults to contractor_tracker.db beside this script)",
    )
    args = parser.parse_args()
    added, skipped = seed(args.db.resolve())
    print(f"Project Oasis demo employees: added {added}, already present {skipped}.")
    print("All synthetic employee kiosk PINs are 0000.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
