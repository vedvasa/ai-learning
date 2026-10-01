from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import subprocess
import sys

import psycopg

from ai_learning.golden_retrieval import DEFAULT_CORPUS, GoldenDatasetError
from ai_learning.retrieval_drafts import DEFAULT_DRAFT_DIRECTORY
from ai_learning.retrieval_evaluation import _atomic_write, _read_results
from ai_learning.retrieval_working_set import DEFAULT_REVIEWED_WORKSHEET, load_evaluation_dataset
from app.rag.documents import load_corpus
from app.rag.embeddings import OpenAIEmbeddingClient
from app.schemas.retrieval_evaluation import VectorEvaluationConfiguration
from app.schemas.vector_capture import VectorCapture
from app.services.retrieval_evaluation import (
    RetrievalEvaluationError, compare_retrieval_reports, evaluate_retrieval, render_retrieval_markdown,
)
from app.services.vector_evaluation import (
    capture_plan, capture_vectors, execute_local_vectors, prepare_vector_inputs, validate_capture,
)


def _source_revision():
    if subprocess.run(["git", "status", "--porcelain"], capture_output=True, check=True, text=True).stdout:
        raise RetrievalEvaluationError("Commit the source changes before capturing or executing a baseline.")
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, check=True, text=True).stdout.strip()


def _prompt_api_key():
    if not sys.stdin.isatty():
        raise RetrievalEvaluationError("Run capture in an interactive terminal for hidden API-key entry.")
    return getpass.getpass("OpenAI API key (hidden; not saved): ")


def _local_connection(port):
    # Fixed disposable Supabase development endpoint. No settings, .env, remote
    # connection option, or user-supplied database URL is read by this command.
    return psycopg.connect(
        host="127.0.0.1", hostaddr="127.0.0.1", port=port, dbname="postgres",
        user="postgres", password="postgres", connect_timeout=5,
        options="-c statement_timeout=30000", autocommit=False,
    )


def build_parser():
    parser = argparse.ArgumentParser(description="Capture embeddings once; repeat exact vector evaluation locally.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="Count inputs without providers or database access.")
    mode.add_argument("--capture-to", type=Path, help="Paid embeddings only; writes a new capture file.")
    mode.add_argument("--execute", type=Path, help="Re-execute a vector capture in temporary local Supabase tables.")
    parser.add_argument("--worksheet", type=Path, default=DEFAULT_REVIEWED_WORKSHEET)
    parser.add_argument("--draft-directory", type=Path, default=DEFAULT_DRAFT_DIRECTORY)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--confirm-spend", action="store_true")
    parser.add_argument("--maximum-input-tokens", type=int, default=12000)
    parser.add_argument("--chunk-max-tokens", type=int, default=500)
    parser.add_argument("--local-port", type=int, default=54322)
    parser.add_argument("--output-directory", type=Path, default=Path("artifacts/vector-baseline"))
    parser.add_argument("--baseline-results", type=Path)
    parser.add_argument("--maximum-metric-drop", type=float, default=0)
    return parser


def run_cli(args):
    try:
        dataset = load_evaluation_dataset(
            worksheet=args.worksheet, corpus_directory=args.corpus,
            include_provisional=True, draft_directory=args.draft_directory,
        )
        corpus = load_corpus(args.corpus)
        config = VectorEvaluationConfiguration(chunk_max_tokens=args.chunk_max_tokens)
        if args.maximum_input_tokens <= 0 or not 1 <= args.local_port <= 65535:
            raise RetrievalEvaluationError("Invalid token budget or local port.")
        if args.execute is None and (args.baseline_results is not None or args.maximum_metric_drop != 0):
            raise RetrievalEvaluationError("Baseline comparisons require --execute.")
        if args.execute is not None and args.maximum_metric_drop != 0 and args.baseline_results is None:
            raise RetrievalEvaluationError("A drop allowance requires --baseline-results.")
        if args.plan or args.capture_to:
            chunks = prepare_vector_inputs(dataset, corpus, config)
            plan = capture_plan(dataset, chunks, config)
            print(json.dumps(plan, sort_keys=True))
            if args.plan:
                return 0
            if not args.confirm_spend:
                raise RetrievalEvaluationError("--confirm-spend is required for paid capture.")
            if plan["estimated_input_tokens"] > args.maximum_input_tokens:
                raise RetrievalEvaluationError("Planned embedding inputs exceed the token budget.")
            if args.capture_to.exists():
                raise RetrievalEvaluationError("Capture output already exists; it will not be overwritten.")
            revision = _source_revision()
            client = OpenAIEmbeddingClient(
                api_key=_prompt_api_key(), model=config.embedding_model,
                dimensions=config.embedding_dimensions, batch_size=64,
            )
            capture = capture_vectors(dataset, corpus, config, client=client, source_revision=revision)
            args.capture_to.parent.mkdir(parents=True, exist_ok=True)
            with args.capture_to.open("x", encoding="utf-8") as output:
                output.write(capture.model_dump_json() + "\n")
            print(f"Captured {len(capture.chunks)} chunk and {len(capture.queries)} query vectors; "
                  f"provider tokens: {capture.embedding_input_tokens}; calls: {capture.embedding_calls}. "
                  "No database was accessed.")
            return 0

        capture = VectorCapture.model_validate_json(args.execute.read_text(encoding="utf-8"))
        validate_capture(capture, dataset, corpus)
        if args.chunk_max_tokens != capture.configuration.chunk_max_tokens:
            raise RetrievalEvaluationError("Requested chunk configuration does not match the capture.")
        outputs = [args.output_directory / name for name in ("results.json", "report.json", "report.md")]
        inputs = [args.execute, args.worksheet, *args.draft_directory.glob("*.json")]
        if args.baseline_results is not None:
            inputs.append(args.baseline_results)
        if any(path.resolve() in {source.resolve() for source in inputs}
               or path.resolve().is_relative_to(args.corpus.resolve()) for path in outputs):
            raise RetrievalEvaluationError("Outputs must not overwrite evaluation inputs.")
        revision = _source_revision()
        connection = _local_connection(args.local_port)
        try:
            run = execute_local_vectors(connection, capture, dataset, corpus, source_revision=revision)
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()
        report = evaluate_retrieval(dataset, corpus, run).model_copy(update={"evaluation_mode": "local_vector_execution"})
        if args.baseline_results is not None:
            baseline = evaluate_retrieval(dataset, corpus, _read_results(args.baseline_results))
            report = compare_retrieval_reports(report, baseline, maximum_metric_drop=args.maximum_metric_drop)
        _atomic_write(outputs[0], run.model_dump_json(indent=2) + "\n")
        _atomic_write(outputs[1], report.model_dump_json(indent=2) + "\n")
        _atomic_write(outputs[2], render_retrieval_markdown(report))
        print(f"Executed {len(run.cases)} local vector searches; gate: {'PASS' if report.gate_passed else 'FAIL'}. "
              "Temporary tables rolled back. No provider calls or telemetry writes.")
        return 0 if report.gate_passed else 1
    except (GoldenDatasetError, RetrievalEvaluationError) as error:
        print(f"Vector baseline error: {error}", file=sys.stderr)
    except Exception:
        # Provider/database/validation errors can contain secrets or corpus text.
        print("Vector baseline failed; no raw provider, database, or input details are displayed.", file=sys.stderr)
    return 2


def main():
    raise SystemExit(run_cli(build_parser().parse_args()))


if __name__ == "__main__":
    main()
