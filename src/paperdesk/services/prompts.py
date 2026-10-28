from __future__ import annotations

from typing import Callable

from ..domain.errors import InvalidInput
from ..domain.models import AssistRequest, AssistTask, Prompt

PROMPT_VERSION = 1  # bump when wording changes so cached answers are not reused

BASE = (
    "You help a reader understand an academic paper. "
    "Answer in {language}. Keep technical terms, model names, dataset names and math notation in their original form. "
    "Do not invent content that is not supported by the given text. Use Markdown sparingly. "
    "Do not run tools or commands; reply with text only."
)


class PromptBuilder:
    """Turns an AssistRequest into a Prompt. Add a task: write a method and register it in _builders."""

    def __init__(self) -> None:
        self._builders: dict[AssistTask, Callable[[AssistRequest], str]] = {
            AssistTask.TRANSLATE: self._translate,
            AssistTask.EXPLAIN: self._explain,
            AssistTask.ASK: self._ask,
            AssistTask.SUMMARIZE: self._summarize,
        }

    def build(self, request: AssistRequest) -> Prompt:
        builder = self._builders.get(request.task)
        if builder is None:
            raise InvalidInput(f"지원하지 않는 작업: {request.task}")
        return Prompt(BASE.format(language=request.target_language), builder(request))

    @staticmethod
    def _context(request: AssistRequest) -> str:
        return f"\n\nSurrounding text for context (do not translate or explain it):\n<context>\n{request.context}\n</context>" if request.context else ""

    def _translate(self, request: AssistRequest) -> str:
        return (f"Translate the passage into natural {request.target_language}. Output only the translation."
                f"{self._context(request)}\n\n<passage>\n{request.text}\n</passage>")

    def _explain(self, request: AssistRequest) -> str:
        return ("Explain the passage for a graduate student new to this subfield: what it says, why it matters "
                "in the paper, and any terms or symbols they need. Keep it under 200 words."
                f"{self._context(request)}\n\n<passage>\n{request.text}\n</passage>")

    def _ask(self, request: AssistRequest) -> str:
        if not request.question.strip():
            raise InvalidInput("질문을 입력하세요.")
        return (f"Answer the question using the passage. Say so if the passage is not enough."
                f"{self._context(request)}\n\n<passage>\n{request.text}\n</passage>\n\nQuestion: {request.question}")

    def _summarize(self, request: AssistRequest) -> str:
        return ("Summarize the paper text: problem, method, key results, limitations. Use short bullet points."
                f"\n\n<paper>\n{request.text}\n</paper>")

