from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json

TEST_SET_SIZE = 10
# 3 summary + 3 authors + 2 date + 2 categories = 10 questions across 4 business types.
QUESTION_TYPES = ["summary", "authors", "date", "categories", "summary", "authors", "date", "categories", "summary", "authors"]


def _question_for(question_type: str, row: pd.Series) -> tuple[str, str]:
    """Question phrasing matches the intent keywords understood by `retrieval.qa._extract_answer`."""
    title = row["title"]
    if question_type == "authors":
        return f"Who authored the paper '{title}'?", row["authors_joined"]
    if question_type == "date":
        return f"When was the paper '{title}' published?", row["published"]
    if question_type == "categories":
        return f"What categories does the paper '{title}' belong to?", row["categories_joined"]
    return f"What is the summary of the paper '{title}'?", first_sentence(row["summary"])


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    # Titles with a single quote would break the '<title>' lookup in qa.py; papers without authors/categories
    # cannot produce a meaningful ground truth for every question type.
    candidates = df[
        ~df["title"].str.contains("'", regex=False)
        & (df["authors_joined"].str.len() > 0)
        & (df["categories_joined"].str.len() > 0)
        & (df["summary"].str.len() > 0)
    ].drop_duplicates("paper_id")
    candidates = candidates.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    if len(candidates) < TEST_SET_SIZE:
        raise ValueError(f"Need at least {TEST_SET_SIZE} valid documents to build the test set, got {len(candidates)}.")

    # Spread the sample evenly from newest to oldest so every age bucket is represented.
    step = (len(candidates) - 1) / (TEST_SET_SIZE - 1)
    picks = [round(i * step) for i in range(TEST_SET_SIZE)]

    test_set: list[dict[str, Any]] = []
    for number, (row_index, question_type) in enumerate(zip(picks, QUESTION_TYPES, strict=True), start=1):
        row = candidates.iloc[row_index]
        question, ground_truth = _question_for(question_type, row)
        test_set.append(
            {
                "id": f"eval_{number:03d}",
                "question_type": question_type,
                "question": question,
                "ground_truth": ground_truth,
                "ground_truth_doc_ids": [row["paper_id"]],
            }
        )

    write_json(output_path, test_set)
    return test_set
