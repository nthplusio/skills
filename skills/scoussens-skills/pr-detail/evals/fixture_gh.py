#!/usr/bin/env python3
"""Read-only gh boundary fixture. Never falls through to a real forge."""

import json
import os
import subprocess
import sys
import time

args = sys.argv[1:]
fixture = json.loads(open(os.environ["FORGE_FIXTURE"]).read())


def flag(name):
    return args[args.index(name) + 1]


if args == ["auth", "status"]:
    sys.exit(0)
if args[:2] == ["pr", "view"]:
    assert flag("--repo") == fixture["repo"]
    assert args[2] == str(fixture["pr"]["number"])
    key, pages = "pr", [fixture["pr"]]
elif args[:2] == ["api", "graphql"]:
    query = next(arg[6:] for arg in args if arg.startswith("query="))
    if "node(id:" in query:
        key = "thread-comments:" + next(arg[3:] for arg in args if arg.startswith("id="))
    else:
        owner, repo = fixture["repo"].split("/")
        assert f"o={owner}" in args and f"r={repo}" in args
        assert f'n={fixture["pr"]["number"]}' in args
        key = "threads" if "reviewThreads(" in query else "counts"
    pages = fixture[key]
    if "--paginate" in args:
        assert "$endCursor:String" in query and "after:$endCursor" in query
        assert query.count("pageInfo{") == 1, "each pagination call owns one cursor"
elif args[:1] == ["api"]:
    prefix = f'repos/{fixture["repo"]}/'
    assert args[1].startswith(prefix), "wrong target repository"
    endpoint = args[1][len(prefix):].split("?")[0]
    if endpoint.endswith("/reviews"):
        key = "reviews"
    elif endpoint.endswith("/timeline"):
        key = "timeline"
    elif endpoint.endswith("/check-runs"):
        key = "check-runs:" + endpoint.split("/")[1]
    else:
        raise AssertionError(f"unexpected endpoint: {endpoint}")
    pages = fixture[key]
else:
    raise AssertionError(f"unsupported or mutating command: {args}")

time.sleep(0.01)
if key in fixture.get("fail", []):
    print(json.dumps(pages[0]))
    print(f"fixture fetch failure: {key}", file=sys.stderr)
    sys.exit(37)
if "--paginate" not in args:
    pages = pages[:1]
if "--slurp" in args:
    pages = [pages]
for page in pages:
    if "--jq" in args:
        subprocess.run(["jq", flag("--jq")], input=json.dumps(page), text=True, check=True)
    else:
        print(json.dumps(page))
