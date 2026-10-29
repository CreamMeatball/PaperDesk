import json
import unittest

from paperdesk.domain.errors import InvalidInput, ProviderFailed
from paperdesk.domain.models import AssistRequest, AssistTask, Completion, ImageInput, PaperMetadata, ProviderStatus
from paperdesk.infrastructure.scholarly import ArxivIndex, CompositeIndex, OpenAlexIndex
from paperdesk.ports.ai import AIProvider
from paperdesk.ports.downloads import FileDownloader
from paperdesk.ports.scholarly import ScholarlyIndex
from paperdesk.providers.registry import ProviderRegistry

from .helpers import build_app, make_pdf

PNG = ImageInput("image/png", b"\x89PNG\r\n\x1a\nfake")


class ScriptedProvider(AIProvider):
    """Replies from a queue; records prompts. supports_images is toggled per test."""

    id = "scripted"
    label = "Scripted"
    kind = "offline"
    replies: list = []
    prompts: list = []
    supports_images = True

    def status(self):
        return ProviderStatus(True)

    def complete(self, prompt):
        ScriptedProvider.prompts.append(prompt)
        reply = ScriptedProvider.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return Completion(reply, self.id, "m")


def scripted_app(*replies, **overrides):
    ScriptedProvider.replies = list(replies)
    ScriptedProvider.prompts = []
    ScriptedProvider.supports_images = True
    app, tmp = build_app(registry=ProviderRegistry([ScriptedProvider]), **overrides)
    app.settings.update_general(provider="scripted", target_language="Korean")
    return app, tmp


class TranslationTests(unittest.TestCase):
    def setUp(self):
        reply = json.dumps({"blocks": [{"id": "0", "sentences": ["첫 문장.", "둘째 문장."]}, {"id": "1", "sentences": ["한 덩어리로 합침."]}]})
        self.app, self.tmp = scripted_app(reply)
        self.doc, _ = self.app.library.import_pdf("a.pdf", make_pdf(["x"]))

    def tearDown(self):
        self.tmp.cleanup()

    def test_sentence_alignment_and_reuse(self):
        blocks = self.app.translations.parse_blocks([
            {"key": "1:abc123", "sentences": ["First sentence.", "Second one."]},
            {"key": "1:def456", "sentences": ["Two source.", "Sentences here."]},
        ])
        result = self.app.translations.translate(self.doc.id, blocks, title="T")
        self.assertEqual(result["blocks"]["1:abc123"]["sentences"], ["첫 문장.", "둘째 문장."])
        self.assertIsNone(result["blocks"]["1:def456"]["sentences"])  # count mismatch -> paragraph only
        self.assertEqual(result["blocks"]["1:def456"]["text"], "한 덩어리로 합침.")
        prompt = ScriptedProvider.prompts[0]
        self.assertIn("natural, consistent Korean", prompt.user)
        again = self.app.translations.translate(self.doc.id, blocks)  # no reply queued: must come from storage
        self.assertEqual(again["blocks"].keys(), result["blocks"].keys())
        self.assertEqual(len(ScriptedProvider.prompts), 1)
        self.assertEqual(set(self.app.translations.list(self.doc.id)["blocks"]), {"1:abc123", "1:def456"})

    def test_structured_translation_prompt_is_enforced_by_codex_cli(self):
        import tempfile
        from pathlib import Path
        from paperdesk.providers.codex_cli import CodexCliProvider
        from .test_providers import context
        self.app.translations.translate(self.doc.id,self.app.translations.parse_blocks([{'key':'1:abc123','sentences':['First.','Second.']}]))
        prompt=ScriptedProvider.prompts[0]
        self.assertEqual(prompt.response_schema['required'],['blocks'])
        provider=CodexCliProvider(context('codex-cli'))
        with tempfile.TemporaryDirectory() as folder:
            command=provider.build_command('/bin/codex',prompt,Path(folder))
            index=command.index('--output-schema')
            self.assertEqual(json.loads(Path(command[index+1]).read_text()),prompt.response_schema)

    def test_malformed_json_is_not_saved_as_a_successful_paragraph(self):
        ScriptedProvider.replies=['{"blocks": INVALID}']
        block=self.app.translations.parse_blocks([{'key':'1:aaaa','sentences':['One.']}])
        result=self.app.translations.translate(self.doc.id,block)
        self.assertEqual(result['missing'],['1:aaaa'])
        self.assertEqual(self.app.translations.list(self.doc.id)['blocks'],{})

    def test_changed_text_is_retranslated_and_bad_input_rejected(self):
        self.app.translations.translate(self.doc.id, self.app.translations.parse_blocks([{"key": "2:aaaa", "sentences": ["A.", "B."]}]))
        ScriptedProvider.replies.append(json.dumps({"blocks": [{"id": "0", "sentences": ["다른 글."]}]}))
        result = self.app.translations.translate(self.doc.id, self.app.translations.parse_blocks([{"key": "2:aaaa", "sentences": ["Changed."]}]))
        self.assertEqual(result["blocks"]["2:aaaa"]["sentences"], ["다른 글."])
        for bad in ([], [{"key": "../x", "sentences": ["a"]}], [{"key": "1:abcd", "sentences": []}]):
            with self.assertRaises(InvalidInput):
                self.app.translations.parse_blocks(bad)


