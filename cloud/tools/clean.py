#! /usr/bin/env python

import sys
from pathlib import Path

sys.path += [str(Path(__file__).parent.parent / "crawl-url-function")]
from htmlutil import clean_content

content = sys.stdin.buffer.read()
sys.stdout.buffer.write(clean_content(content))
