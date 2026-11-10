#!/usr/bin/env python3
"""The package names no origin project: no tracked file contains a forbidden word.

Words are stored as sha256 of the lowercase token, so this file does not name them either.
Add a word: python3 -c "import hashlib; print(hashlib.sha256(b'word').hexdigest())"
"""

import hashlib
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {
    "3b39145912f6ec60ac6285c26aa77fb89cf2b6c5d15229f7c4e15a3079bb4088",
    "5c83eae2d2c8633627c03e436d234f0d81517bc4baff8515c3ff6ccc6316d7c8",
}
TOKEN = re.compile(rb"[a-z0-9]+")


class NoOriginIdentityTest(unittest.TestCase):
    def test_no_tracked_file_or_path_names_the_origin(self):
        files = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"]).split(b"\0")
        hits = []
        for name in filter(None, files):
            path = ROOT / name.decode()
            blobs = [name] if path.is_symlink() or not path.is_file() else [name, path.read_bytes()]
            for blob in blobs:
                words = set(TOKEN.findall(blob.lower()))
                if any(hashlib.sha256(w).hexdigest() in FORBIDDEN for w in words):
                    hits.append(name.decode())
                    break
        self.assertEqual([], hits)


if __name__ == "__main__":
    unittest.main()
