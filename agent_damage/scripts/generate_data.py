#!/usr/bin/env python3
"""CLI: generate train/val/test CSV datasets via rejection sampling."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.src.data.generator import generate_splits, write_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate balanced damage dataset")
    parser.add_argument("--n_train", type=int, default=5000)
    parser.add_argument("--n_val", type=int, default=1000)
    parser.add_argument("--n_test", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
    )
    args = parser.parse_args()

    print(f"[generate_data] sizes: train={args.n_train}, val={args.n_val}, test={args.n_test}")
    train_df, val_df, test_df = generate_splits(
        n_train=args.n_train, n_val=args.n_val, n_test=args.n_test, seed=args.seed
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(train_df, args.output_dir / "train.csv")
    write_csv(val_df, args.output_dir / "val.csv")
    write_csv(test_df, args.output_dir / "test.csv")

    for name, df in (("train", train_df), ("val", val_df), ("test", test_df)):
        counts = df["label"].value_counts().sort_index().to_dict()
        print(f"[generate_data] {name}: {len(df)} rows  label counts={counts}")

    print(f"[generate_data] Saved CSVs to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
