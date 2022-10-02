export PROJECT:=pbot-site-crawler
export REGION:=us-west1

deploy: deploy-crawl-url deploy-webserver

# Can only be run once.
create-pubsub-topics: create-bigquery-tables
	gcloud pubsub schemas create crawl --project=$(PROJECT) --type=AVRO "--definition=$$(cat crawl.avsc)"
	gcloud pubsub topics create crawl --project=$(PROJECT) --schema=crawl --message-encoding=JSON
	gcloud pubsub schemas create changed-pages --project=$(PROJECT) --type=AVRO "--definition=$$(cat changed-pages.avsc)"
	gcloud pubsub topics create changed-pages --project=$(PROJECT) --schema=changed-pages --message-encoding=JSON
	gcloud pubsub subscriptions create sub-changed-pages-bigquery --topic=changed-pages \
		--bigquery-table=$(PROJECT):crawl.changed-pages --use-topic-schema --drop-unknown-fields

create-bigquery-tables:
	bq mk --table $(PROJECT):crawl.changed-pages crawl:DATE,page:STRING,change:STRING

deploy-crawl-url:
	gcloud functions deploy crawl-url --gen2 --project=$(PROJECT) --region=$(REGION) --runtime=python310 \
		--source=crawl-url-function/ --entry-point=crawl_url \
		--trigger-topic=crawl --max-instances=1 --memory=256Mi


deploy-webserver:
  gcloud run deploy webserver --project=$(PROJECT) --region=us-west1 --source webserver/ \
		--memory 512Mi --cpu 1

start-emulator:
	gcloud beta emulators pubsub start --project=$(PROJECT)

test: test-crawl-url

test-crawl-url:
	cd crawl-url-function; test/emulate_servers.sh python -m pytest -v

start-crawl:
	gcloud pubsub topics publish crawl --project=$(PROJECT) --message='{"url": "https://www.portland.gov/transportation", "crawl": "", "prev_crawl": ""}'
