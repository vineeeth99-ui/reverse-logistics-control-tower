
"""Fast, offline tests for assistant grounding and safety contracts.

These tests mock Ollama and ChromaDB dependencies. They verify that the
assistant validates inputs, passes operational evidence and retrieved rules
to the LLM, and preserves safety instructions. They do not prove that an
LLM will always follow those instructions; live-model evaluation is separate.
"""

import unittest
from unittest.mock import patch

from src.services.assistant_service import answer_question


class TestAssistantGuardrails(unittest.TestCase):

    def setUp(self):
        self.context = {
            "shipment_delay_threshold_days": 3,
            "potentially_delayed_shipments": [
                {
                    "shipment_id": "SHP-TEST-001",
                    "shipment_status": "In Transit",
                    "days_since_dispatch": 5.2,
                }
            ],
            "read_only": True,
        }

    def test_empty_question_is_rejected_before_retrieval(self):
        with patch(
            "src.services.assistant_service.search_documents"
        ) as search:
            with self.assertRaisesRegex(ValueError, "enter a question"):
                answer_question("   ", self.context)

            search.assert_not_called()

    def test_non_dictionary_context_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError, "context must be a dictionary"
        ):
            answer_question("Which shipments may be delayed?", [])

    @patch(
        "src.services.assistant_service.generate_response",
        return_value="One shipment is potentially delayed.",
    )
    @patch(
        "src.services.assistant_service.search_documents",
        return_value=[
            {
                "source": "documents/logistics_rules.md",
                "text": (
                    "Potential delay is not proof of a missed commitment."
                ),
                "distance": 0.1,
            }
        ],
    )
    def test_operational_context_and_retrieved_rule_are_sent_to_model(
        self, mock_search, mock_generate
    ):
        answer = answer_question(
            "Which shipments may be delayed?", self.context
        )

        self.assertEqual(
            answer, "One shipment is potentially delayed."
        )

        mock_search.assert_called_once_with(
            "Which shipments may be delayed?", n_results=3
        )
        mock_generate.assert_called_once()

        call_kwargs = mock_generate.call_args.kwargs
        prompt = call_kwargs["prompt"]
        system_prompt = call_kwargs["system_prompt"]

        self.assertIn("SHP-TEST-001", prompt)
        self.assertIn("Potential delay is not proof", prompt)
        self.assertIn(
            "VERIFIED OPERATIONAL DATABASE CONTEXT", prompt
        )
        self.assertIn("RETRIEVED BUSINESS DOCUMENTS", prompt)
        self.assertIn("Never invent IDs, statuses, dates, or counts.", system_prompt)
        self.assertIn("Never claim to have changed database records.", system_prompt)
        self.assertIn("missed", system_prompt.lower())

    @patch("src.services.assistant_service.generate_response")
    @patch(
        "src.services.assistant_service.search_documents",
        side_effect=RuntimeError("vector store unavailable"),
    )
    def test_retrieval_failure_does_not_call_llm(
        self, mock_search, mock_generate
    ):
        with self.assertRaisesRegex(
            RuntimeError, "Local document retrieval failed"
        ):
            answer_question(
                "Explain the delay rule", self.context
            )

        mock_generate.assert_not_called()

    @patch(
        "src.services.assistant_service.generate_response",
        return_value="No matching evidence is available.",
    )
    @patch(
        "src.services.assistant_service.search_documents",
        return_value=[],
    )
    def test_no_retrieved_documents_is_explicit_in_prompt(
        self, mock_search, mock_generate
    ):
        answer_question(
            "Explain an undocumented rule", self.context
        )

        prompt = mock_generate.call_args.kwargs["prompt"]

        self.assertIn(
            "No relevant business-rule documents were retrieved",
            prompt,
        )
        self.assertIn(
            "Do not invent undocumented rules", prompt
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
