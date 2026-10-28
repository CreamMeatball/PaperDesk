import json
import unittest

from paperdesk.domain.errors import InvalidInput
from paperdesk.ports.downloads import FileDownloader

from .helpers import build_app, make_pdf

ATTENTION = ("[32] Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan N. Gomez, Lukasz Kaiser, "
             "and Illia Polosukhin. Attention is all you need. arXiv preprint arXiv:1706.03762, 2017.")


class FakeDownloader(FileDownloader):
    def __init__(self, data):
        self.data, self.urls = data, []

    def download(self, url, *, max_bytes, timeout):
        self.urls.append(url)
        return self.data


class ReadingListTests(unittest.TestCase):
    def setUp(self):
        self.downloader = FakeDownloader(make_pdf(["Attention"]))
        self.app, self.tmp = build_app(downloader=self.downloader)
        self.folder = self.app.folders.create("NLP")
        self.source, _ = self.app.library.import_pdf("bert.pdf", make_pdf(["BERT"]), self.folder.id)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_parses_and_deduplicates(self):
        item, created = self.app.reading.add(ATTENTION, source_doc_id=self.source.id)
        self.assertTrue(created)
        self.assertEqual((item.title, item.year, item.arxiv_id), ("Attention is all you need", "2017", "1706.03762"))
        again, created_again = self.app.reading.add("Vaswani et al. Attention Is All You Need. NeurIPS 2017.")
        self.assertFalse(created_again)
        self.assertEqual(again.id, item.id)

    def test_rejects_too_short_or_too_long(self):
        with self.assertRaises(InvalidInput):
            self.app.reading.add("[3]")
        with self.assertRaises(InvalidInput):
            self.app.reading.add("x " * 1500)

    def test_arxiv_pdf_goes_to_citing_papers_folder(self):
        item, _ = self.app.reading.add(ATTENTION, source_doc_id=self.source.id)
        linked, document = self.app.reading.fetch_arxiv_pdf(item.id)
        self.assertEqual(self.downloader.urls, ["https://arxiv.org/pdf/1706.03762"])
        self.assertEqual(document.folder_id, self.folder.id)
        self.assertEqual(document.title, "Attention is all you need")
        self.assertTrue(linked.in_library)
        self.app.library.delete(document.id)  # deleting the PDF puts the paper back on the to-read list
        self.assertFalse(self.app.reading.get(item.id).in_library)

    def test_manual_pdf_and_unfiled_choice(self):
        item, _ = self.app.reading.add("Kaiming He et al. Deep residual learning for image recognition. CVPR 2016.",
                                       source_doc_id=self.source.id)
        _, document = self.app.reading.attach_pdf(item.id, "resnet.pdf", make_pdf(["ResNet"]), "")
        self.assertIsNone(document.folder_id)
        with self.assertRaises(InvalidInput):
            self.app.reading.fetch_arxiv_pdf(item.id)

    def test_deleting_source_paper_keeps_item(self):
        item, _ = self.app.reading.add(ATTENTION, source_doc_id=self.source.id)
        self.app.library.delete(self.source.id)
        self.assertIsNone(self.app.reading.get(item.id).source_doc_id)
