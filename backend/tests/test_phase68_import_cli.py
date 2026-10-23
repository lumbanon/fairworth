"""The operator report cannot overwrite archived listing/reference originals."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


@pytest.mark.parametrize("operation", ["preview", "apply"])
@pytest.mark.parametrize("destination", ["nasdaqlisted", "company_tickers_exchange", "acquisition_manifest"])
def test_report_output_cannot_overwrite_archived_originals(tmp_path, monkeypatch, operation, destination):
    originals = {key: tmp_path / (key + ".raw")
                 for key in ("nasdaqlisted", "company_tickers_exchange", "acquisition_manifest")}
    for path in originals.values():
        path.write_text("retained original bytes", encoding="utf-8")
    spec = tmp_path / "archived-spec.json"
    spec.write_text(json.dumps({"sources": {key: str(originals[key])
        for key in ("nasdaqlisted", "company_tickers_exchange")},
        "acquisition_manifest": str(originals["acquisition_manifest"])}), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "import_sec_financials.py"
    loaded = importlib.util.spec_from_file_location("phase68_import_output_guard", script)
    module = importlib.util.module_from_spec(loaded)
    loaded.loader.exec_module(module)
    def forbidden():
        pytest.fail("Unsafe output must be rejected before loading database configuration or applying an import.")
    monkeypatch.setattr(module, "Settings", forbidden)
    if operation == "preview":
        argv = [str(script), "preview", "--manifest", str(tmp_path / "financial-manifest.json"),
            "--source", f"MSFT={tmp_path / 'financial.json'}", "--as-of", "2026-10-22T06:51:30Z",
            "--archived-security-package", str(spec), "--output", str(originals[destination])]
    else:
        preview = tmp_path / "preview.json"
        preview.write_text(json.dumps({"sources": [], "archived_security": {"spec_file": str(spec)}}), encoding="utf-8")
        argv = [str(script), "apply", "--preview", str(preview), "--confirm", "APPLY reviewed-digest",
                "--output", str(originals[destination])]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert all(path.read_text(encoding="utf-8") == "retained original bytes" for path in originals.values())
