import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_seed_demo_users_only_creates_system_users_without_workspace_content(tmp_path: Path):
    data_dir = tmp_path / "data"
    avatars_dir = tmp_path / "avatars"
    avatars_dir.mkdir()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["MIANOTES_DATA_DIR"] = str(data_dir)
    env["MIANOTES_STORAGE_CONFIG_PATH"] = str(tmp_path / "workspaces.json")
    env.pop("MIANOTES_DATABASE_URL", None)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/seed_demo.py",
            "--admin-email",
            "admin@example.com",
            "--admin-name",
            "Admin User",
            "--avatars-dir",
            str(avatars_dir),
            "--demo-user-count",
            "0",
            "--users-only",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "Seeded 0 demo users and admin admin@example.com. "
        "Imported 0 existing workspace users, mapped 0 duplicate emails, "
        "and updated 0 workspace references."
    )

    system_database = data_dir / "system.db"
    workspace_database = data_dir / ".mianotes" / "mia.db"
    assert system_database.exists()
    assert not workspace_database.exists()

    with sqlite3.connect(system_database) as connection:
        users = connection.execute("SELECT email, name, is_admin FROM users").fetchall()
        original_password_hash = connection.execute(
            "SELECT password_hash FROM users WHERE email = ?",
            ("admin@example.com",),
        ).fetchone()[0]
        original_master_hash = connection.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("master_password_hash",),
        ).fetchone()[0]

    assert users == [("admin@example.com", "Admin User", 1)]

    preserved = subprocess.run(
        [
            sys.executable,
            "scripts/seed_demo.py",
            "--admin-email",
            "admin@example.com",
            "--admin-name",
            "Admin User",
            "--avatars-dir",
            str(avatars_dir),
            "--demo-user-count",
            "0",
            "--password",
            "changed-password",
            "--users-only",
            "--preserve-existing-passwords",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert preserved.returncode == 0, preserved.stderr

    with sqlite3.connect(system_database) as connection:
        next_password_hash = connection.execute(
            "SELECT password_hash FROM users WHERE email = ?",
            ("admin@example.com",),
        ).fetchone()[0]
        next_master_hash = connection.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("master_password_hash",),
        ).fetchone()[0]

    assert next_password_hash == original_password_hash
    assert next_master_hash == original_master_hash


def test_seed_demo_users_only_syncs_existing_workspace_users(tmp_path: Path):
    data_dir = tmp_path / "data"
    avatars_dir = tmp_path / "avatars"
    avatars_dir.mkdir()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["MIANOTES_DATA_DIR"] = str(data_dir)
    env["MIANOTES_STORAGE_CONFIG_PATH"] = str(tmp_path / "workspaces.json")
    env.pop("MIANOTES_DATABASE_URL", None)

    initial = subprocess.run(
        [
            sys.executable,
            "scripts/seed_demo.py",
            "--admin-email",
            "admin@example.com",
            "--admin-name",
            "Admin User",
            "--avatars-dir",
            str(avatars_dir),
            "--demo-user-count",
            "0",
            "--users-only",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert initial.returncode == 0, initial.stderr

    system_database = data_dir / "system.db"
    with sqlite3.connect(system_database) as connection:
        admin_id = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            ("admin@example.com",),
        ).fetchone()[0]

    workspace_database = data_dir / ".mianotes" / "mia.db"
    workspace_database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(workspace_database) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                name TEXT NOT NULL,
                username TEXT NOT NULL,
                phone TEXT,
                role TEXT,
                avatar_path TEXT,
                is_admin INTEGER NOT NULL,
                password_hash TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE mia_jobs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO users (
                id, email, name, username, is_admin, password_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-admin",
                "admin@example.com",
                "Legacy Admin",
                "legacy-admin",
                1,
                "legacy-admin-password",
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO users (
                id, email, name, username, is_admin, password_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-member",
                "member@example.com",
                "Legacy Member",
                "legacy-member",
                0,
                "legacy-member-password",
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:00",
            ),
        )
        connection.execute("INSERT INTO mia_jobs (id, user_id) VALUES (?, ?)", ("job-admin", "legacy-admin"))
        connection.execute("INSERT INTO mia_jobs (id, user_id) VALUES (?, ?)", ("job-member", "legacy-member"))

    synced = subprocess.run(
        [
            sys.executable,
            "scripts/seed_demo.py",
            "--admin-email",
            "admin@example.com",
            "--admin-name",
            "Admin User",
            "--avatars-dir",
            str(avatars_dir),
            "--demo-user-count",
            "0",
            "--users-only",
            "--preserve-existing-passwords",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert synced.returncode == 0, synced.stderr
    assert "Imported 1 existing workspace users" in synced.stdout
    assert "mapped 1 duplicate emails" in synced.stdout
    assert "updated 1 workspace references" in synced.stdout

    with sqlite3.connect(system_database) as connection:
        users = connection.execute("SELECT id, email FROM users ORDER BY email").fetchall()

    assert users == [
        (admin_id, "admin@example.com"),
        ("legacy-member", "member@example.com"),
    ]

    with sqlite3.connect(workspace_database) as connection:
        job_users = connection.execute(
            "SELECT id, user_id FROM mia_jobs ORDER BY id"
        ).fetchall()

    assert job_users == [
        ("job-admin", admin_id),
        ("job-member", "legacy-member"),
    ]
