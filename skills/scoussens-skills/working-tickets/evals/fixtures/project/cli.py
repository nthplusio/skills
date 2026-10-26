import sys


def main(args):
    if args == ["--help"]:
        print("Usage: cli.py [--help]")
        return 0
    if args:
        print("Unknown flag", file=sys.stderr)
        return 0
    print("ready")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
