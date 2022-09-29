import json
from datetime import timedelta
from hashlib import sha256

import main
from cloudevents.http import CloudEvent

main.crawl_delay = timedelta(seconds=0)


def test_crawl_url(firestore_db, requests_mock, pull_from_crawl):
    TEST_LINK_TARGET = 'https://www.portland.gov/transportation/page3'
    PAGE_CONTENT = f'<a href="{TEST_LINK_TARGET}">Link</a>'.encode()
    requests_mock.get(firestore_db.TEST_PAGE1, request_headers={'if-none-match': firestore_db.THE_ETAG},
                      headers={'etag': firestore_db.THE_ETAG + ' next',
                               'content-type': 'text/html'},
                      content=PAGE_CONTENT)
    requests_mock.get(firestore_db.TEST_PAGE1,
                      headers={'etag': firestore_db.THE_ETAG + ' next',
                               'content-type': 'text/html'},
                      content=PAGE_CONTENT)

    event = CloudEvent({'type': '', 'source': ''}, {
        'prev_crawl': '2022-09-26',
        'crawl': '2022-09-27',
        'url': firestore_db.TEST_PAGE1,
    })
    main.do_crawl_url(event)

    assert [doc.path for doc in firestore_db.collection('crawl-2022-09-27').list_documents()] == [
        firestore_db.collection(
            'crawl-2022-09-27').document(sha256(firestore_db.TEST_PAGE1.encode()).hexdigest()).path,
    ]
    assert firestore_db.collection('crawl-2022-09-27').document(sha256(firestore_db.TEST_PAGE1.encode()).hexdigest()).get().to_dict() == {
        'url': firestore_db.TEST_PAGE1,
        'status_code': 200,
        'headers': {
            'etag': firestore_db.THE_ETAG + ' next',
            'content-type': 'text/html'
        },
        'content': firestore_db.collection('content').document(sha256(PAGE_CONTENT).hexdigest()),
    }

    assert json.loads(pull_from_crawl().message.data) == {
        'prev_crawl': '2022-09-26',
        'crawl': '2022-09-27',
        'url': TEST_LINK_TARGET,
    }
