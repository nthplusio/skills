import json
import sys


def can_cancel(status):
    return status in ("new", "packing")


if __name__ == "__main__":
    print(json.dumps({"allowed": can_cancel(sys.argv[1])}))
