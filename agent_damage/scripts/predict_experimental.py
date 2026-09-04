#!/usr/bin/env python3
"""Predict Dk and threshold damage grade for one FDS/case condition."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.src.inference.split_model_predictor import (  # noqa: E402
    load_split_model_predictor,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fds", type=Path)
    parser.add_argument("case_name")
    parser.add_argument("--model-dir", type=Path, default=None)
    args = parser.parse_args()

    predictor = load_split_model_predictor(args.model_dir)
    result = predictor.predict(args.fds, args.case_name)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

