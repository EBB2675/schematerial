"""Emit an inline fixture supplied on stdin, using only the standard library.

Adapter tests provide their own small fixture document. This script exercises
the same process and JSON boundary as a real source reader.
"""

import json
import sys

if __name__ == "__main__":
    print(json.dumps(json.load(sys.stdin), allow_nan=False))
