from __future__ import annotations

import json

from app.video_studio import director


def test_director_plan_is_validated_as_editable_scene(monkeypatch):
    monkeypatch.setattr(
        director,
        "_call_multimodal_text_model",
        lambda **_kwargs: json.dumps(
            {
                "scene": {
                    "background": "#edf2ff",
                    "camera": {
                        "position": {"x": 6, "y": 4, "z": 8},
                        "target": {"x": 0, "y": 1, "z": 0},
                        "focal_length": 35,
                    },
                    "objects": [
                        {
                            "id": "talent-1",
                            "name": "Presenter",
                            "shape": "mannequin",
                            "position": {"x": 0, "y": 0, "z": 0},
                            "scale": {"x": 1, "y": 1, "z": 1},
                            "color": "#8b5cf6",
                        }
                    ],
                }
            }
        ),
    )

    result = director.generate_director_plan("A presenter beside the product")
    assert result.scene.objects[0].shape == "mannequin"
    assert result.scene.camera.focal_length == 35
