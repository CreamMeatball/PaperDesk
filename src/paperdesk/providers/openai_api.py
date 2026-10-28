from __future__ import annotations

from ..domain.errors import ProviderUnavailable
from ..domain.models import Completion, Prompt, ProviderStatus
from ..ports.ai import AIProvider, OptionField
from .openai_responses import ResponsesClient


class OpenAIApiProvider(AIProvider):
    id = "openai-api"
    label = "OpenAI API"
    supports_images = True
    kind = "api"
    description = "OpenAI Platform API 키로 호출합니다. 사용량은 내 API 계정에 청구됩니다."
    docs_url = "https://platform.openai.com/api-keys"
    options = (
        OptionField("model", "모델", default="gpt-6-luna"),
        OptionField("api_key", "API 키", kind="secret", env="OPENAI_API_KEY", placeholder="sk-..."),
    )

    def status(self) -> ProviderStatus:
        if not self.option("api_key"):
            return ProviderStatus(False, "API 키를 입력하세요 (또는 OPENAI_API_KEY 환경 변수).")
        return ProviderStatus(True, "API 키 준비됨")

    def complete(self, prompt: Prompt) -> Completion:
        key = self.option("api_key")
        if not key:
            raise ProviderUnavailable(self.status().detail)
        text = ResponsesClient(self.context.http).complete(bearer=key, model=self.model, prompt=prompt)
        return Completion(text, self.id, self.model)

