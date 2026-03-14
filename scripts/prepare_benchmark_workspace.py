#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def copy_file_if_exists(source: Path, dest: Path) -> None:
    if source.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)


def descriptive_eval_dirs(iteration_dir: Path) -> List[Path]:
    result: List[Path] = []
    for child in sorted(iteration_dir.iterdir()):
        if child.is_dir() and (child / "eval_metadata.json").exists():
            result.append(child)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare aggregate-compatible benchmark layout"
    )
    parser.add_argument("iteration_dir", help="Path to an iteration directory")
    args = parser.parse_args()

    iteration_dir = Path(args.iteration_dir).resolve()
    runs_root = iteration_dir / "runs"
    if runs_root.exists():
        shutil.rmtree(runs_root)
    runs_root.mkdir(parents=True, exist_ok=True)

    for eval_dir in descriptive_eval_dirs(iteration_dir):
        metadata = load_json(eval_dir / "eval_metadata.json")
        eval_id = metadata["eval_id"]
        target_eval_dir = runs_root / f"eval-{eval_id}"
        target_eval_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            eval_dir / "eval_metadata.json", target_eval_dir / "eval_metadata.json"
        )

        for source_config_name, target_config_name in [
            ("with_skill", "with_skill"),
            ("old_skill", "without_skill"),
        ]:
            source_run_dir = eval_dir / source_config_name
            if not source_run_dir.exists():
                continue
            target_run_dir = target_eval_dir / target_config_name / "run-1"
            outputs_target = target_run_dir / "outputs"
            outputs_target.mkdir(parents=True, exist_ok=True)

            outputs_source = source_run_dir / "outputs"
            if outputs_source.exists():
                for output_file in outputs_source.iterdir():
                    if output_file.is_file():
                        shutil.copy2(output_file, outputs_target / output_file.name)

            copy_file_if_exists(
                source_run_dir / "timing.json", target_run_dir / "timing.json"
            )
            copy_file_if_exists(
                source_run_dir / "grading.json", target_run_dir / "grading.json"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
