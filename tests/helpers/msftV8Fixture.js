import { readFileSync } from "node:fs";

// Exact successful authorized v8 capture, replayed offline after boundary-only
// spacing changes. All financial values and provenance remain unrounded here.
export function msftV8PresentationFixture() {
  const saved = JSON.parse(readFileSync(new URL("../../backend/tests/fixtures/ai/msft_v8_success.json", import.meta.url), "utf8"));
  const { registry, ...snapshot } = saved.evidence_package;
  return {
    ...snapshot, evidence_references: Object.values(registry),
    generated_at: "2026-10-17T07:03:43.663351Z", snapshot_token: "offline-v8-replay-snapshot",
    answer: saved.expected_presented_findings,
  };
}
