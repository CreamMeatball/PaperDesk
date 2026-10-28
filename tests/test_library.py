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

