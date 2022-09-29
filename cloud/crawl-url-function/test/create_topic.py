#! /usr/bin/env python

import argparse

import google.api_core.exceptions
from google.cloud import pubsub_v1

parser = argparse.ArgumentParser(description='Create a pubsub topic.')
parser.add_argument('--project', required=True,
                    help='Google Cloud project ID')
parser.add_argument('--topic', required=True,
                    help='the name of the topic to create')

args = parser.parse_args()

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(args.project, args.topic)
try:
  topic = publisher.create_topic(request={"name": topic_path})
except google.api_core.exceptions.AlreadyExists:
  # It's fine if the topic already exists.
  pass
