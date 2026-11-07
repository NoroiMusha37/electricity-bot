import pytest

from energy_bot.config import Settings


@pytest.fixture
def env(monkeypatch, tmp_path):
    # Run from an empty directory so a developer's local .env is never picked up.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_TOKEN", "1:secret-token")
    return monkeypatch


def test_comma_separated_lists(env):
    env.setenv("ALLOWED_USER_IDS", "111, 222")
    env.setenv("WARNING_OFFSETS_MINUTES", "45,15")
    settings = Settings()
    assert settings.ALLOWED_USER_IDS == [111, 222]
    assert settings.WARNING_OFFSETS_MINUTES == [45, 15]


def test_json_style_list(env):
    env.setenv("ALLOWED_USER_IDS", "[333]")
    assert Settings().ALLOWED_USER_IDS == [333]


def test_bot_token_never_shown(env):
    env.setenv("ALLOWED_USER_IDS", "1")
    settings = Settings()
    assert "secret-token" not in repr(settings) and "secret-token" not in str(settings.BOT_TOKEN)
    assert settings.BOT_TOKEN.get_secret_value() == "1:secret-token"
