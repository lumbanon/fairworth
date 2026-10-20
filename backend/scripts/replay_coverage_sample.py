"""Offline, dated public-fixture audit; requires backend test dependencies."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "tests")]
import httpx
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app.core.database import Base, build_session_factory
import app.models  # Register all SQL mappings on this new in-memory database.
from app.registry.audit import summarize
from coverage_sample_helpers import replay_reference_sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses", help="Optional output for exact saved CoverageResponse samples.")
    parser.add_argument("--output", help="Optional summarized audit output; otherwise stdout.")
    args = parser.parse_args()
    def blocked(*_args, **_kwargs):
        raise RuntimeError("External HTTP is forbidden during this offline replay.")
    async def async_blocked(*_args, **_kwargs):
        blocked()
    httpx.HTTPTransport.handle_request = blocked
    httpx.AsyncHTTPTransport.handle_async_request = async_blocked
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    try:
        Base.metadata.create_all(engine)
        bundle = asyncio.run(replay_reference_sample(build_session_factory(engine)))
        report = summarize(bundle)
        if args.responses:
            Path(args.responses).write_text(json.dumps(bundle, default=str, indent=2) + "\n", encoding="utf-8")
        output = json.dumps(report, sort_keys=True, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            print(output, end="")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
