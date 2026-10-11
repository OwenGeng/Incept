import os
import pytest

# Keep the suite hermetic: tests must not depend on a developer's local .env.
# Process env takes precedence over .env, so these placeholders also keep real
# credentials out of test runs.
os.environ.setdefault("VERTEX_AI_ENABLED", "true")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")


@pytest.fixture(autouse=True)
def no_live_pi_provider_requests(monkeypatch):
    # A forgotten old-engine mock after migration must fail locally, never
    # reach Google ADC/network or consume a real provider request.
    from app.video_studio import pi_agent
    def forbidden(*args, **kwargs):
        raise AssertionError('Live Pi provider requests are forbidden in the test suite; mock the provider boundary.')
    monkeypatch.setattr(pi_agent, 'model_response', forbidden)
