import base64
import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import config
import main
import pytest
from cloudevents.http import CloudEvent
from google.cloud import pubsub_v1

main.crawl_delay = timedelta(seconds=0)


@pytest.fixture(autouse=True)
def reset_crawled_urls():
    main.crawled_urls.clear()


def test_crawl_url(
    firestore_db, requests_mock, pull_from_crawl, pull_from_changed_pages
):
    TEST_LINK_TARGET = "https://www.portland.gov/transportation/page3"
    PAGE_CONTENT = f'<a href="{TEST_LINK_TARGET}">Link</a>'.encode()
    PAGE_MARKDOWN = f"[Link]({TEST_LINK_TARGET})\n\n".encode()
    requests_mock.get(
        firestore_db.TEST_PAGE1,
        request_headers={"if-none-match": firestore_db.THE_ETAG},
        headers={"etag": firestore_db.THE_ETAG + " next", "content-type": "text/html"},
        content=PAGE_CONTENT,
    )
    requests_mock.get(
        "https://web.archive.org/save/https://www.portland.gov/transportation",
        status_code=200,
    )

    event = CloudEvent(
        {"type": "", "source": ""},
        {
            "message": {
                "data": base64.b64encode(
                    json.dumps(
                        {
                            "prev_crawl": "2022-09-26",
                            "crawl": "2022-09-27",
                            "url": firestore_db.TEST_PAGE1,
                        }
                    ).encode()
                )
            }
        },
    )
    main.do_crawl_url(event)

    assert [
        doc.path for doc in firestore_db.collection("crawl-2022-09-27").list_documents()
    ] == [
        firestore_db.collection("crawl-2022-09-27")
        .document(sha256(firestore_db.TEST_PAGE1.encode()).hexdigest())
        .path,
    ]
    assert firestore_db.collection("crawl-2022-09-27").document(
        sha256(firestore_db.TEST_PAGE1.encode()).hexdigest()
    ).get().to_dict() == {
        "url": firestore_db.TEST_PAGE1,
        "status_code": 200,
        "headers": {
            "etag": firestore_db.THE_ETAG + " next",
            "content-type": "text/html",
        },
        "content": firestore_db.collection("content").document(
            sha256(PAGE_CONTENT).hexdigest()
        ),
        "text_content": firestore_db.collection("text_content").document(
            sha256(PAGE_MARKDOWN).hexdigest()
        ),
    }

    assert json.loads(pull_from_crawl().message.data) == {
        "prev_crawl": "2022-09-26",
        "crawl": "2022-09-27",
        "url": TEST_LINK_TARGET,
    }

    assert json.loads(pull_from_changed_pages().message.data) == {
        "crawl": "2022-09-27",
        "page": firestore_db.TEST_PAGE1,
        "change": "CHANGE",
        "diff": """--- https://www.portland.gov/transportation\t2022-09-26
+++ https://www.portland.gov/transportation\t2022-09-27
@@ -1 +1,2 @@
-This is some text
+[Link](https://www.portland.gov/transportation/page3)
+
"""
    }


def test_get_crawl(firestore_db):
    curr_crawl, prev_crawl = main.get_crawl(
        {"url": "https://www.portland.gov/transportation"}
    )
    assert prev_crawl == "2022-09-26"
    assert curr_crawl == datetime.now(tz=timezone.utc).date().isoformat()


def test_added_page(firestore_db, requests_mock, pull_from_changed_pages):
    PAGE_URL = "https://www.portland.gov/transportation/new_page"
    requests_mock.get(
        PAGE_URL,
        headers={"etag": "an-etag", "content-type": "text/html"},
        content="I am a page".encode(),
    )
    requests_mock.get("https://web.archive.org/save/" + PAGE_URL, status_code=200)

    event = CloudEvent(
        {"type": "", "source": ""},
        {
            "message": {
                "data": base64.b64encode(
                    json.dumps(
                        {
                            "prev_crawl": "2022-09-26",
                            "crawl": "2022-09-27",
                            "url": PAGE_URL,
                        }
                    ).encode()
                )
            }
        },
    )
    main.do_crawl_url(event)

    assert json.loads(pull_from_changed_pages().message.data) == {
        "crawl": "2022-09-27",
        "page": PAGE_URL,
        "change": "ADD",
        "diff": "",
    }


def test_removed_page(firestore_db, requests_mock, pull_from_changed_pages):
    requests_mock.get(
        firestore_db.TEST_PAGE1,
        request_headers={"if-none-match": firestore_db.THE_ETAG},
        status_code=404,
    )
    requests_mock.get(
        "https://web.archive.org/save/" + firestore_db.TEST_PAGE1, status_code=200
    )

    event = CloudEvent(
        {"type": "", "source": ""},
        {
            "message": {
                "data": base64.b64encode(
                    json.dumps(
                        {
                            "prev_crawl": "2022-09-26",
                            "crawl": "2022-09-27",
                            "url": firestore_db.TEST_PAGE1,
                        }
                    ).encode()
                )
            }
        },
    )
    main.do_crawl_url(event)

    assert json.loads(pull_from_changed_pages().message.data) == {
        "crawl": "2022-09-27",
        "page": firestore_db.TEST_PAGE1,
        "change": "DEL",
        "diff": "",
    }


def test_unchanged_page(firestore_db, requests_mock, pull_from_changed_pages):
    requests_mock.get(
        firestore_db.TEST_PAGE1,
        request_headers={"if-none-match": firestore_db.THE_ETAG},
        status_code=304,
    )

    event = CloudEvent(
        {"type": "", "source": ""},
        {
            "message": {
                "data": base64.b64encode(
                    json.dumps(
                        {
                            "prev_crawl": "2022-09-26",
                            "crawl": "2022-09-27",
                            "url": firestore_db.TEST_PAGE1,
                        }
                    ).encode()
                )
            }
        },
    )
    main.do_crawl_url(event)

    # Publish a message to the changed-pages topic. If we get the new one back,
    # it means do_crawl_url() didn't publish anything.
    publisher = pubsub_v1.PublisherClient()
    changed_pages_topic_path = publisher.topic_path(
        config.CLOUD_PROJECT, "changed-pages"
    )

    test_pub = {
        "crawl": "2022-09-30",
        "page": "The fake publication",
        "change": "ADD",
        "diff": "",
    }
    publisher.publish(changed_pages_topic_path, json.dumps(test_pub).encode())

    assert json.loads(pull_from_changed_pages().message.data) == test_pub
