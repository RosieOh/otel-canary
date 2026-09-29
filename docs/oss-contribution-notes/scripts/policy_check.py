"""For candidate repos: why do outsider PRs get closed, and does CONTRIBUTING gate PRs on issue assignment / AI use?"""
import base64
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import pr_speed as ps

REPOS = sys.argv[1:]
KEYWORDS = re.compile(r"(assign\w*|AI[- ]generated|AI[- ]assisted|\bLLM\b|generative AI|issue first|approved issue|"
                      r"open an issue|discuss\w* (?:first|before)|help wanted|good first issue|CLA\b|DCO\b)", re.I)


def closed_reasons(repo):
    prs = [p for p in ps.fetch(f"repo:{repo} is:pr is:closed is:unmerged", "closed", ps.date(2026, 9, 13), ps.date(2026, 9, 27))
           if not ps.is_bot(p) and p["authorAssociation"] not in ps.MAINTAINER and p["isCrossRepository"]][:8]
    out = []
    for p in prs:
        comments = ps.http(f"https://api.github.com/repos/{repo}/issues/{p['number']}/comments?per_page=100")
        others = [c for c in comments if c["user"]["login"] != p["author"]["login"]]
        last = others[-1] if others else None
        out.append(f"  #{p['number']}: " + (f"{last['user']['login']}: {re.sub(r'\s+', ' ', last['body'])[:170]}"
                                             if last else "(closed with no comment)"))
    return out


def contributing(repo):
    for path in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md", "CONTRIBUTING.rst"):
        try:
            f = ps.http(f"https://api.github.com/repos/{repo}/contents/{path}")
        except Exception:
            continue
        text = base64.b64decode(f["content"]).decode("utf-8", "replace")
        hits = []
        for line in text.splitlines():
            if KEYWORDS.search(line) and len(hits) < 8:
                hits.append("  > " + re.sub(r"\s+", " ", line.strip())[:200])
        return [f"  [{path}]"] + hits
    return ["  (no CONTRIBUTING file found)"]


def run(repo):
    return "\n".join([f"=== {repo}", " closed outsider PRs (last non-author comment):"] + closed_reasons(repo)
                     + [" contributing keywords:"] + contributing(repo))


if __name__ == "__main__":
    ps.SEARCH = ps.SEARCH.replace("authorAssociation", "isCrossRepository authorAssociation")
    with ThreadPoolExecutor(max_workers=4) as ex:
        for block in ex.map(run, REPOS):
            print(block, flush=True)
