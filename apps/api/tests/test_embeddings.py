"""Encoder checks; the model is downloaded from Hugging Face on first run."""
from math import sqrt
import unittest

from app.embeddings import PASSAGE_PREFIX, QUERY_PREFIX, embed_passages, embed_query, get_encoder
from app.models import EMBEDDING_DIMENSIONS


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


class EmbeddingTests(unittest.TestCase):
    def test_passage_vectors_are_normalized_and_match_the_column_width(self):
        vectors = embed_passages(["Project Atlas launch moved to 25 September.", "The office closes at 3pm on Friday."])
        self.assertEqual([len(vector) for vector in vectors], [EMBEDDING_DIMENSIONS, EMBEDDING_DIMENSIONS])
        for vector in vectors:
            self.assertAlmostEqual(sqrt(sum(value * value for value in vector)), 1.0, places=5)

    def test_prefixes_change_the_encoding(self):
        text = "Project Atlas launch moved to 25 September."
        as_query = embed_query(text)
        as_passage = embed_passages([text])[0]
        self.assertLess(cosine(as_query, as_passage), 0.999)
        self.assertEqual(get_encoder().max_seq_length, 512)
        self.assertEqual((QUERY_PREFIX, PASSAGE_PREFIX), ("query: ", "passage: "))

    def test_chinese_query_retrieves_the_english_passage(self):
        passages = [
            "Project Atlas launch date moved to 25 September.",
            "The office will close at 3pm on Friday for the fire drill.",
        ]
        scores = [cosine(embed_query("阿特拉斯什么时候发布"), vector) for vector in embed_passages(passages)]
        self.assertGreater(scores[0], scores[1])

    def test_malay_query_retrieves_the_english_passage(self):
        passages = [
            "Northline Pte Ltd price list effective 1 August: SKU-A19 is $4.80 per unit.",
            "The office will close at 3pm on Friday for the fire drill.",
        ]
        scores = [cosine(embed_query("harga SKU-A19 sekarang"), vector) for vector in embed_passages(passages)]
        self.assertGreater(scores[0], scores[1])

    def test_empty_input_does_not_call_the_model(self):
        self.assertEqual(embed_passages([]), [])


if __name__ == "__main__":
    unittest.main()
