"""Collect public GitHub Actions evidence for LK08 runs into Documentation/LK08/actions/.

Usage: python scripts/collect_lk08_actions_evidence.py LABEL=RUN_ID [LABEL=RUN_ID ...]
"""
from datetime import datetime
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "Documentation/LK08/actions"
REPO = "ghazthiskc19/MLOps-AnomaliCuacaOpenMeteo"
API = f"https://api.github.com/repos/{REPO}"


def get(url, raw=False):
    request = urllib.request.Request(url, headers={"User-Agent": "lk08-evidence", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    return data.decode("utf-8", "replace") if raw else json.loads(data)


def seconds(start, end):
    if not start or not end:
        return None
    parse = lambda v: datetime.fromisoformat(v.replace("Z", "+00:00"))
    return round((parse(end) - parse(start)).total_seconds())


def collect(label, run_id):
    run = get(f"{API}/actions/runs/{run_id}")
    jobs = get(f"{API}/actions/runs/{run_id}/jobs")["jobs"]
    commit = get(f"{API}/commits/{run['head_sha']}")
    record = {
        "label": label, "run_id": run_id, "url": run["html_url"], "event": run["event"],
        "branch": run["head_branch"], "head_sha": run["head_sha"], "run_number": run["run_number"],
        "commit_message": commit["commit"]["message"].split("\n")[0],
        "files_changed": [f["filename"] for f in commit.get("files", [])][:20],
        "created_at": run["created_at"], "updated_at": run["updated_at"],
        "status": run["status"], "conclusion": run["conclusion"], "jobs": [],
    }
    for job in jobs:
        record["jobs"].append({
            "name": job["name"], "conclusion": job["conclusion"], "url": job["html_url"],
            "duration_s": seconds(job["started_at"], job["completed_at"]),
            "steps": [{"number": s["number"], "name": s["name"], "conclusion": s["conclusion"],
                       "duration_s": seconds(s["started_at"], s["completed_at"])} for s in job["steps"]],
        })
        try:
            log = get(f"{API}/actions/jobs/{job['id']}/logs", raw=True)
            (OUT / f"{label}-job.log").write_text(log, encoding="utf-8")
            record["log_saved"] = True
        except Exception as error:  # logs may require authentication
            record["log_saved"] = f"unavailable: {error}"
    return record


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "evidence.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for pair in sys.argv[1:]:
        label, run_id = pair.split("=", 1)
        existing[label] = collect(label, run_id)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for label, rec in existing.items():
        print(label, rec["conclusion"], rec["url"])
