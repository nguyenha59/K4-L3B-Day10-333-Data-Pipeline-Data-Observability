from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import shutil

import pandas as pd
import pytest

# Tests must be offline, deterministic and free: force the mock LLM and the local Crossref snapshot.
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_MODEL"] = "mock"
for _name in ("REFRESH_SOURCE", "REFRESH_TEST_SET", "RUN_RAGAS"):
    os.environ.pop(_name, None)

from core.config import Settings, load_settings  # noqa: E402
from ingestion.cleaning import build_clean_dataframe  # noqa: E402
from ingestion.crossref import load_raw_records  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
RUN_DATE = datetime(2026, 9, 26, tzinfo=UTC)


def make_sandbox(root: Path) -> Settings:
    """Isolated project dir with a copy of the raw snapshot, so tests never touch real artifacts."""
    raw = root / "data" / "raw"
    raw.mkdir(parents=True)
    for name in ("crossref_response.json", "crossref_records.json"):
        shutil.copy(RAW_DIR / name, raw / name)
    return load_settings(project_dir=root)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_sandbox(tmp_path / "project")


@pytest.fixture(scope="session")
def raw_records():
    return load_raw_records(RAW_DIR / "crossref_records.json")


@pytest.fixture(scope="session")
def clean_df(raw_records) -> pd.DataFrame:
    return build_clean_dataframe(raw_records, RUN_DATE)


@pytest.fixture(scope="session")
def e2e(tmp_path_factory) -> dict:
    """Run the full baseline + corruption/repair flow once per test session."""
    from pipelines.corruption_flow import run_corruption_flow_pipeline
    from pipelines.phase1 import run_phase1_pipeline

    settings = make_sandbox(tmp_path_factory.mktemp("e2e") / "project")
    phase1 = run_phase1_pipeline(settings)
    flow = run_corruption_flow_pipeline(settings)
    return {"settings": settings, "phase1": phase1, "flow": flow}
