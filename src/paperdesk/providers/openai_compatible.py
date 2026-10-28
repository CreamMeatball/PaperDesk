"""Local or self-hosted model servers that speak the OpenAI Chat Completions protocol (Ollama, vLLM, LM Studio...)."""

from __future__ import annotations

import re
from typing import ClassVar

from ..domain.errors import ProviderFailed, ProviderUnavailable, ReaderError
from ..domain.models import Completion, Prompt, ProviderStatus
from ..ports.ai import AIProvider, OptionField

_THINK = re.compile(r"^\s*<think>.*?</think>\s*", re.S)


def server_options(default_base_url: str, *, key_help: str) -> tuple[OptionField, ...]:
    return (
        OptionField("base_url", "서버 주소", kind="url", default=default_base_url, placeholder=default_base_url),
        OptionField("model", "모델", placeholder="비워 두면 서버의 첫 번째 모델"),
        OptionField("api_key", "API 키 (선택)", kind="secret", help=key_help),
    )


class OpenAICompatibleProvider(AIProvider):
    kind = "local-server"
    default_base_url: ClassVar[str] = "http://localhost:8000/v1"
    probe_timeout: ClassVar[float] = 2.0
    timeout: ClassVar[float] = 600

    @property
    def base_url(self) -> str:
        return self.option("base_url").rstrip("/")

    def _headers(self) -> dict[str, str]:
        key = self.option("api_key")
        return {"Authorization": f"Bearer {key}"} if key else {}

    def list_models(self) -> list[str]:
        data = self.context.http.get_json(f"{self.base_url}/models", headers=self._headers(), timeout=self.probe_timeout)
        return [str(item.get("id")) for item in (data.get("data") or []) if item.get("id")]

    def status(self) -> ProviderStatus:
        try:
            models = self.list_models()
        except ReaderError as error:
            return ProviderStatus(False, f"{self.base_url} 에 연결하지 못했어요. 서버가 켜져 있는지 확인하세요. ({error})")
        if not models:
            return ProviderStatus(False, "서버에 불러온 모델이 없어요.", ())
        chosen = self.model or models[0]
        note = "" if chosen in models else " (서버 목록에 없는 모델 이름)"
        return ProviderStatus(True, f"{self.base_url} · {chosen}{note}", tuple(models))

    def complete(self, prompt: Prompt) -> Completion:
        model = self.model
        if not model:
            try:
                models = self.list_models()
            except ReaderError as error:
                raise ProviderUnavailable(str(error)) from error
            if not models:
                raise ProviderUnavailable("서버에 불러온 모델이 없어요.")
            model = models[0]
        data = self.context.http.post_json(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            body={
                "model": model,
                "messages": [{"role": "system", "content": prompt.system}, {"role": "user", "content": prompt.user}],
                "stream": False,
            },
            timeout=self.timeout,
        )
        try:
            text = data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderFailed("서버 응답 형식을 이해하지 못했어요.") from error
        text = _THINK.sub("", text)  # some reasoning models inline their thinking
        if not text.strip():
            raise ProviderFailed("모델이 빈 응답을 돌려줬어요.")
        return Completion(text, self.id, model)


class OllamaProvider(OpenAICompatibleProvider):
    id = "ollama"
    label = "Ollama (내 컴퓨터)"
    description = "내 컴퓨터의 Ollama로 오프라인 처리합니다. 문서가 밖으로 나가지 않습니다. 예: ollama pull qwen3"
    docs_url = "https://github.com/ollama/ollama/blob/main/docs/openai.md"
    default_base_url = "http://localhost:11434/v1"
    options = server_options(default_base_url, key_help="보통 필요 없습니다.")


class OpenAICompatibleServerProvider(OpenAICompatibleProvider):
    id = "openai-compatible"
    label = "vLLM · OpenAI 호환 서버"
    description = "vLLM, LM Studio, llama.cpp server처럼 OpenAI 호환 API를 제공하는 서버(회사·학교 내부 서버 포함)에 연결합니다."
    docs_url = "https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html"
    default_base_url = "http://localhost:8000/v1"
    options = server_options(default_base_url, key_help="vLLM을 --api-key로 띄웠다면 입력하세요.")

