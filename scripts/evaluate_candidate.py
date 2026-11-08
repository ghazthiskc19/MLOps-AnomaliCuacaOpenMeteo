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
    if __import__("os").environ.get("GITHUB_ACTIONS"):
        m=result["combined"]["metrics"]
        level="notice" if result["passed"] else "error"
        print(f"::{level} title=Quality gate {result['status']}::combined macro F1={m['f1_macro']:.4f} (threshold > 0.85), "
              f"support={int(m['support_class_0'])}/{int(m['support_class_1'])}/{int(m['support_class_2'])}, "
              f"fault recall={m['recall_class_1']:.4f}, false alarm={result['combined']['false_alarm_rate']:.4f}, "
              f"scenario kinds passed={sum(g['passed'] for g in result['scenarios'].values())}/{len(result['scenarios'])}")
    raise SystemExit(0 if result['passed'] else 1)
