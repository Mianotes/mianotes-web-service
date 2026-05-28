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
    assert result.stdout.strip() == "Seeded 0 demo users and admin admin@example.com."

    system_database = data_dir / "system.db"
    workspace_database = data_dir / ".mianotes" / "mia.db"
    assert system_database.exists()
    assert not workspace_database.exists()

    with sqlite3.connect(system_database) as connection:
        users = connection.execute("SELECT email, name, is_admin FROM users").fetchall()

    assert users == [("admin@example.com", "Admin User", 1)]
