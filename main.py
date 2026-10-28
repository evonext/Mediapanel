import sys


def main():
    if "--selftest" in sys.argv:
        from mpanel.selftest import run as selftest
        sys.exit(selftest())
    from mpanel.app import run
    run(demo="--demo" in sys.argv)


if __name__ == "__main__":
    main()
