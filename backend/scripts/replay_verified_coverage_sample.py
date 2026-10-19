"""Offline replay of the approved dated 30-security excerpts; needs test dependencies."""
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
import app.models
from app.registry.coverage_audit import financial_matrix, markdown_matrix
from phase66_coverage_helpers import replay_verified_sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses")
    parser.add_argument("--output")
    parser.add_argument("--matrix-output")
    args = parser.parse_args()
    def blocked(*_args, **_kwargs):
        raise RuntimeError("HTTP is forbidden during the dated replay.")
    async def async_blocked(*_args, **_kwargs):
        blocked()
    httpx.HTTPTransport.handle_request = blocked
    httpx.AsyncHTTPTransport.handle_async_request = async_blocked
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    try:
        Base.metadata.create_all(engine)
        bundle = asyncio.run(replay_verified_sample(build_session_factory(engine)))
        report = financial_matrix(bundle)
        if args.responses:
            Path(args.responses).write_text(json.dumps(bundle, indent=2, default=str) + "\n", encoding="utf-8")
        if args.matrix_output:
            Path(args.matrix_output).write_text(markdown_matrix(report), encoding="utf-8")
        output = json.dumps(report, indent=2, default=str) + "\n"
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            print(output, end="")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
