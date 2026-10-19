"""Read-only SQL listing aggregates and optional local financial sample audit.

This command never acquires provider data, changes the database, or generates AI.
"""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.database import build_engine, build_session_factory
from app.registry.coverage_audit import MODES, financial_matrix, markdown_matrix, registry_counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True, help="Explicit audit calendar date.")
    parser.add_argument("--data-mode", choices=sorted(MODES), required=True)
    parser.add_argument("--max-age-days", type=int, default=1)
    parser.add_argument("--financial-sample", help="Optional bounded local CoverageResponse bundle; never downloaded.")
    parser.add_argument("--matrix-output", help="Optional Markdown matrix for that same sample.")
    parser.add_argument("--output", help="Write JSON to this local path; otherwise stdout.")
    args = parser.parse_args()
    if args.matrix_output and not args.financial_sample:
        parser.error("--matrix-output requires --financial-sample")
    engine = build_engine(get_settings().database_url)
    try:
        result = {"registry": registry_counts(build_session_factory(engine), as_of=args.as_of,
            data_mode=args.data_mode, max_age_days=args.max_age_days)}
        if args.financial_sample:
            file = Path(args.financial_sample)
            if file.stat().st_size > 25_000_000:
                raise ValueError("Financial sample exceeds the bounded local audit size.")
            result["financial_sample"] = financial_matrix(json.loads(file.read_text(encoding="utf-8")))
            if args.matrix_output:
                Path(args.matrix_output).write_text(markdown_matrix(result["financial_sample"]), encoding="utf-8")
        output = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            print(output, end="")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
