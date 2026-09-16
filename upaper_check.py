"""루트 진입점: python upaper_check.py 책.epub"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from upaper_check.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
