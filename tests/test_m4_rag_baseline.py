from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from ah.config import load_config
from ah.core import AHCore
from ah.diagnostics.hackathon_metrics import M2QuestionObservation, score_m2_explainability, score_m4_comparison
from ah.diagnostics.m4_acceptance import (
    InjectedAhAnswer,
    load_m4_questions,
    run_m4_acceptance,
)
from ah.llm.embeddings import EmbeddingClientError, FakeEmbeddingClient, build_embedding_client
from rag.vanilla import (
    RagChunk,
    VanillaRag,
    VanillaRagIndex,
    cosine_similarity,
    rag_hallucinated,
)
from ah.llm.lmstudio_client import LMStudioClient
from ah.llm.ollama_client import OllamaClient
from ah.llm.process_backend import LLMResponse, LocalLLMProcessBackend


PROJECT = Path(__file__).resolve().parents[1]


class _FakeGenerator:
    def __init__(self, text: str = "UNKNOWN") -> None:
        self.text = text
        self.roles: list[str] = []
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, system: str = "", override=None, role: str = "generic") -> LLMResponse:
        self.roles.append(role)
        self.prompts.append(prompt)
        return LLMResponse(self.text, {"text": self.text})


class M4RagBaselineTests(unittest.TestCase):
    def test_fake_embeddings_retrieve_expected_top1(self) -> None:
        index = VanillaRagIndex(
            (
                RagChunk("c1", "doc", "alpha unique token", (1.0, 0.0, 0.0)),
                RagChunk("c2", "doc", "beta other token", (0.0, 1.0, 0.0)),
            )
        )
        hits = index.retrieve((0.99, 0.01, 0.0), top_k=1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].chunk.chunk_id, "c1")
        self.assertGreater(hits[0].score, 0.9)
        self.assertGreater(
            cosine_similarity((1.0, 0.0), (1.0, 0.0)),
            cosine_similarity((1.0, 0.0), (0.0, 1.0)),
        )

    def test_rag_does_not_mutate_ah_core(self) -> None:
        core = AHCore()
        before = set(core.store.all_uids())
        embedder = FakeEmbeddingClient({"query": (1.0, 0.0), "chunk text": (1.0, 0.0)}, dim=2)
        rag = VanillaRag(embedder, _FakeGenerator("chunk text"), top_k=1)
        index = VanillaRagIndex((RagChunk("c1", "doc", "chunk text", (1.0, 0.0)),))
        answer = rag.answer("query", index)
        self.assertEqual(answer.answer, "chunk text")
        self.assertEqual(set(core.store.all_uids()), before)
        self.assertEqual(embedder.calls[-1], ("query",))

    def test_rag_hallucination_is_deterministic(self) -> None:
        chunk = "Автоматика остановила насос, потому что давление упало."
        self.assertFalse(rag_hallucinated("давление упало", [chunk], ["давление упало"]))
        self.assertTrue(rag_hallucinated("луна сделана из сыра", [chunk], ["давление упало"]))
        self.assertFalse(rag_hallucinated("UNKNOWN", [chunk], ["давление упало"]))

    def test_rag_explain_score_is_zero_when_trace_incomplete(self) -> None:
        observations = tuple(M2QuestionObservation(True, 6, False, str(index)) for index in range(14))
        report = score_m2_explainability(observations, expected_count=14)
        self.assertEqual(report.explain_score, 0.0)

    def test_embed_request_payload_helpers(self) -> None:
        ollama_body = OllamaClient.embed_request_body(model="nomic-embed-text", texts=["hello"])
        self.assertEqual(ollama_body, {"model": "nomic-embed-text", "input": ["hello"]})
        self.assertEqual(
            OllamaClient.parse_embed_response({"embeddings": [[0.1, 0.2]]}),
            [[0.1, 0.2]],
        )
        lm_body = LMStudioClient.embed_request_body(model="text-embedding", texts=["a", "b"])
        self.assertEqual(lm_body, {"model": "text-embedding", "input": ["a", "b"]})
        self.assertEqual(
            LMStudioClient.parse_embed_response(
                {"data": [{"index": 1, "embedding": [0.0, 1.0]}, {"index": 0, "embedding": [1.0, 0.0]}]}
            ),
            [[1.0, 0.0], [0.0, 1.0]],
        )

    def test_builtin_process_embeddings_are_fail_closed(self) -> None:
        cfg = load_config(PROJECT / "config/default.toml")
        with self.assertRaisesRegex(EmbeddingClientError, "builtin_process"):
            build_embedding_client(cfg)
        backend = LocalLLMProcessBackend(cfg)
        with self.assertRaisesRegex(RuntimeError, "embeddings"):
            backend.embed(["hello"])

    def test_harness_writes_bundle_and_scores_without_live_llm(self) -> None:
        cfg = load_config(PROJECT / "config/ollama.toml")
        questions = load_m4_questions(PROJECT / "data/m4_questions.json")
        self.assertEqual(len(questions), 14)
        ah_answers = {
            item.question_id: InjectedAhAnswer(
                " ".join(item.must_contain),
                used_uids=item.path,
                used_fact_ids=item.path,
            )
            for item in questions
        }
        generator = _FakeGenerator("UNKNOWN")
        with TemporaryDirectory() as td:
            with patch("ah.diagnostics.m4_acceptance._build_isolated_services") as isolated:
                report = run_m4_acceptance(
                    cfg,
                    data_dir=PROJECT / "data",
                    embedder=FakeEmbeddingClient(dim=8),
                    generator=generator,
                    ah_answers=ah_answers,
                    output_dir=td,
                )
            isolated.assert_not_called()
            self.assertTrue(report.passed)
            self.assertIsNone(report.error)
            self.assertIsNotNone(report.m4)
            self.assertGreater(report.ah_explainability or 0.0, 0.0)
            self.assertEqual(report.rag_explainability, 0.0)
            self.assertTrue(all(not item.trace_complete for item in report.rag_cases))
            self.assertEqual(generator.roles, ["m4_rag"] * 14)
            comparison = score_m4_comparison(
                ah_explainability=report.ah_explainability or 0.0,
                rag_explainability=report.rag_explainability or 0.0,
                ah_hallucination=report.ah_hallucination or 0.0,
                rag_hallucination=report.rag_hallucination or 0.0,
            )
            self.assertAlmostEqual(comparison.delta_explainability, report.m4.delta_explainability)
            self.assertGreater(comparison.delta_explainability, 0.0)
            bundle = Path(report.output_dir or "")
            for name in (
                "summary.json",
                "report.txt",
                "config_snapshot.json",
                "questions.json",
                "ah_cases.jsonl",
                "rag_cases.jsonl",
                "index_manifest.json",
            ):
                self.assertTrue((bundle / name).is_file(), name)
            manifest = json.loads((bundle / "index_manifest.json").read_text(encoding="utf-8"))
            self.assertGreater(manifest["chunk_count"], 0)
            self.assertNotIn("vectors", manifest)
            summary = json.loads((bundle / "summary.json").read_text(encoding="utf-8"))
            self.assertIn("m4", summary)
            ah_lines = (bundle / "ah_cases.jsonl").read_text(encoding="utf-8").strip().splitlines()
            rag_lines = (bundle / "rag_cases.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(ah_lines), 14)
            self.assertEqual(len(rag_lines), 14)

    def test_missing_llm_writes_error_bundle_without_synthetic_scores(self) -> None:
        cfg = load_config(PROJECT / "config/default.toml")
        with TemporaryDirectory() as td:
            report = run_m4_acceptance(
                cfg,
                data_dir=PROJECT / "data",
                output_dir=td,
            )
            self.assertFalse(report.passed)
            self.assertIsNotNone(report.error)
            self.assertIsNone(report.m4)
            self.assertIsNone(report.ah_explainability)
            bundle = Path(report.output_dir or "")
            summary = json.loads((bundle / "summary.json").read_text(encoding="utf-8"))
            self.assertIsNone(summary["m4"])
            self.assertTrue((bundle / "report.txt").is_file())


if __name__ == "__main__":
    unittest.main()
