terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.40"
    }
  }
}

locals {
  project = "pbot-site-crawler"
  region  = "us-west1"
}

provider "google" {
  project = local.project
  region  = local.region
}

resource "google_pubsub_schema" "crawl" {
  name       = "crawl"
  type       = "AVRO"
  definition = file("crawl.avsc")
}

resource "google_pubsub_topic" "crawl" {
  name = "crawl"

  depends_on = [google_pubsub_schema.crawl]
  schema_settings {
    schema   = google_pubsub_schema.crawl.id
    encoding = "JSON"
  }
}

resource "google_pubsub_schema" "changed-pages" {
  name       = "changed-pages"
  type       = "AVRO"
  definition = file("changed-pages.avsc")
}

resource "google_pubsub_topic" "changed-pages" {
  name = "changed-pages"

  depends_on = [google_pubsub_schema.changed-pages]
  schema_settings {
    schema   = google_pubsub_schema.changed-pages.id
    encoding = "JSON"
  }
}

resource "google_bigquery_dataset" "crawl" {
  dataset_id  = "crawl"
  description = "Holds crawl results"
  location    = "us-west1"
}

resource "google_bigquery_table" "changed-pages" {
  dataset_id = google_bigquery_dataset.crawl.dataset_id
  table_id   = "changed-pages"

  schema = jsonencode(
    [
      {
        name = "crawl",
        type = "DATE",
        #mode        = "REQUIRED",
        description = "The date of the crawl this change describes"
      },
      {
        name = "page",
        type = "STRING",
        #mode        = "REQUIRED",
        description = "URL of the page that changed"
      },
      {
        name = "change",
        type = "STRING",
        #mode        = "REQUIRED",
        description = "ADD, DEL, or CHANGE"
      },
      {
        name        = "diff",
        type        = "STRING",
        mode        = "NULLABLE",
        description = "If present, a diff between the current crawl's page and the previous version"
      }
  ])
}

resource "google_pubsub_subscription" "sub-changed-pages-bigquery" {
  name  = "sub-changed-pages-bigquery"
  topic = google_pubsub_topic.changed-pages.name

  bigquery_config {
    table               = "${google_bigquery_table.changed-pages.project}:${google_bigquery_table.changed-pages.dataset_id}.${google_bigquery_table.changed-pages.table_id}"
    use_topic_schema    = true
    drop_unknown_fields = true
  }
}

resource "google_storage_bucket" "function-source" {
  name                        = "${local.project}-function-source"
  location                    = "us-west1"
  uniform_bucket_level_access = true
  force_destroy               = true

  lifecycle_rule {
    condition {
      age = 1
    }
    action {
      type = "Delete"
    }
  }
}

# TODO: Use https://registry.terraform.io/providers/hashicorp/archive/latest/docs/data-sources/archive_file
resource "google_storage_bucket_object" "crawl-url-function" {
  name   = "crawl-url-function-${filebase64sha256("crawl-url-function.zip")}.zip"
  bucket = google_storage_bucket.function-source.name
  source = "crawl-url-function.zip" # Add path to the zipped function source code
}

resource "google_cloudfunctions2_function" "start-crawl" {
  name        = "start-crawl"
  description = "Crawl the weekly crawl"
  location    = "us-west1"

  build_config {
    runtime     = "python310"
    entry_point = "start_crawl"
    source {
      storage_source {
        bucket = google_storage_bucket.function-source.name
        object = google_storage_bucket_object.crawl-url-function.name
      }
    }
  }



  service_config {
    max_instance_count = 1
    available_memory   = "256Mi"
    timeout_seconds    = 60
  }
}

output "start-crawl-uri" {
  value = google_cloudfunctions2_function.start-crawl.service_config[0].uri
}

resource "google_cloudfunctions2_function" "crawl-url" {
  name        = "crawl-url"
  description = "Crawl one URL from the crawl PubSub topic"
  location    = "us-west1"

  build_config {
    runtime     = "python310"
    entry_point = "crawl_url"
    source {
      storage_source {
        bucket = google_storage_bucket.function-source.name
        object = google_storage_bucket_object.crawl-url-function.name
      }
    }
  }

  event_trigger {
    pubsub_topic   = google_pubsub_topic.crawl.id
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    retry_policy   = "RETRY_POLICY_DO_NOT_RETRY"
    trigger_region = "us-west1"
  }

  service_config {
    max_instance_count = 1
    available_memory   = "256Mi"
    timeout_seconds    = 60
  }
}

resource "google_pubsub_subscription" "crawl-to-crawl-url" {
  name  = "eventarc-us-west1-crawl-url-528516-sub-455"
  topic = google_pubsub_topic.crawl.name
  ack_deadline_seconds = 600
  message_retention_duration = "86400s"

  labels = {
    goog-eventarc = ""
  }

  push_config {
    push_endpoint = google_cloudfunctions2_function.crawl-url.service_config[0].uri

    oidc_token {
      audience              = google_cloudfunctions2_function.crawl-url.service_config[0].uri
      service_account_email = "918189120933-compute@developer.gserviceaccount.com"
    }
    attributes = {
      x-goog-version = "v1"
    }
  }
  retry_policy {
    maximum_backoff = "600s"
    minimum_backoff = "10s"
  }
}

resource "google_cloud_scheduler_job" "start-pbot-crawl" {
  name             = "start-pbot-crawl"
  description      = "Start the weekly PBOT crawl by calling https://console.cloud.google.com/functions/details/us-west1/start-crawl?env=gen2&project=pbot-site-crawler"
  schedule         = "0 2 * * 5"
  time_zone        = "Etc/UTC"
  attempt_deadline = "600s"

  retry_config {
    retry_count = 3
  }

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.start-crawl.service_config[0].uri
    oidc_token {
      service_account_email = "scheduler-service-account@pbot-site-crawler.iam.gserviceaccount.com"
      audience              = google_cloudfunctions2_function.start-crawl.service_config[0].uri
    }
  }
}

# Building the webserver image is even more complicated: just keep using the
# Makefile for that.
