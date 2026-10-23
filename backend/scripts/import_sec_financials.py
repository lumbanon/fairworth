"""Preview retained SEC evidence, or explicitly apply one reviewed preview.

No downloads, implicit imports, database creation, or schema upgrades occur.
The apply confirmation is meaningful only after the operator separately obtains
authorization for the displayed source hashes and database write plan.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.services.financial_import_service import apply_preview, build_preview


def archived_original_paths(spec_path, parser):
    """Resolve all originals before opening any database connection."""
    path = Path(spec_path).resolve()
    try:
        if not 0 < path.stat().st_size <= 100_000:
            parser.error("The archived security specification exceeds its bounded size limit.")
        spec = json.loads(path.read_text(encoding="utf-8"))
        sources = spec.get("sources")
        if (not isinstance(sources, dict) or not isinstance(spec.get("acquisition_manifest"), str)
                or not all(isinstance(value, str) for value in sources.values())):
            parser.error("The archived security specification must identify its original local source files.")
        return {path, Path(spec["acquisition_manifest"]).resolve(),
                *(Path(value).resolve() for value in sources.values())}
    except (OSError, ValueError, AttributeError):
        parser.error("The archived security specification could not be read safely.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    preview = commands.add_parser("preview", help="Read-only; never authorizes apply.")
    preview.add_argument("--manifest", required=True, type=Path)
    preview.add_argument("--source", required=True, action="append", metavar="TICKER=PATH")
    preview.add_argument("--as-of", required=True)
    preview.add_argument("--archived-security-package", type=Path,
                         help="Optional exact retained MSFT listing/reference attachment; never refreshes the installed registry.")
    preview.add_argument("--output", required=True, type=Path)
    apply = commands.add_parser("apply", help="Requires separately authorized exact preview.")
    apply.add_argument("--preview", required=True, type=Path)
    apply.add_argument("--confirm", required=True, help="Exact literal: APPLY <preview_digest>")
    apply.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.operation == "preview":
        specs = []
        for value in args.source:
            ticker, separator, path = value.partition("=")
            if not separator or not ticker or not path:
                parser.error("Each source must be TICKER=PATH.")
            specs.append({"ticker": ticker, "source": path, "manifest": str(args.manifest)})
        protected = {Path(row["source"]).resolve() for row in specs} | {args.manifest.resolve()}
        if args.archived_security_package:
            protected.update(archived_original_paths(args.archived_security_package, parser))
    else:
        if args.preview.stat().st_size > 2_000_000:
            parser.error("The preview manifest exceeds the bounded size limit.")
        frozen = json.loads(args.preview.read_text(encoding="utf-8"))
        protected = {args.preview.resolve()}
        protected.update(Path(row["source_files"][field]).resolve() for row in frozen.get("sources", [])
                         for field in ("source", "manifest"))
        if frozen.get("archived_security"):
            protected.update(archived_original_paths(frozen["archived_security"]["spec_file"], parser))
    if args.output.resolve() in protected:
        parser.error("The output must not overwrite original evidence or its preview/acquisition manifest.")
    settings = Settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1"}:
        parser.error("Use the existing configured local PostgreSQL database; no database is created.")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        if args.operation == "preview":
            report = build_preview(engine, specs, as_of=args.as_of, sec_cache_ttl_seconds=settings.sec_cache_ttl_seconds,
                                   archived_security_package=args.archived_security_package)
            output = {"mode": report["mode"], "preview_digest": report["preview_digest"],
                      "totals": report["totals"], "migration_required": report["migration_required"],
                      "apply_blocked": report["apply_blocked"]}
        else:
            report = apply_preview(engine, frozen, confirmation=args.confirm)
            output = {"batch_id": report["batch_id"], "already_applied": report["already_applied"],
                      "row_changes": report["row_changes"], "original_rows_preserved": report["original_rows_preserved"]}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, default=str, allow_nan=False), encoding="utf-8")
        print(json.dumps(output))
    except Exception as error:
        # Never expose a driver connection string, configured password or raw
        # provider/contact fields through a traceback in this operator command.
        if isinstance(error, ValueError):
            parser.error(str(error))
        parser.error(f"{type(error).__name__}: operation failed; any import transaction was rolled back.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
