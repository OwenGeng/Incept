"""生成能力共享的供应商类型契约。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Keep this list explicit.  Generation adapters have materially different auth,
# request, and asynchronous-result semantics; a free-form provider string would
# make it too easy to accidentally route one provider through another's API.
ProviderKey = Literal["openai", "creatify", "vertex"]


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """执行生成任务时需要的供应商配置。"""

    provider: ProviderKey
    api_key: str
    base_url: str | None = None
    api_secret: str = ""
    project_id: str | None = None
    location: str | None = None
