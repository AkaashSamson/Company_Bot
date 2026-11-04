import unittest
from tests.evaluation.metrics import recall_at_k, mrr

class TestMetrics(unittest.TestCase):
    def test_recall_at_k(self):
        retrieved = ["A", "B", "C", "D"]
        relevant = ["B", "D"]
        
        self.assertEqual(recall_at_k(retrieved, relevant, 1), 0.0)
        self.assertEqual(recall_at_k(retrieved, relevant, 2), 0.5)
        self.assertEqual(recall_at_k(retrieved, relevant, 4), 1.0)
        
        # Handling no relevant chunks
        self.assertEqual(recall_at_k(retrieved, [], 4), 0.0)
        
        # K greater than candidate count
        self.assertEqual(recall_at_k(retrieved, relevant, 10), 1.0)
        
        # Empty results
        self.assertEqual(recall_at_k([], relevant, 4), 0.0)
        
    def test_mrr(self):
        retrieved = ["A", "B", "C", "D"]
        relevant = ["C"]
        self.assertEqual(mrr(retrieved, relevant), 1/3)
        
        relevant_first = ["A"]
        self.assertEqual(mrr(retrieved, relevant_first), 1.0)
        
        no_relevant = ["E"]
        self.assertEqual(mrr(retrieved, no_relevant), 0.0)
        
        # Multiple relevant chunks, should use the first one found
        multi_relevant = ["C", "B"]
        self.assertEqual(mrr(retrieved, multi_relevant), 1/2)
        
        # Empty results
        self.assertEqual(mrr([], relevant), 0.0)

if __name__ == '__main__':
    unittest.main()
