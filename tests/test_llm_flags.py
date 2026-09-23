from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LLM_FLAGS = ROOT / "bin/hermes/llm-flags.sh"


def run_bash(snippet: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'. "{LLM_FLAGS}"\n{snippet}'],
        capture_output=True,
        text=True,
    )


class LlmFlagsHelperTest(unittest.TestCase):
    def test_model_splits_known_provider(self):
        proc = run_bash(
            'parse_llm_flags --model together/zai-org/GLM-5.3-Flash || exit 1\n'
            'printf "provider=%s\\n" "$LLM_FLAGS_PROVIDER"\n'
            'printf "model=%s\\n" "$LLM_FLAGS_MODEL"\n'
            'printf "rest=%s\\n" "${LLM_FLAGS_REST[*]}"'
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "provider=together\nmodel=zai-org/GLM-5.3-Flash\nrest=\n")

    def test_slashed_model_without_known_provider_stays_whole(self):
        proc = run_bash(
            'parse_llm_flags --model together-ai/foo || exit 1\n'
            'printf "provider=%s\\n" "$LLM_FLAGS_PROVIDER"\n'
            'printf "model=%s\\n" "$LLM_FLAGS_MODEL"'
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "provider=\nmodel=together-ai/foo\n")

    def test_flags_equal_forms_and_passthrough(self):
        proc = run_bash(
            'parse_llm_flags --provider=openai-codex --model=gpt-5.5 --thinking=high -- extra || exit 1\n'
            'printf "provider=%s\\n" "$LLM_FLAGS_PROVIDER"\n'
            'printf "model=%s\\n" "$LLM_FLAGS_MODEL"\n'
            'printf "thinking=%s\\n" "$LLM_FLAGS_THINKING"\n'
            'printf "rest=%s\\n" "${LLM_FLAGS_REST[*]}"'
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "provider=openai-codex\nmodel=gpt-5.5\nthinking=high\nrest=-- extra\n")

    def test_provider_conflict_with_split_model_errors(self):
        proc = run_bash(
            'parse_llm_flags --provider cursor --model together/zai-org/GLM-5.3-Flash'
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("conflicting", proc.stderr)

    def test_export_writes_launcher_envs(self):
        proc = run_bash(
            'parse_llm_flags --model cursor/grok-4.6:slow --thinking high || exit 1\n'
            'llm_flags_export\n'
            'printf "p=%s\\n" "${HERMES_AGENT_LLM_PROVIDER-}"\n'
            'printf "m=%s\\n" "${HERMES_AGENT_LLM_MODEL-}"\n'
            'printf "t=%s\\n" "${HERMES_AGENT_LLM_THINKING-}"\n'
            'printf "alias=%s\\n" "${HERMES_MODEL-}"'
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "p=cursor\nm=grok-4.6:slow\nt=high\nalias=grok-4.6:slow\n")

    def test_missing_value_fails(self):
        proc = run_bash('parse_llm_flags --model')
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()