export PROJECT:=pbot-site-crawler
export REGION:=us-west1

deploy: deploy-crawl-url

# Can only be run once. Don't attach a schema because it's impossible to change
# schemas without deleting and recreating the topic.
create-pubsub-topic:
	gcloud pubsub topics create crawl --project=$(PROJECT)

deploy-crawl-url:
	gcloud functions deploy crawl-url --gen2 --project=$(PROJECT) --region=$(REGION) --runtime=python310 \
		--source=crawl-url-function/ --entry-point=crawl_url \
		--trigger-topic=crawl --max-instances=1 --memory=256Mi


start-emulator:
	gcloud beta emulators pubsub start --project=$(PROJECT)

test: test-crawl-url

test-crawl-url:
	cd crawl-url-function; test/emulate_servers.sh python -m pytest
