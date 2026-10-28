from __future__ import annotations

import re

from ..domain.models import Completion, Prompt, ProviderStatus
from ..ports.ai import AIProvider


class DemoProvider(AIProvider):
    """Offline stand-in so the UI can be tried and tested without any account. Never calls a model."""

    id = "demo"
    label = "체험 모드 (AI 없음)"
    kind = "offline"
    description = "실제 AI를 부르지 않고 화면 흐름만 보여 줍니다. 결과는 입력 일부를 되돌려 준 예시입니다."

    def status(self) -> ProviderStatus:
        return ProviderStatus(True, "오프라인 · 비용 없음")

    def complete(self, prompt: Prompt) -> Completion:
        found = re.search(r"<(passage|paper)>\s*(.*?)\s*</\1>", prompt.user, re.S)
        excerpt = " ".join((found.group(2) if found else prompt.user).split())[:240]
        return Completion(f"[체험 모드 응답] 실제 AI를 연결하면 이 자리에 결과가 나옵니다.\n\n입력 일부: {excerpt}", self.id, "demo")

