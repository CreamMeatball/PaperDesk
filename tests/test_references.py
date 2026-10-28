import unittest

from paperdesk.services.references import ReferenceParser


class ReferenceParserTests(unittest.TestCase):
    def setUp(self):
        self.parse = ReferenceParser().parse

    def test_neurips_numeric(self):
        ref = self.parse("[32] Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan N. Gomez, "
                         "Lukasz Kaiser, and Illia Polosukhin. Attention is all you need. In NeurIPS, 2017.")
        self.assertEqual(ref.title, "Attention is all you need")
        self.assertTrue(ref.authors.startswith("Ashish Vaswani"))
        self.assertEqual(ref.year, "2017")

    def test_natbib_with_arxiv(self):
        ref = self.parse("Jonathan Ho, Ajay Jain, and Pieter Abbeel. Denoising diffusion probabilistic models. "
                         "arXiv preprint arXiv:2006.11239, 2020.")
        self.assertEqual((ref.title, ref.arxiv_id, ref.year), ("Denoising diffusion probabilistic models", "2006.11239", "2020"))

    def test_apa(self):
        ref = self.parse("Lipman, Y., Chen, R. T. Q., Ben-Hamu, H., Nickel, M., & Le, M. (2023). Flow matching for "
                         "generative modeling. In International Conference on Learning Representations. https://doi.org/10.48550/arXiv.2210.02747.")
        self.assertEqual(ref.title, "Flow matching for generative modeling")
        self.assertEqual(ref.year, "2023")
        self.assertEqual(ref.doi, "10.48550/arXiv.2210.02747")

    def test_acl_year_after_authors(self):
        ref = self.parse("Jacob Devlin, Ming-Wei Chang, Kenton Lee, and Kristina Toutanova. 2019. BERT: Pre-training of deep "
                         "bidirectional transformers for language understanding. In Proceedings of NAACL, pages 4171–4186.")
        self.assertEqual(ref.title, "BERT: Pre-training of deep bidirectional transformers for language understanding")
        self.assertEqual(ref.year, "2019")

    def test_ieee_quoted_title(self):
        ref = self.parse('[4] K. He, X. Zhang, S. Ren, and J. Sun, “Deep residual learning for image recognition,” in Proc. CVPR, 2016, pp. 770–778.')
        self.assertEqual(ref.title, "Deep residual learning for image recognition")
        self.assertEqual(ref.authors, "K. He, X. Zhang, S. Ren, and J. Sun")

    def test_trailing_year_is_not_part_of_title(self):
        ref = self.parse("Shuai Bai, Keqin Chen, and Junyang Lin. Qwen2.5-vl technical report, 2025.")
        self.assertEqual((ref.title, ref.year), ("Qwen2.5-vl technical report", "2025"))

    def test_initials_and_et_al_do_not_split(self):
        ref = self.parse("Ricky T. Q. Chen, Yulia Rubanova, J. Bettencourt, and D. K. Duvenaud. Neural ordinary differential "
                         "equations. Advances in Neural Information Processing Systems, 31, 2018. URL https://arxiv.org/abs/1806.07366.")
        self.assertEqual(ref.title, "Neural ordinary differential equations")
        self.assertEqual(ref.arxiv_id, "1806.07366")

