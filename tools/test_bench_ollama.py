"""Tests autonomes de bench_ollama.py (sans GPU ni serveur Ollama)."""
import unittest

import bench_ollama as b


class BuildPromptTest(unittest.TestCase):
    def test_taille_approchee(self):
        p = b.build_prompt(1000, "[sel] ")
        self.assertTrue(p.startswith("[sel] "))
        self.assertGreater(len(p), 4000)
        self.assertLess(len(p), 4300)

    def test_sel_different_prompt_different(self):
        # sans sel distinct, Ollama servirait le prefill depuis son cache KV
        self.assertNotEqual(b.build_prompt(500, "[a] "), b.build_prompt(500, "[b] "))


class ExtractMetricsTest(unittest.TestCase):
    def test_debits(self):
        m = b.extract_metrics({
            "prompt_eval_count": 2000, "prompt_eval_duration": 500_000_000,
            "eval_count": 512, "eval_duration": 8_000_000_000,
        })
        self.assertAlmostEqual(m["prefill_tps"], 4000.0)
        self.assertAlmostEqual(m["decode_tps"], 64.0)

    def test_reponse_vide(self):
        m = b.extract_metrics({})
        self.assertIsNone(m["prefill_tps"])
        self.assertIsNone(m["decode_tps"])


if __name__ == "__main__":
    unittest.main()
