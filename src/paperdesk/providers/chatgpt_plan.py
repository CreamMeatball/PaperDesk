from __future__ import annotations

from ..domain.errors import ProviderUnavailable
from ..domain.models import Completion, Prompt, ProviderStatus
from ..ports.ai import AIProvider, OptionField
from .openai_responses import ResponsesClient


class ChatGPTPlanProvider(AIProvider):
    """'Sign in with ChatGPT' with ChatGPT plan usage (OpenAI preview for open-source and locally hosted apps).

    Inference is already implemented: Responses API with the user's OAuth access token as Bearer.
    Still to build: the sign-in flow (dynamic_agent_client registration, PKCE, loopback callback,
    persisted ext_agent_host_id, token refresh) which will save 'access_token' into the SecretStore.
    """

    id = "chatgpt-plan"
    label = "ChatGPT 요금제 (Sign in with ChatGPT)"
    supports_images = True
    kind = "account"
    description = "‘ChatGPT로 계속하기’로 로그인해 내 ChatGPT 요금제 사용량으로 처리합니다. OpenAI가 오픈소스·로컬 앱용으로 공개한 프리뷰 방식입니다."
    docs_url = "https://developers.openai.com/siwc/token-sharing-open-source"
    options = (
        OptionField("model", "모델", placeholder="로그인 후 계정에서 쓸 수 있는 모델 선택"),
        OptionField("access_token", "OAuth 액세스 토큰", kind="secret",
                    help="로그인 흐름이 자동으로 저장합니다. 직접 입력할 필요가 없습니다."),
    )

    def status(self) -> ProviderStatus:
        if not self.option("access_token"):
            return ProviderStatus(False, "‘ChatGPT로 계속하기’ 로그인은 다음 단계에서 연결합니다.")
        if not self.model:
            return ProviderStatus(False, "사용할 모델을 고르세요.")
        return ProviderStatus(True, "ChatGPT 요금제 사용 중")

    def complete(self, prompt: Prompt) -> Completion:
        token = self.option("access_token")
        if not token or not self.model:
            raise ProviderUnavailable(self.status().detail)
        text = ResponsesClient(self.context.http).complete(bearer=token, model=self.model, prompt=prompt)
        return Completion(text, self.id, self.model)

