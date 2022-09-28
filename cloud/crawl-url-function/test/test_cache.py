from hashlib import sha256

import cache
import pytest
import requests
from google.cloud import firestore

TEST_PAGE1 = 'https://www.portland.gov/transportation'
TEST_LINK_TARGET = 'https://www.portland.gov/transportation/link/target'
THE_ETAG = 'This is an ETag'


@pytest.fixture
def firestore_db():
    db = firestore.Client()
    try:
        url = TEST_PAGE1
        db.collection('crawl-2022-09-26').document(sha256(url.encode()).hexdigest()).set({
            'url': url,
            'status_code': 200,
            'headers': {
                'content-type': 'text/html',
                'etag': THE_ETAG,
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
    finally:
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
        'etag': THE_ETAG,
    }
    assert response.links == [
        'https://www.portland.gov/transportation/page1',
        'https://www.portland.gov/transportation/page2',
    ]


def test_cached_response_fetch_304(firestore_db, requests_mock):
    requests_mock.get(TEST_PAGE1, request_headers={'if-none-match': THE_ETAG},
                      status_code=304,
                      headers={'last-modified': 'today'})
    response = cache.CachedResponse(
        firestore_db, TEST_PAGE1, prev_crawl='2022-09-26', curr_crawl='2022-09-27')
    assert response.state == cache.CacheState.STALE
    fresh = response.fetch(requests.Session())
    assert fresh.status_code == 200
    assert fresh.headers == {
        'last-modified': 'today',
        'content-type': 'text/html',
        'etag': THE_ETAG,
    }
    assert fresh.links == [
        'https://www.portland.gov/transportation/page1',
        'https://www.portland.gov/transportation/page2',
    ]


def test_cached_response_fetch_200(firestore_db, requests_mock):
    PAGE_CONTENT = f'<a href="{TEST_LINK_TARGET}">Link</a>'.encode()
    requests_mock.get(TEST_PAGE1, request_headers={'if-none-match': THE_ETAG},
                      headers={'etag': THE_ETAG + ' next',
                               'content-type': 'text/html; param'},
                      content=PAGE_CONTENT)
    response = cache.CachedResponse(
        firestore_db, TEST_PAGE1, prev_crawl='2022-09-26', curr_crawl='2022-09-27')
    assert response.state == cache.CacheState.STALE
    fresh = response.fetch(requests.Session())
    assert fresh.status_code == 200
    assert fresh.headers == {
        'etag': THE_ETAG + ' next',
        'content-type': 'text/html; param',
    }
    assert fresh.content_reference == firestore_db.collection(
        'content').document(sha256(PAGE_CONTENT).hexdigest())
    assert fresh.links == [
        TEST_LINK_TARGET,
    ]
    assert fresh.content_reference.get().to_dict() == {
        'links': [
            TEST_LINK_TARGET,
        ]
    }


def test_write_fresh_response(firestore_db):
    response = cache.FreshResponse(TEST_LINK_TARGET)
    response.status_code = 200
    response.headers = {
        'etag': THE_ETAG,
        'content-type': 'text/html'
    }
    response.content_reference = firestore_db.collection(
        'content').document('2')
    response.write_to_firestore(firestore_db, '2022-09-27')
    assert firestore_db.collection('crawl-2022-09-27').document(sha256(TEST_LINK_TARGET.encode()).hexdigest()).get().to_dict() == {
        'url': TEST_LINK_TARGET,
        'status_code': 200,
        'headers': {
            'etag': THE_ETAG,
            'content-type': 'text/html'
        },
        'content': response.content_reference,
    }
