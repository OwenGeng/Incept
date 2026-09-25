from __future__ import annotations

import json

from app.incept.vertex_generation import _call_multimodal_text_model

from .models import DirectorPlanResponse, DirectorScene


def generate_director_plan(prompt: str) -> DirectorPlanResponse:
    raw = _call_multimodal_text_model(
        prompt=f"""You are LinglongLab Video's previsualization director.
Turn the user's scene description into a small, editable 3D blocking scene. Use simple geometry only.
Return one JSON object only:
{{
  "scene": {{
    "background": "#RRGGBB",
    "camera": {{
      "position": {{"x": 6, "y": 4, "z": 8}},
      "target": {{"x": 0, "y": 1, "z": 0}},
      "focal_length": 35
    }},
    "objects": [
      {{
        "id": "short-stable-id",
        "name": "visible object name",
        "shape": "cube|sphere|cylinder|mannequin",
        "position": {{"x": 0, "y": 0.5, "z": 0}},
        "scale": {{"x": 1, "y": 1, "z": 1}},
        "color": "#RRGGBB"
      }}
    ]
  }}
}}
Use at most 20 objects. Put objects on or above y=0. Keep the camera outside objects and aimed at the action.

User scene request:
{prompt}""",
        parts=[],
        json_response=True,
    )
    value = raw.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    payload = json.loads(value)
    response = DirectorPlanResponse.model_validate(payload)
    response.scene = DirectorScene.model_validate(response.scene)
    return response
