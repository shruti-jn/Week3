"""
Unit tests for backend configuration loading.
"""

from pathlib import Path

import pytest

from app.config import get_settings


class TestGetSettings:
    def test_raises_clear_error_when_required_env_var_is_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        get_settings should raise a readable error when required env vars are missing.

        We change CWD to a temp dir (no .env there) and remove VOYAGE_API_KEY from
        os.environ so that pydantic-settings cannot find the key anywhere, forcing
        the ValidationError -> RuntimeError path.
        """
        get_settings.cache_clear()
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        # Move to a temp dir with no .env file so pydantic-settings only reads
        # from environment variables (not from the local backend/.env file, which
        # has real keys and would make the test pass even without the env var).
        monkeypatch.chdir(tmp_path)

        with pytest.raises(RuntimeError, match="VOYAGE_API_KEY"):
            get_settings()

        get_settings.cache_clear()
