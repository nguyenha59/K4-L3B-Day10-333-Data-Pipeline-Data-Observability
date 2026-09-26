from __future__ import annotations

from dataclasses import replace

import pytest

from core.config import normalized_provider, require_llm_credentials
from core.utils import first_sentence
from retrieval import agent as agent_module
from retrieval.index import LocalEmbeddingIndex
from retrieval.llm import build_llm
from retrieval.qa import answer_question


@pytest.fixture(scope="module")
def index(clean_df, tmp_path_factory):
    from conftest import make_sandbox

    settings = make_sandbox(tmp_path_factory.mktemp("retrieval") / "project")
    return LocalEmbeddingIndex.build(clean_df, settings)


# ---------------------------------------------------------------- index.py (ChromaDB + MiniLM)
def test_index_builds_baseline_collection(index, clean_df):
    assert index.collection_name == "papers-baseline"
    assert index.collection.count() == len(clean_df) == 24
    assert index.settings.paths.embeddings_json.exists()


def test_semantic_search_finds_paper_by_its_summary(index, clean_df):
    row = clean_df.iloc[5]
    results = index.search(row["summary"], top_k=3)
    assert len(results) == 3
    assert results[0].paper_id == row["paper_id"]
    assert results[0].score >= results[-1].score


def test_lookup_by_id_or_title(index, clean_df):
    row = clean_df.iloc[0]
    assert index.lookup(row["paper_id"].upper())["title"] == row["title"]
    assert index.lookup(f"  {row['title']}  ")["paper_id"] == row["paper_id"]
    assert index.lookup("no such paper") is None


def test_load_from_manifest_and_collection_names(index):
    settings = index.settings
    loaded = LocalEmbeddingIndex.load(settings)
    assert loaded.collection_name == index.collection_name
    assert len(loaded.documents) == 24
    derive = LocalEmbeddingIndex._derive_collection_name
    assert derive(settings, settings.paths.corrupted_embeddings_json) == "papers-corrupted"
    assert derive(settings, settings.paths.repaired_embeddings_json) == "papers-repaired"
    assert derive(settings, settings.paths.project_dir / "My Custom_Index.json") == "my-custom-index"


# ---------------------------------------------------------------- qa.py
@pytest.mark.parametrize(
    ("template", "field"),
    [
        ("Who authored the paper '{title}'?", "authors_joined"),
        ("When was the paper '{title}' published?", "published"),
        ("What categories does the paper '{title}' belong to?", "categories_joined"),
        ("What is the summary of the paper '{title}'?", None),
    ],
)
def test_answer_question_extracts_expected_field(index, clean_df, template, field):
    row = clean_df.iloc[3]
    result = answer_question(template.format(title=row["title"]), settings=index.settings, index=index)
    expected = row[field] if field else first_sentence(row["summary"])
    assert result.answer == expected
    assert result.retrieved_doc_ids[0] == row["paper_id"]
    assert len(result.retrieved_doc_ids) == index.settings.top_k


# ---------------------------------------------------------------- llm.py / config.py
def test_provider_normalization_and_credentials(settings):
    assert normalized_provider(replace(settings, llm_provider=" Anthorpic ")) == "anthropic"
    assert normalized_provider(replace(settings, llm_provider="custom-llm")) == "custom"
    for provider in ("gemini", "openai", "anthropic", "openrouter", "custom"):
        with pytest.raises(RuntimeError):
            require_llm_credentials(
                replace(
                    settings,
                    llm_provider=provider,
                    google_api_key=None,
                    openai_api_key=None,
                    anthropic_api_key=None,
                    openrouter_api_key=None,
                    custom_llm_base_url=None,
                )
            )
    with pytest.raises(RuntimeError, match="Unsupported"):
        require_llm_credentials(replace(settings, llm_provider="nope"))


@pytest.mark.parametrize(
    ("provider", "class_name"),
    [
        ("gemini", "ChatGoogleGenerativeAI"),
        ("openai", "ChatOpenAI"),
        ("anthropic", "ChatAnthropic"),
        ("openrouter", "ChatOpenAI"),
        ("ollama", "ChatOllama"),
        ("custom", "ChatOpenAI"),
        ("mock", "FakeListChatModel"),
    ],
)
def test_build_llm_routes_each_provider(settings, provider, class_name):
    configured = replace(
        settings,
        llm_provider=provider,
        model_name="test-model",
        google_api_key="fake",
        openai_api_key="fake",
        anthropic_api_key="fake",
        openrouter_api_key="fake",
        custom_llm_base_url="http://localhost:9999/v1",
    )
    assert type(build_llm(configured)).__name__ == class_name


def test_mock_llm_answers_offline(settings):
    assert "mock" in build_llm(settings).invoke("hi").content


# ---------------------------------------------------------------- agent.py
def test_agent_tools_query_the_index(index, clean_df, monkeypatch):
    monkeypatch.setattr(agent_module, "create_agent", lambda **kwargs: kwargs)
    config = agent_module.build_agent(index.settings, index)
    search_tool, lookup_tool = config["tools"]
    row = clean_df.iloc[2]
    assert row["paper_id"] in search_tool.invoke({"query": row["summary"], "top_k": 2})
    assert row["title"] in lookup_tool.invoke({"paper_id_or_title": row["paper_id"]})
    assert lookup_tool.invoke({"paper_id_or_title": "missing"}) == "No exact paper match found."


def test_run_agent_question_returns_last_message():
    class FakeMessage:
        content = "final answer"

    class FakeAgent:
        def __init__(self, messages):
            self.messages = messages

        def invoke(self, payload):
            return {"messages": self.messages}

    assert agent_module.run_agent_question(FakeAgent([object(), FakeMessage()]), "q") == "final answer"
    assert agent_module.run_agent_question(FakeAgent([]), "q") == ""
