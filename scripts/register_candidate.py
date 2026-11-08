"""Register a candidate in Staging after re-evaluation; no Production changes."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.automation import register_candidate

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(register_candidate(args.candidate_dir),indent=2))
