#! /usr/bin/env python3

import argparse
import asyncio
from datetime import date
from hashlib import sha256
from typing import List

import html2text
from google.cloud import firestore

parser = argparse.ArgumentParser(
    description="Set all the text contents for a crawl that only has full HTML."
)
parser.add_argument(
    "crawl_date", type=date.fromisoformat, help="Date of the crawl to download from"
)

args = parser.parse_args()

db = firestore.AsyncClient()

total_docs = 0
finished_docs = 0


async def update_all_text(crawl_date: date) -> None:
    global total_docs
    all_docs: List[asyncio.Task] = []
    async for ref in db.collection(f"crawl-{crawl_date.isoformat()}").list_documents():
        total_docs += 1
        all_docs.append(asyncio.create_task(update_text_for_ref(ref)))  # type: ignore
    try:
        await asyncio.gather(*all_docs)
    except Exception:
        for doc_task in all_docs:
            doc_task.cancel()
        raise


async def update_text_for_ref(ref: firestore.AsyncDocumentReference) -> None:
    global total_docs, finished_docs
    try:
        doc: firestore.DocumentSnapshot = await ref.get()  # type: ignore
        url = doc.get("url")
        content_ref: firestore.DocumentReference = doc.get("content")
        if content_ref is None:
            return
        content: firestore.DocumentSnapshot = await db.document(content_ref.path).get()  # type: ignore
        markdown = html2text.html2text(content.get("content"), baseurl=url)
        text_ref = db.collection("text_content").document(
            sha256(markdown.encode()).hexdigest()
        )
        await asyncio.gather(
            text_ref.set({"text": markdown}), ref.update({"text_content": text_ref})
        )
    finally:
        finished_docs += 1
    print(f"[{finished_docs}/{total_docs}] Updated {url}")


asyncio.run(update_all_text(args.crawl_date), debug=True)
