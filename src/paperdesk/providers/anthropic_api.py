from __future__ import annotations

from ..domain.errors import ProviderFailed, ProviderUnavailable
from ..domain.models import Completion, Prompt, ProviderStatus
from ..ports.ai import AIProvider, OptionField


class AnthropicApiProvider(AIProvider):
    """Claude API with the user's own Console key: Anthropic's recommended path for third-party and open-source apps."""

    id = "anthropic-api"
    label = "Claude API"
    kind = "api"
    supports_images = True
    description = "Claude Console API 키로 호출합니다. 사용량은 내 Anthropic API 계정에 청구됩니다."
    docs_url = "https://platform.claude.com/docs/en/get-api-key"
    endpoint = "https://api.anthropic.com/v1/messages"
    options = (
        OptionField("model", "모델", default="claude-haiku-5-5"),
        OptionField("api_key", "API 키", kind="secret", env="ANTHROPIC_API_KEY", placeholder="sk-ant-..."),
    )

    def status(self) -> ProviderStatus:
        if not self.option("api_key"):
            return ProviderStatus(False, "API 키를 입력하세요 (또는 ANTHROPIC_API_KEY 환경 변수).")
        return ProviderStatus(True, "API 키 준비됨")

    @staticmethod
    def _content(prompt: Prompt):
        if not prompt.images:
            return prompt.user
        import base64

        blocks = [{"type": "image", "source": {"type": "base64", "media_type": image.media_type,
                                                "data": base64.b64encode(image.data).decode()}} for image in prompt.images]
        return blocks + [{"type": "text", "text": prompt.user}]

    def complete(self, prompt: Prompt) -> Completion:
        key = self.option("api_key")
        if not key:
            raise ProviderUnavailable(self.status().detail)
        data = self.context.http.post_json(
            self.endpoint,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            body={
                "model": self.model,
                "max_tokens": 4096,
                "system": prompt.system,
                "messages": [{"role": "user", "content": self._content(prompt)}],
            },
            timeout=180,
        )
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        if not text:
            raise ProviderFailed(f"Claude API가 빈 응답을 돌려줬어요 (stop_reason={data.get('stop_reason')}).")
        return Completion(text, self.id, self.model)

