"""Shared client for the OpenAI Responses API. Used with an API key or with a ChatGPT-plan OAuth token."""

from __future__ import annotations

from ..domain.errors import ProviderFailed
from ..domain.models import Prompt
from ..ports.ai import HttpClient
from ..i18n import _

USAGE_LIMIT_CODES = {"subscription_sharing_usage_limit_exceeded", "subscription_sharing_usage_unavailable"}
MANAGE_USAGE_URL = "https://chatgpt.com/settings/usage"


class ResponsesClient:
    def __init__(self, http: HttpClient, *, base_url: str = "https://api.openai.com/v1", timeout: float = 180) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def complete(self, *, bearer: str, model: str, prompt: Prompt) -> str:
        # store=false + stream=true + input array + instructions satisfies both the API-key route and the
        # ChatGPT-plan preview requirements, so one code path serves both credential types.
        body = {
            "model": model,
            "instructions": prompt.system,
            "input": [{"role": "user", "content": self._content(prompt)}],
            "store": False,
            "stream": True,
        }
        parts: list[str] = []
        completed = False
        for event in self._http.stream_sse(
            f"{self._base_url}/responses",
            headers={"Authorization": f"Bearer {bearer}"},
            body=body,
            timeout=self._timeout,
        ):
            kind = event.get("type", "")
            if kind == "response.output_text.delta":
                parts.append(event.get("delta", ""))
            elif kind == "response.completed":
                completed = True
            elif kind in ("response.failed", "response.incomplete", "error"):
                raise ProviderFailed(self._failure(event))
        if not completed:
            raise ProviderFailed(_("응답이 끝나기 전에 연결이 끊겼어요."))
        return "".join(parts)

    @staticmethod
    def _content(prompt: Prompt):
        if not prompt.images:
            return prompt.user
        return [{"type": "input_text", "text": prompt.user}] + [
            {"type": "input_image", "image_url": image.data_url} for image in prompt.images]

    @staticmethod
    def _failure(event: dict) -> str:
        error = (event.get("response") or {}).get("error") or event.get("error") or {}
        code = error.get("code", "") if isinstance(error, dict) else ""
        if code in USAGE_LIMIT_CODES:
            return _("ChatGPT 요금제 사용 한도에 도달했어요. 사용량 관리: {url}", url=MANAGE_USAGE_URL)
        message = error.get("message", "") if isinstance(error, dict) else str(error)
        reason = ((event.get("response") or {}).get("incomplete_details") or {}).get("reason", "")
        return _("OpenAI 응답 실패 {code}: {message}", code=code or reason, message=message)

