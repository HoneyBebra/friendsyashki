import subprocess
import sys
from pathlib import Path

MESSENGER_ROOT = Path(__file__).parent.parent


class TestMigrations:
    def test_upgrade_on_clean_db(self, alembic_env: dict[str, str]) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "base"],
            cwd=str(MESSENGER_ROOT),
            env=alembic_env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Downgrade failed: {result.stderr}"

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(MESSENGER_ROOT),
            env=alembic_env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Upgrade failed: {result.stderr}"

    def test_rerun_upgrade_is_idempotent(self, alembic_env: dict[str, str]) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(MESSENGER_ROOT),
            env=alembic_env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Re-run failed: {result.stderr}"
