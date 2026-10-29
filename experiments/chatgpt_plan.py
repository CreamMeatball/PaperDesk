from __future__ import annotations

from paperdesk.domain.errors import ProviderUnavailable
from paperdesk.domain.models import Completion, Prompt, ProviderStatus
from paperdesk.ports.ai import AIProvider, OptionField
from paperdesk.providers.openai_responses import ResponsesClient
from paperdesk.i18n import _


class ChatGPTPlanProvider(AIProvider):
    """'Sign in with ChatGPT' with ChatGPT plan usage (OpenAI preview for open-source and locally hosted apps).

    Inference is already implemented: Responses API with the user's OAuth access token as Bearer.
    Still to build: the sign-in flow (dynamic_agent_client registration, PKCE, loopback callback,
    persisted ext_agent_host_id, token refresh) which will save 'access_token' into the SecretStore.
    """

    id = "chatgpt-plan"
    label = _("ChatGPT 요금제 (Sign in with ChatGPT)")
    supports_images = True
    kind = "account"
    description = _("‘ChatGPT로 계속하기’로 로그인해 내 ChatGPT 요금제 사용량으로 처리합니다. OpenAI가 오픈소스·로컬 앱용으로 공개한 프리뷰 방식입니다.")
    docs_url = "https://developers.openai.com/siwc/token-sharing-open-source"
    options = (
        OptionField("model", _("모델"), placeholder=_("로그인 후 계정에서 쓸 수 있는 모델 선택")),
        OptionField("access_token", _("OAuth 액세스 토큰"), kind="secret",
                    help=_("로그인 흐름이 자동으로 저장합니다. 직접 입력할 필요가 없습니다.")),
    )

    def status(self) -> ProviderStatus:
        if not self.option("access_token"):
            return ProviderStatus(False, _("‘ChatGPT로 계속하기’ 로그인은 다음 단계에서 연결합니다."))
        if not self.model:
            return ProviderStatus(False, _("사용할 모델을 고르세요."))
        return ProviderStatus(True, _("ChatGPT 요금제 사용 중"))

    def complete(self, prompt: Prompt) -> Completion:
        token = self.option("access_token")
        if not token or not self.model:
            raise ProviderUnavailable(self.status().detail)
        text = ResponsesClient(self.context.http).complete(bearer=token, model=self.model, prompt=prompt)
        return Completion(text, self.id, self.model)

