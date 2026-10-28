"""Non-regression harness for the transform step of the ETL.

Workflow:
    1. freeze   -> copy the current transform inputs (HTML cache + extract Parquet
                   files) into a frozen, read-only-by-convention directory.
    2. baseline -> run the transform on the frozen inputs with the reference code
                   and store its outputs as the baseline.
    3. pytest   -> run the transform on the same frozen inputs with the modified
                   code and compare its outputs to the baseline.

Usage (from the repository root):
    python tests/regression/transform_regression.py freeze
    python tests/regression/transform_regression.py baseline
    pytest -m regression -v

The transform always runs in a temporary working copy of the frozen inputs, so
neither the frozen inputs nor the real cache are ever modified.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CACHE_DIR = Path.home() / ".access-it" / "cache"
DEFAULT_REGRESSION_DIR = Path.home() / ".access-it" / "regression"

CACHE_DIR = Path(os.getenv("ACCESS_IT_CACHE") or DEFAULT_CACHE_DIR)
REGRESSION_DIR = Path(os.getenv("ACCESS_IT_REGRESSION_DIR") or DEFAULT_REGRESSION_DIR)
FROZEN_INPUTS_DIR = REGRESSION_DIR / "inputs"
BASELINE_DIR = REGRESSION_DIR / "baseline"

# Raw cache directories read by the transform step
RAW_DIRS = ["results", "results_national", "startlists"]

# Parquet files produced by the extract step and read by the transform step.
# Note: clubs.parquet is both read and overwritten by the transform step.
INPUT_FILES = [
    "departements.parquet",
    "departemental_committees.parquet",
    "regional_committees.parquet",
    "clubs.parquet",
]

# Tables written by the transform step, mapped to the columns used to sort them
# before comparison (rows are compared regardless of their original order)
OUTPUT_TABLES = {
    "clubs": ["club_id"],
    "races": ["race_id"],
    "riders": ["rider_id"],
    "rankings": ["race_id", "rider_id", "finish_rank"],
    "affiliations": ["rider_id", "start_date"],
    "rider_categories": ["rider_id", "start_date"],
}

MAX_LOG_LINES = 40
MAX_DIFF_ROWS = 10


# --------------------------------------------------------------------------- #
# Freezing the inputs
# --------------------------------------------------------------------------- #

def _link_or_copy(src: str, dst: str) -> str:
    """Hard-link HTML files (saves disk space), copy everything else.

    HTML files are safe to hard-link: the extract step replaces them atomically
    (write to a temporary file, then rename), so it never modifies the shared
    inode in place.
    """
    if src.endswith(".html"):
        try:
            os.link(src, dst)
            return dst
        except OSError:  # e.g. different file systems
            pass
    return shutil.copy2(src, dst)


def freeze_inputs(cache_dir: Path, frozen_dir: Path, overwrite: bool = False) -> None:
    """Copy the transform inputs from the cache into the frozen directory."""
    if frozen_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"Frozen inputs already exist in {frozen_dir} (use --overwrite)."
            )
        shutil.rmtree(frozen_dir)

    missing = [cache_dir / name for name in RAW_DIRS if not (cache_dir / name).is_dir()]
    missing += [cache_dir / "data" / f for f in INPUT_FILES if not (cache_dir / "data" / f).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing transform inputs: {[str(p) for p in missing]}")

    for name in RAW_DIRS:
        shutil.copytree(cache_dir / name, frozen_dir / name, copy_function=_link_or_copy)
    (frozen_dir / "data").mkdir(parents=True)
    for file_name in INPUT_FILES:
        shutil.copy2(cache_dir / "data" / file_name, frozen_dir / "data" / file_name)


# --------------------------------------------------------------------------- #
# Running the transform
# --------------------------------------------------------------------------- #

def _tail(text: str, n: int = MAX_LOG_LINES) -> str:
    return "\n".join(text.splitlines()[-n:])


def run_transform(frozen_dir: Path, output_dir: Path, repo_root: Path = REPO_ROOT) -> None:
    """Run scripts/transform.py of `repo_root` on a working copy of the frozen inputs.

    The code under test is always taken from `repo_root/src`, whatever the
    installed version of the package. The output tables are copied to `output_dir`.
    """
    if not frozen_dir.is_dir():
        raise FileNotFoundError(f"Frozen inputs not found in {frozen_dir} (run 'freeze' first).")
    transform_script = repo_root / "scripts" / "transform.py"
    if not transform_script.is_file():
        raise FileNotFoundError(f"Transform script not found: {transform_script}")

    with tempfile.TemporaryDirectory(prefix="access-it-regression-") as tmp:
        work_dir = Path(tmp)
        # Raw HTML is only read by the transform: symbolic links are enough
        for name in RAW_DIRS:
            (work_dir / name).symlink_to((frozen_dir / name).resolve(), target_is_directory=True)
        # Parquet files are overwritten by the transform: real copies are needed
        shutil.copytree(frozen_dir / "data", work_dir / "data")

        python_path = os.pathsep.join(
            p for p in [str(repo_root / "src"), os.environ.get("PYTHONPATH", "")] if p
        )
        env = os.environ | {"ACCESS_IT_CACHE": str(work_dir), "PYTHONPATH": python_path}
        result = subprocess.run(
            [sys.executable, str(transform_script)],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Transform failed (exit code {result.returncode}).\n"
                f"--- stdout (tail) ---\n{_tail(result.stdout)}\n"
                f"--- stderr (tail) ---\n{_tail(result.stderr)}"
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        for table in OUTPUT_TABLES:
            shutil.copy2(work_dir / "data" / f"{table}.parquet", output_dir / f"{table}.parquet")


def create_baseline(
        frozen_dir: Path,
        baseline_dir: Path,
        repo_root: Path = REPO_ROOT,
        overwrite: bool = False
    ) -> None:
    """Run the transform with the reference code and store its outputs as the baseline."""
    if baseline_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Baseline already exists in {baseline_dir} (use --overwrite).")
        shutil.rmtree(baseline_dir)
    run_transform(frozen_dir, baseline_dir, repo_root=repo_root)


# --------------------------------------------------------------------------- #
# Comparing the outputs
# --------------------------------------------------------------------------- #

def normalize_table(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Sort columns by name and rows by keys then all other columns."""
    df = df[sorted(df.columns)]
    sort_columns = keys + [c for c in df.columns if c not in keys]
    return (
        df.sort_values(by=sort_columns, key=lambda s: s.astype(str), kind="stable")
        .reset_index(drop=True)
    )


