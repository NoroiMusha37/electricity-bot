from datetime import time

import pytest

from energy_bot.config import Settings


@pytest.fixture
def env(monkeypatch, tmp_path):
    # Run from an empty directory so a developer's local .env is never picked up.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_TOKEN", "1:abc")
    return monkeypatch


def test_comma_separated_lists(env):
    env.setenv("ALLOWED_USER_IDS", "111, 222")
    env.setenv("WARNING_OFFSETS_MINUTES", "45,15")
    s = Settings()
    assert s.ALLOWED_USER_IDS == [111, 222]
    assert s.WARNING_OFFSETS_MINUTES == [45, 15]


def test_json_style_list(env):
    env.setenv("ALLOWED_USER_IDS", "[333]")
    assert Settings().ALLOWED_USER_IDS == [333]


def test_defaults(env):
    env.setenv("ALLOWED_USER_IDS", "1")
    s = Settings()
    assert s.WARNING_OFFSETS_MINUTES == [60, 30]
    assert (s.DEFAULT_QUIET_START, s.DEFAULT_QUIET_END) == (time(23, 0), time(7, 0))
    assert str(s.TZ) == "Europe/Kyiv"
    assert "abc" not in repr(s)


def test_quiet_hours_parsed(env):
    env.setenv("ALLOWED_USER_IDS", "1")
    env.setenv("DEFAULT_QUIET_START", "22:30")
    assert Settings().DEFAULT_QUIET_START == time(22, 30)
