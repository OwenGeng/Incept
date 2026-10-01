import os

# Keep the suite hermetic: tests must not depend on a developer's local .env.
# Process env takes precedence over .env, so these placeholders also keep real
# credentials out of test runs.
os.environ.setdefault("VERTEX_AI_ENABLED", "true")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