def describe_row_differences(
        expected: pd.DataFrame,
        actual: pd.DataFrame,
        max_rows: int = MAX_DIFF_ROWS
    ) -> str:
    """Summarize rows present in only one of the two tables (values compared as strings)."""
    merged = expected.astype(str).merge(actual.astype(str), how="outer", indicator=True)
    only_expected = merged[merged["_merge"] == "left_only"].drop(columns="_merge")
    only_actual = merged[merged["_merge"] == "right_only"].drop(columns="_merge")
    lines = [
        f"rows: baseline={len(expected)}, current={len(actual)}, "
        f"only in baseline={len(only_expected)}, only in current={len(only_actual)}"
    ]
    if len(only_expected) > 0:
        lines.append(f"first rows only in baseline:\n{only_expected.head(max_rows).to_string()}")
    if len(only_actual) > 0:
        lines.append(f"first rows only in current:\n{only_actual.head(max_rows).to_string()}")
    if len(only_expected) == 0 and len(only_actual) == 0:
        lines.append("same rows as strings: the difference is in dtypes or float precision")
    return "\n".join(lines)


def compare_outputs(baseline_dir: Path, current_dir: Path) -> list[str]:
    """Compare every output table; return one failure message per differing table."""
    failures = []
    for table, keys in OUTPUT_TABLES.items():
        expected = pd.read_parquet(baseline_dir / f"{table}.parquet")
        actual = pd.read_parquet(current_dir / f"{table}.parquet")

        if set(expected.columns) != set(actual.columns):
            failures.append(
                f"[{table}] different columns: "
                f"missing={sorted(set(expected.columns) - set(actual.columns))}, "
                f"unexpected={sorted(set(actual.columns) - set(expected.columns))}"
            )
            continue

        expected = normalize_table(expected, keys)
        actual = normalize_table(actual, keys)
        try:
            pd.testing.assert_frame_equal(actual, expected, check_dtype=True)
        except AssertionError as error:
            failures.append(f"[{table}] {error}\n{describe_row_differences(expected, actual)}")
    return failures


# --------------------------------------------------------------------------- #
# Command-line interface
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Non-regression harness for the transform step.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    freeze_parser = subparsers.add_parser("freeze", help="Freeze the current transform inputs.")
    freeze_parser.add_argument("--overwrite", action="store_true")

    baseline_parser = subparsers.add_parser("baseline", help="Create the baseline outputs.")
    baseline_parser.add_argument("--overwrite", action="store_true")
    baseline_parser.add_argument(
        "--repo",
        type=Path,
        default=REPO_ROOT,
        help="Checkout holding the reference code (default: this repository).",
    )

    compare_parser = subparsers.add_parser(
        "compare", help="Run the transform and compare its outputs to the baseline."
    )
    compare_parser.add_argument("--repo", type=Path, default=REPO_ROOT)

    args = parser.parse_args()

    if args.command == "freeze":
        freeze_inputs(CACHE_DIR, FROZEN_INPUTS_DIR, overwrite=args.overwrite)
        print(f"Inputs frozen in {FROZEN_INPUTS_DIR}")
    elif args.command == "baseline":
        create_baseline(
            FROZEN_INPUTS_DIR, BASELINE_DIR, repo_root=args.repo.resolve(), overwrite=args.overwrite
        )
        print(f"Baseline created in {BASELINE_DIR}")
    elif args.command == "compare":
        with tempfile.TemporaryDirectory(prefix="access-it-current-") as tmp:
            run_transform(FROZEN_INPUTS_DIR, Path(tmp), repo_root=args.repo.resolve())
            failures = compare_outputs(BASELINE_DIR, Path(tmp))
        if failures:
            print("\n\n".join(failures))
            sys.exit(1)
        print("All output tables match the baseline.")


if __name__ == "__main__":
    main()
