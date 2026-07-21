import app.sentry
from app.config import settings
from app.sentry import init_sentry


class TestInitSentry:
    def test_no_dsn_configured_by_default(self):
        assert settings.SENTRY_DSN is None

    def test_init_is_noop_when_dsn_unset(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(app.sentry.sentry_sdk, "init", lambda **kwargs: captured.update(kwargs))

        init_sentry()

        assert captured["dsn"] is None

    def test_init_passes_expected_kwargs(self, monkeypatch):
        dsn = "https://public@example.ingest.sentry.io/1"
        captured = {}
        monkeypatch.setattr(app.sentry.sentry_sdk, "init", lambda **kwargs: captured.update(kwargs))
        monkeypatch.setattr(settings, "SENTRY_DSN", dsn)

        init_sentry()

        assert captured["dsn"] == dsn
        assert captured["environment"] == settings.ENVIRONMENT
        assert captured["release"] == settings.APP_VERSION
        assert captured["traces_sample_rate"] == settings.SENTRY_TRACES_SAMPLE_RATE
        assert (
            captured["profile_session_sample_rate"] == settings.SENTRY_PROFILE_SESSION_SAMPLE_RATE
        )
        assert captured["profile_lifecycle"] == "trace"
