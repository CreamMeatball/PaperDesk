from __future__ import annotations

import re

from ..domain.models import Completion, Prompt, ProviderStatus
from ..i18n import _
from ..ports.ai import AIProvider


DEMO_TEXT = {
    "Korean": "[체험 모드] 실제 AI를 연결하면 이 자리에 결과가 나옵니다.",
    "English": "[Demo] Connect an AI in Settings to see real answers here.",
    "Japanese": "[体験モード] 実際のAIを接続すると、ここに結果が表示されます。",
    "Chinese (Simplified)": "[体验模式] 连接真正的 AI 后，结果会显示在这里。",
}


class DemoProvider(AIProvider):
    """Offline stand-in so the UI can be tried and tested without any account. Never calls a model."""

    id = "demo"
    label = _("체험 모드 (AI 없음)")
    kind = "offline"
    supports_images = True
    description = _("실제 AI를 부르지 않고 화면 흐름만 보여 줍니다. 결과는 입력 일부를 되돌려 준 예시입니다.")

    @staticmethod
    def _fake_blocks(user: str) -> str:
        import json

        payload = json.loads(user[user.index("<blocks>") + 8:user.index("</blocks>")])
        return json.dumps({"blocks": [{"id": b["id"], "sentences": [f"[demo] {s}" for s in b["sentences"]]}
                                      for b in payload["blocks"]]}, ensure_ascii=False)

    def status(self) -> ProviderStatus:
        return ProviderStatus(True, _("오프라인 · 비용 없음"))

    def complete(self, prompt: Prompt) -> Completion:
        found = re.search(r"<(passage|paper)>\s*(.*?)\s*</\1>", prompt.user, re.S)
        excerpt = " ".join((found.group(2) if found else prompt.user).split())[:240]
        if '"blocks"' in prompt.user and "<blocks>" in prompt.user:
            return Completion(self._fake_blocks(prompt.user), self.id, "demo")
        lead = DEMO_TEXT.get(self._language(prompt), DEMO_TEXT["English"])
        return Completion(f"{lead}\n\n> {excerpt}", self.id, "demo")

    @staticmethod
    def _language(prompt: Prompt) -> str:
        found = re.search(r"Answer in ([A-Za-z ()]+?)\.", prompt.system)
        return found.group(1) if found else "English"

