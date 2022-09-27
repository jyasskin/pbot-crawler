from hashlib import sha256

import cache
import pytest
from google.cloud import firestore

TEST_PAGE1 = 'https://www.portland.gov/transportation'


@pytest.fixture
def firestore_db():
    db = firestore.Client()
    url = TEST_PAGE1
    db.collection('crawl-2022-09-26').document(sha256(url.encode()).hexdigest()).set({
        'url': url,
        'status_code': 200,
        'headers': {
            'content-type': 'text/html',
        },
        'content': db.collection('objects').document('1'),
    })
    db.collection('objects').document('1').set({
        'links': [
            'https://www.portland.gov/transportation/page1',
            'https://www.portland.gov/transportation/page2',
        ],
    })
    yield db
    for collection in db.collections():
        for doc in collection.list_documents():
            doc.delete()


def test_cached_response_fresh(firestore_db):
    response = cache.CachedResponse(
        firestore_db, TEST_PAGE1, prev_crawl='2022-09-25', curr_crawl='2022-09-26')
    assert response.state == cache.CacheState.FRESH
    # Nothing else is loaded for fresh responses.
    assert response.status_code == 0


def test_cached_response_stale(firestore_db):
    response = cache.CachedResponse(
        firestore_db, TEST_PAGE1, prev_crawl='2022-09-26', curr_crawl='2022-09-27')
    assert response.state == cache.CacheState.STALE
    assert response.status_code == 200
    assert response.headers == {
        'content-type': 'text/html',
    }
    assert response.links == [
        'https://www.portland.gov/transportation/page1',
        'https://www.portland.gov/transportation/page2',
    ]
