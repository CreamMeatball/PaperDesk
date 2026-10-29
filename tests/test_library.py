import unittest

from paperdesk.domain.errors import InvalidInput, NotFound

from .helpers import build_app, make_pdf


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.app, self.tmp = build_app()
        self.folders = self.app.folders
        self.library = self.app.library

    def tearDown(self):
        self.tmp.cleanup()

    def test_nested_folders_and_unique_names_per_parent(self):
        ml = self.folders.create("Machine Learning")
        diffusion = self.folders.create("Diffusion", ml.id)
        self.folders.create("Diffusion")  # same name is fine at a different level
        with self.assertRaises(InvalidInput):
            self.folders.create("diffusion", ml.id)
        self.assertEqual(self.folders.descendants(ml.id), {diffusion.id})

    def test_cannot_move_folder_into_its_own_subtree(self):
        root = self.folders.create("A")
        child = self.folders.create("B", root.id)
        grandchild = self.folders.create("C", child.id)
        with self.assertRaises(InvalidInput):
            self.folders.move(root.id, grandchild.id)
        moved = self.folders.move(grandchild.id, None)
        self.assertIsNone(moved.parent_id)

    def test_delete_moves_papers_and_subfolders_up(self):
        parent = self.folders.create("Vision")
        target = self.folders.create("Detection", parent.id)
        sub = self.folders.create("YOLO", target.id)
        clash = self.folders.create("YOLO", parent.id)
        doc, _ = self.library.import_pdf("a.pdf", make_pdf(["alpha"]), target.id)
        self.folders.delete(target.id)
        self.assertEqual(self.library.get(doc.id).folder_id, parent.id)
        names = sorted(f.name for f in self.folders.list() if f.parent_id == parent.id)
        self.assertEqual(names, ["YOLO", "YOLO (2)"])
        self.assertIn(clash.id, {f.id for f in self.folders.list()})
        self.assertIn(sub.id, {f.id for f in self.folders.list()})

    def test_scope_folder_includes_subfolders(self):
        parent = self.folders.create("NLP")
        child = self.folders.create("RAG", parent.id)
        a, _ = self.library.import_pdf("a.pdf", make_pdf(["a"]), parent.id)
        b, _ = self.library.import_pdf("b.pdf", make_pdf(["b"]), child.id)
        c, _ = self.library.import_pdf("c.pdf", make_pdf(["c"]))
        self.assertEqual({d.id for d in self.library.list(parent.id, scope="folder")}, {a.id, b.id})
        self.assertEqual([d.id for d in self.library.list(scope="unfiled")], [c.id])


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.app, self.tmp = build_app()
        self.library = self.app.library

    def tearDown(self):
        self.tmp.cleanup()

    def test_simultaneous_import_of_same_pdf_returns_one_document_without_orphan_files(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from unittest.mock import patch
        barrier=Barrier(2)
        repository=self.library._documents
        original=repository.find_by_sha256
        def both_see_missing(digest):
            result=original(digest);barrier.wait(timeout=3);return result
        raw=make_pdf(['Concurrent upload.'])
        with patch.object(repository,'find_by_sha256',side_effect=both_see_missing),ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.library.import_pdf('same.pdf',raw),range(2)))
        self.assertEqual(len({doc.id for doc,created in results}),1)
        self.assertEqual(sorted(created for doc,created in results),[False,True])
        self.assertEqual(len(self.library.list()),1)
        self.assertEqual(len(list(self.app.paths.blobs.rglob('*.pdf'))),1)

    def test_import_rejects_non_pdf_and_deduplicates(self):
        with self.assertRaises(InvalidInput):
            self.library.import_pdf("x.pdf", b"hello")
        data = make_pdf(["Attention Is All You Need"])
        first, created = self.library.import_pdf("attention_is_all.pdf", data)
        again, created_again = self.library.import_pdf("copy.pdf", data)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.id, again.id)
        self.assertEqual(first.title, "attention is all")
        self.assertTrue(self.library.pdf_path(first.id).read_bytes().startswith(b"%PDF-"))

    def test_move_to_missing_folder_fails(self):
        doc, _ = self.library.import_pdf("a.pdf", make_pdf(["a"]))
        with self.assertRaises(NotFound):
            self.library.move(doc.id, "nope")

    def test_text_search_and_delete(self):
        doc, _ = self.library.import_pdf("a.pdf", make_pdf(["a"]))
        self.library.save_text(doc.id, ["Intro about transformers", "Results: BLEU 28.4"])
        hits = self.library.search("bleu")
        self.assertEqual(hits[0]["page"], 2)
        self.assertEqual(self.library.read_text(doc.id, 2, 2), [(2, "Results: BLEU 28.4")])
        self.library.delete(doc.id)
        self.assertEqual(self.library.search("bleu"), [])
        with self.assertRaises(NotFound):
            self.library.get(doc.id)



class LongPaperTitleTests(unittest.TestCase):
    def test_long_title_can_be_saved_without_changing_the_original_pdf(self):
        app,tmp=build_app()
        self.addCleanup(tmp.cleanup)
        raw=make_pdf(['A long scientific title'])
        doc,_=app.library.import_pdf('submission_2026.pdf',raw)
        title='A comprehensive account of scientific reading and reproducibility across heterogeneous datasets, model families, and independently trained experimental systems'
        renamed=app.library.rename(doc.id,title)
        self.assertEqual(renamed.title,title)
        self.assertEqual(renamed.filename,'submission_2026.pdf')
        self.assertEqual(app.library.pdf_path(doc.id).read_bytes(),raw)
        with self.assertRaises(InvalidInput):app.library.rename(doc.id,'a'*301)
        duplicate,created=app.library.import_pdf('another_name.pdf',raw)
        self.assertFalse(created)
        self.assertEqual(duplicate.title,title)
