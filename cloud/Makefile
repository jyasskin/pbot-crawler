export PROJECT:=pbot-site-crawler
export REGION:=us-west1

deploy: zip-crawl-url-function deploy-webserver apply-terraform

apply-terraform: zip-crawl-url-function
	terraform apply

deploy-webserver:
	gcloud run deploy webserver --project=$(PROJECT) --region=us-west1 --source webserver/ \
		--memory 512Mi --cpu 1 --service-account=webserver@$(PROJECT).iam.gserviceaccount.com \
		--update-secrets=/etc/secrets/sendgrid/api_key=sendgrid-send-email-api-key:latest \
		--env-vars-file=webserver/production.env.yaml

start-emulator:
	gcloud beta emulators pubsub start --project=$(PROJECT)

test: test-crawl-url

test-crawl-url:
	cd crawl-url-function; ../tools/emulate_servers.sh python -m pytest -vv

start-crawl:
	# gcloud pubsub topics publish crawl --project=$(PROJECT) --message='{"url": "https://www.portland.gov/transportation", "crawl": "", "prev_crawl": ""}'
	curl -i -X POST https://start-crawl-26h4rfwp7a-uw.a.run.app -H "Authorization: bearer $(gcloud auth print-identity-token)"

zip-crawl-url-function:
	cd crawl-url-function && zip --filesync -r ../crawl-url-function.zip . --exclude @.zipignore
