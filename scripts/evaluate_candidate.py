"""Recompute candidate evidence and exit nonzero when validation blocks promotion."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.automation import evaluate_candidate

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir",type=Path,required=True)
    args=parser.parse_args()
    result=evaluate_candidate(args.candidate_dir)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
