from __future__ import annotations

from datetime import datetime
import math
import random
import string
from typing import Any

import pandas as pd

from core.utils import now_utc, write_json
from ingestion.cleaning import add_derived_columns

SEED = 20260926
DROP_LATEST_RATIO = 0.20
BLANK_SUMMARY_ROWS = 3
NOISE_ROWS = 3
TRUNCATE_TITLE_ROWS = 3
TRUNCATED_TITLE_CHARS = 6
STALE_RATIO = 0.30
STALE_SHIFT_DAYS = 365
DUPLICATE_ROWS = 2


def _noise_token(rng: random.Random) -> str:
    return "".join(rng.choice(string.ascii_letters + string.digits + "#@$%&~^") for _ in range(rng.randint(4, 9)))


def _inject_noise(text: str, rng: random.Random) -> str:
    """Replace roughly half of the words with random garbage tokens."""
    words = text.split()
    return " ".join(_noise_token(rng) if rng.random() < 0.5 else word for word in words)


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path, run_date: datetime | None = None) -> pd.DataFrame:
    rng = random.Random(SEED)
    run_date = run_date or now_utc()
    corrupted = df.copy().reset_index(drop=True)
    scenarios: list[dict[str, Any]] = []
    rows_before = len(corrupted)

    # 1. Drop latest records: the newest 20% silently disappear (e.g. an incremental load failed).
    drop_count = max(1, round(rows_before * DROP_LATEST_RATIO))
    latest = corrupted.sort_values("published", ascending=False).head(drop_count)
    corrupted = corrupted.drop(index=latest.index).reset_index(drop=True)
    scenarios.append(
        {
            "scenario": "drop_latest_records",
            "rows_affected": drop_count,
            "description": f"Removed the {drop_count} most recently published papers ({DROP_LATEST_RATIO:.0%}).",
            "changes": [
                {"paper_id": pid, "field": "<row>", "before": published, "after": None}
                for pid, published in zip(latest["paper_id"], latest["published"], strict=True)
            ],
        }
    )

    # Scenarios 2-5 touch disjoint rows so each effect stays attributable in the log.
    available = list(corrupted.index)
    rng.shuffle(available)

    def take(count: int) -> list[int]:
        picked = available[:count]
        del available[:count]
        return picked

    def mutate(rows: list[int], field: str, new_values: list[Any]) -> list[dict[str, Any]]:
        """Apply new values to one field and return a before/after record per changed row."""
        before = corrupted.loc[rows, field].tolist()
        corrupted.loc[rows, field] = new_values
        return [
            {"paper_id": pid, "field": field, "before": old, "after": new}
            for pid, old, new in zip(corrupted.loc[rows, "paper_id"], before, new_values, strict=True)
        ]

    # 2. Blank summary: abstract lost upstream.
    rows = take(BLANK_SUMMARY_ROWS)
    changes = mutate(rows, "summary", [""] * len(rows))
    scenarios.append(
        {
            "scenario": "blank_summary",
            "rows_affected": len(rows),
            "description": "Summary replaced with an empty string.",
            "changes": changes,
        }
    )

    # 3. Inject noise: encoding/scraping garbage mixed into the abstract.
    rows = take(NOISE_ROWS)
    changes = mutate(rows, "summary", [_inject_noise(text, rng) for text in corrupted.loc[rows, "summary"]])
    scenarios.append(
        {
            "scenario": "inject_noise",
            "rows_affected": len(rows),
            "description": "About 50% of summary words replaced with random garbage tokens.",
            "changes": changes,
        }
    )

    # 4. Truncate title below the 8-character validity threshold.
    rows = take(TRUNCATE_TITLE_ROWS)
    changes = mutate(rows, "title", [title[:TRUNCATED_TITLE_CHARS] for title in corrupted.loc[rows, "title"]])
    scenarios.append(
        {
            "scenario": "truncate_title",
            "rows_affected": len(rows),
            "description": f"Title cut to {TRUNCATED_TITLE_CHARS} characters (below the 8-character threshold).",
            "changes": changes,
        }
    )

    # 5. Stale date: published date shifted into the past, breaking the freshness SLA.
    rows = take(math.ceil(len(corrupted) * STALE_RATIO))
    shifted = pd.to_datetime(corrupted.loc[rows, "published"]) - pd.Timedelta(days=STALE_SHIFT_DAYS)
    changes = mutate(rows, "published", shifted.dt.strftime("%Y-%m-%d").tolist())
    corrupted.loc[rows, "updated"] = corrupted.loc[rows, "published"]
    scenarios.append(
        {
            "scenario": "stale_date",
            "rows_affected": len(rows),
            "description": f"Published date moved back {STALE_SHIFT_DAYS} days on {STALE_RATIO:.0%} of rows.",
            "changes": changes,
        }
    )

    # 6. Duplicate rows: a retried load appended the same records twice.
    duplicate_source = sorted(rng.sample(list(corrupted.index), DUPLICATE_ROWS))
    duplicates = corrupted.loc[duplicate_source]
    corrupted = pd.concat([corrupted, duplicates], ignore_index=True)
    scenarios.append(
        {
            "scenario": "duplicate_rows",
            "rows_affected": len(duplicates),
            "description": f"Appended {len(duplicates)} exact duplicate rows (paper_id no longer unique).",
            "changes": [{"paper_id": pid, "field": "<row>", "before": 1, "after": 2} for pid in duplicates["paper_id"]],
        }
    )

    # 7. Rebuild derived columns so text_for_embedding / age_days reflect the corrupted base data.
    corrupted = add_derived_columns(corrupted, run_date)

    write_json(
        output_log_path,
        {
            "seed": SEED,
            "run_date": run_date.isoformat(timespec="seconds"),
            "rows_before": rows_before,
            "rows_after": len(corrupted),
            "scenarios": scenarios,
        },
    )
    return corrupted