class AssistantImageTests(unittest.TestCase):
    def test_images_dropped_for_text_only_providers_and_retried_on_refusal(self):
        app, tmp = scripted_app(ProviderFailed("vision not supported"), "텍스트로 설명")
        self.addCleanup(tmp.cleanup)
        result = app.assistant.run(AssistRequest(AssistTask.FIGURE, "Figure 2: results", images=(PNG,)))
        self.assertEqual(result.text, "텍스트로 설명")
        self.assertEqual(len(ScriptedProvider.prompts[0].images), 1)
        self.assertEqual(ScriptedProvider.prompts[1].images, ())
        self.assertIn("could not be sent", ScriptedProvider.prompts[1].user)
        ScriptedProvider.supports_images = False
        ScriptedProvider.replies.append("ok")
        app.assistant.run(AssistRequest(AssistTask.EQUATION, "E = mc^2", images=(PNG,)))
        self.assertEqual(ScriptedProvider.prompts[-1].images, ())

    def test_cache_only_never_calls_model(self):
        app, tmp = scripted_app("요약")
        self.addCleanup(tmp.cleanup)
        request = AssistRequest(AssistTask.TLDR, "paper text")
        self.assertIsNone(app.assistant.run(request, cache_only=True))
        app.assistant.run(request)
        self.assertEqual(app.assistant.run(request, cache_only=True).text, "요약")
        self.assertEqual(len(ScriptedProvider.prompts), 1)


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.app, self.tmp = build_app()
        self.doc, _ = self.app.library.import_pdf("a.pdf", make_pdf(["x"]))

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_update_delete(self):
        a = self.app.annotations.add(self.doc.id, page=1, kind="highlight", color="yellow", text=" key  idea ",
                                     rects=[[0.1, 0.2, 0.5, 0.22], [0.5, 0.5, 0.4, 0.6]])
        self.assertEqual((a.text, len(a.rects)), ("key idea", 1))
        b = self.app.annotations.update(a.id, note="check later", color="pink")
        self.assertEqual((b.kind, b.color, b.note), ("note", "pink", "check later"))
        self.assertEqual([x.id for x in self.app.annotations.list(self.doc.id)], [a.id])
        with self.assertRaises(InvalidInput):
            self.app.annotations.add(self.doc.id, page=1, kind="highlight", color="red", text="x", rects=[[0, 0, 1, 1]])
        self.app.library.delete(self.doc.id)
        self.assertIsNone(self.app.annotations._repository.get(a.id))


class FakeDownloader(FileDownloader):
    def __init__(self, routes):
        self.routes, self.urls = routes, []

    def download(self, url, *, max_bytes, timeout):
        self.urls.append(url)
        for prefix, body in self.routes.items():
            if url.startswith(prefix):
                return body.encode() if isinstance(body, str) else body
        raise InvalidInput("404")


ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2006.11239v2</id>
<title>Denoising Diffusion Probabilistic
  Models</title><summary>We present high quality image synthesis results.</summary><published>2020-06-19T00:00:00Z</published>
<author><name>Jonathan Ho</name></author><author><name>Ajay Jain</name></author></entry></feed>"""
OPENALEX = json.dumps({"results": [{"display_name": "Deep Residual Learning for Image Recognition", "publication_year": 2016,
                                    "abstract_inverted_index": {"Deeper": [0], "networks": [1], "are": [2], "hard": [3]},
                                    "authorships": [{"author": {"display_name": "Kaiming He"}}]}]})


class ScholarlyTests(unittest.TestCase):
    def test_arxiv_by_title_requires_close_match(self):
        index = ArxivIndex(FakeDownloader({"https://export.arxiv.org/api/query": ATOM}))
        found = index.lookup(title="Denoising diffusion probabilistic models")
        self.assertEqual((found.arxiv_id, found.year, found.authors), ("2006.11239", "2020", "Jonathan Ho, Ajay Jain"))
        self.assertIsNone(index.lookup(title="Completely different paper about graphs"))

    def test_openalex_abstract_and_composite_fallthrough(self):
        downloader = FakeDownloader({"https://api.openalex.org/works?": OPENALEX, "https://export.arxiv.org": "<feed xmlns='http://www.w3.org/2005/Atom'/>"})
        index = CompositeIndex([ArxivIndex(downloader), OpenAlexIndex(downloader)])
        found = index.lookup(title="Deep residual learning for image recognition")
        self.assertEqual((found.source, found.abstract), ("openalex", "Deeper networks are hard"))


class FixedIndex(ScholarlyIndex):
    def __init__(self, result):
        self.result, self.calls = result, 0

    def lookup(self, **kwargs):
        self.calls += 1
        return self.result


class ReferenceNoteTests(unittest.TestCase):
    def test_grounded_summary_and_metadata_cache(self):
        index = FixedIndex(PaperMetadata("DDPM", "We present diffusion models.", "Ho", "2020", source="arxiv", arxiv_id="2006.11239"))
        app, tmp = scripted_app("확산 모델 논문입니다.", scholarly=index)
        self.addCleanup(tmp.cleanup)
        citation = "Ho, J., Jain, A., and Abbeel, P. Denoising diffusion probabilistic models. NeurIPS, 2020."
        self.assertIsNone(app.reference_notes.explain(citation, language="Korean", cache_only=True)["summary"])
        result = app.reference_notes.explain(citation, language="Korean")
        self.assertTrue(result["grounded"])
        self.assertIn("We present diffusion models.", ScriptedProvider.prompts[0].user)
        app.reference_notes.explain(citation, language="Korean")
        self.assertEqual(index.calls, 1)

    def test_reading_list_finds_arxiv_id_by_title(self):
        index = FixedIndex(PaperMetadata("Qwen2.5-VL Technical Report", "abs", arxiv_id="2502.13923"))
        app, tmp = build_app(scholarly=index)
        self.addCleanup(tmp.cleanup)
        item, _ = app.reading.add("Shuai Bai, Keqin Chen, and Junyang Lin. Qwen2.5-vl technical report, 2025.")
        self.assertEqual(app.reading.find_arxiv(item.id).arxiv_id, "2502.13923")

