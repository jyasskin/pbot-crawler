#! /usr/bin/env python3

import argparse
import sys
from datetime import date
from hashlib import sha256
from typing import Union

import google.cloud.firestore_v1.base_query
from google.cloud import firestore

parser = argparse.ArgumentParser(description="Download a file from the crawl.")
parser.add_argument(
    "crawl_date", type=date.fromisoformat, help="Date of the crawl to download from"
)
parser.add_argument("url", type=str, help="Crawled URL to download")
parser.add_argument(
    "--raw", help="Download the raw HTML instead of the markdown version"
)
parser.add_argument(
    "-o",
    type=argparse.FileType(mode="w"),
    default="-",
    help="where to save the content",
)

args = parser.parse_args()

db = firestore.Client()
crawl_info: firestore.DocumentSnapshot = (
    db.collection(f"crawl-{args.crawl_date.isoformat()}")
    .document(sha256(args.url.encode()).hexdigest())
    .get()
)

if not crawl_info.exists:
    sys.exit(f"Can't find {args.url} in the crawl")

if args.raw:
    content_ref: firestore.DocumentReference = crawl_info.get("content")
    if content_ref is None:
        sys.exit(f"{args.url} didn't return content")
    content_snapshot = content_ref.get()
    if not content_snapshot.exists:
        sys.exit(f"Didn't save content for {args.url}")
    content: str = content_snapshot.get("content")
    args.o.write(content)
else:
    text_content_ref: firestore.DocumentReference = crawl_info.get("text_content")
    if text_content_ref is None:
        sys.exit(f"{args.url} didn't return text content")
    text_content_snapshot = text_content_ref.get()
    if not text_content_snapshot.exists:
        sys.exit(f"Didn't save text content for {args.url}")
    text_content: str = text_content_snapshot.get("text")
    args.o.write(text_content)
