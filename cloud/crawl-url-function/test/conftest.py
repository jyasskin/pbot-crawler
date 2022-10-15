from hashlib import sha256

import config
import google.pubsub_v1.types
import pytest
from google.api_core import retry
from google.cloud import firestore, pubsub_v1

TEST_PAGE1 = "https://www.portland.gov/transportation"
TEST_PAGE2 = "https://www.portland.gov/transportation/has-text-content"
THE_ETAG = "This is an ETag"


@pytest.fixture
def firestore_db():
    db = firestore.Client()
    try:
        url = TEST_PAGE1
        db.collection("crawl-2022-09-26").document(
            sha256(url.encode()).hexdigest()
        ).set(
            {
                "url": url,
                "status_code": 200,
                "headers": {
                    "content-type": "text/html",
                    "etag": THE_ETAG,
                },
                "content": db.collection("objects").document("1"),
                "text_content": db.collection("text-content").document("2"),
            }
        )
        db.collection("objects").document("1").set(
            {
                "links": [
                    "https://www.portland.gov/transportation/page1",
                    "https://www.portland.gov/transportation/page2",
                ],
            }
        )
        db.collection("crawl-2022-09-26").document(
            sha256(TEST_PAGE2.encode()).hexdigest()
        ).set(
            {
                "url": TEST_PAGE2,
                "status_code": 200,
                "headers": {
                    "content-type": "text/html",
                    "etag": THE_ETAG,
                },
                "content": db.collection("objects").document("3"),
                "text_content": db.collection("text-content").document("2"),
            }
        )
        db.collection("text-content").document("2").set(
            {
                "text": "This is some text\n",
            }
        )
        db.TEST_PAGE1 = TEST_PAGE1
        db.TEST_PAGE2 = TEST_PAGE2
        db.THE_ETAG = THE_ETAG
        yield db
    finally:
        for collection in db.collections():
            for doc in collection.list_documents():
                doc.delete()


def pull_from_topic(topic: str):
    subscriber = pubsub_v1.SubscriberClient()
    topic_path = subscriber.topic_path(config.CLOUD_PROJECT, topic)

    # Wrap the subscriber in a 'with' block to automatically call close() to
    # close the underlying gRPC channel when done.
    with subscriber:
        subscription = subscriber.create_subscription(request={"topic": topic_path})

        def pull_one() -> google.pubsub_v1.types.ReceivedMessage:
            response = subscriber.pull(
                request={"subscription": subscription.name, "max_messages": 1},
                timeout=10,
            )
            return response.received_messages[0]

        yield pull_one


@pytest.fixture
def pull_from_crawl():
    yield from pull_from_topic("crawl")


@pytest.fixture
def pull_from_changed_pages():
    yield from pull_from_topic("changed-pages")
