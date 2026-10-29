
"""Offline checks for unsupported claims in AI-generated answers.

These checks flag suspicious claims; they do not prove semantic correctness.
No Ollama calls, API keys, or database writes are required.
"""

import re
import unittest


def check_answer_claims(answer, known_ids=None, known_counts=None):
    """Return warnings for IDs, counts, or write claims needing verification."""
    known_ids = set(known_ids or [])
    known_counts = known_counts or {}

    warnings = []

    # Flag shipment/asset IDs that are not in the supplied evidence.
    found_ids = set(
        re.findall(
            r"\b(?:SHP|AST|RET|REP|INS)-[A-Z0-9-]+\b",
            answer,
            flags=re.IGNORECASE,
        )
    )

    known_ids_upper = {item.upper() for item in known_ids}
    for item in sorted(found_ids):
        if item.upper() not in known_ids_upper:
            warnings.append("Unverified ID: {}".format(item))

    # Flag explicit numeric statements that conflict with known counts.
    for label, expected in known_counts.items():
        pattern = r"\b(\d+)\s+" + re.escape(label) + r"\b"
        for match in re.finditer(pattern, answer, flags=re.IGNORECASE):
            actual = int(match.group(1))
            if actual != expected:
                warnings.append(
                    "Count mismatch for '{}': expected {}, found {}.".format(
                        label, expected, actual
                    )
                )

    # Flag language that may falsely imply a write occurred.
    write_patterns = [
        r"\bI have updated\b",
        r"\bI updated the database\b",
        r"\bI have changed\b",
        r"\bshipment has been marked\b",
        r"\brecord has been modified\b",
    ]

    for pattern in write_patterns:
        if re.search(pattern, answer, flags=re.IGNORECASE):
            warnings.append(
                "Possible unsupported claim that data was changed."
            )
            break

    # Flag wording that turns a potential delay into a confirmed failure.
    if (
        re.search(r"\bpotentially delayed\b", answer, re.IGNORECASE)
        and re.search(
            r"\b(delivery failed|missed delivery|definitely late)\b",
            answer,
            re.IGNORECASE,
        )
    ):
        warnings.append(
            "Potential delay may have been incorrectly stated as a "
            "confirmed delivery failure."
        )

    return warnings


class TestAIHallucinationChecks(unittest.TestCase):

    def test_known_id_is_accepted(self):
        warnings = check_answer_claims(
            "Shipment SHP-TEST-001 is in transit.",
            known_ids=["SHP-TEST-001"],
        )
        self.assertEqual(warnings, [])

    def test_unknown_id_is_flagged(self):
        warnings = check_answer_claims(
            "Shipment SHP-FAKE-999 is delayed.",
            known_ids=["SHP-TEST-001"],
        )
        self.assertTrue(any("Unverified ID" in item for item in warnings))

    def test_incorrect_count_is_flagged(self):
        warnings = check_answer_claims(
            "There are 7 open repairs.",
            known_counts={"open repairs": 3},
        )
        self.assertTrue(any("Count mismatch" in item for item in warnings))

    def test_correct_count_is_accepted(self):
        warnings = check_answer_claims(
            "There are 3 open repairs.",
            known_counts={"open repairs": 3},
        )
        self.assertEqual(warnings, [])

    def test_unsupported_write_claim_is_flagged(self):
        warnings = check_answer_claims(
            "I have updated the shipment record."
        )
        self.assertTrue(any("data was changed" in item for item in warnings))

    def test_potential_delay_claim_is_flagged(self):
        warnings = check_answer_claims(
            "This shipment is potentially delayed and delivery failed."
        )
        self.assertTrue(any("confirmed delivery failure" in item for item in warnings))

    def test_neutral_answer_has_no_warning(self):
        warnings = check_answer_claims(
            "The shipment is in transit. Verify the delivery commitment."
        )
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
