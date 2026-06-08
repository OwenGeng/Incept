import os

from google import genai

from app.core.config import settings


class GeminiService:
    def __init__(self) -> None:
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.google_cloud_project)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.google_cloud_location)
        os.environ.setdefault(
            "GOOGLE_GENAI_USE_ENTERPRISE",
            "True" if settings.google_genai_use_enterprise else "False",
        )
        self.client = genai.Client()

    def generate_weekly_brief(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        return response.text or ""

