"""Transport-only CLI copied into disposable evaluation repositories."""

import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description="Project issue tracker and acceptance checks")
    parser.add_argument("operation", choices=["identity", "workflow", "list", "get", "comments", "update", "comment", "create", "check"])
    parser.add_argument("id", nargs="?")
    parser.add_argument("--parent")
    parser.add_argument("--cursor", type=int, default=0)
    parser.add_argument("--ready", action="store_true")
    parser.add_argument("--revision", type=int)
    parser.add_argument("--json", help="JSON object, or @path to a JSON file")
    parser.add_argument("--body")
    args = vars(parser.parse_args())
    payload = args.pop("json")
    if payload:
        args["patch"] = json.loads(Path(payload[1:]).read_text() if payload.startswith("@") else payload)
    config = json.loads((Path(__file__).resolve().parents[1] / ".tracker.json").read_text())
    request = Request(config["url"], json.dumps(args).encode(), {"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as error:
        print(error.read().decode(), file=sys.stderr)
        return 1
    except URLError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
