#! /usr/bin/env python

import argparse

import google.api_core.exceptions
from google.cloud import pubsub_v1
from google.cloud.pubsub import PublisherClient, SchemaServiceClient
from google.pubsub_v1.types import Encoding, Schema

parser = argparse.ArgumentParser(description='Create a pubsub topic.')
parser.add_argument('--project', required=True,
                    help='Google Cloud project ID')
parser.add_argument('--topic', required=True,
                    help='the name of the topic to create')
schema_args = parser.add_argument_group(
    'schema', 'require messages in this topic to match an Avro schema')
schema_args.add_argument('--schema', type=argparse.FileType(mode='r'))
schema_args.add_argument('--schema_id')
schema_args.add_argument('--message_encoding', choices=['binary', 'json'])

args = parser.parse_args()

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(args.project, args.topic)
request = {"name": topic_path}
try:
    publisher.delete_topic(topic=topic_path)
except google.api_core.exceptions.NotFound:
    pass

if args.schema or args.schema_id or args.message_encoding:
    if not args.schema or not args.schema_id or not args.message_encoding:
        parser.error(
            'schema, schema_id, and message_encoding must all be specified if any is')
    schema_client = SchemaServiceClient()
    schema_path = schema_client.schema_path(args.project, args.schema_id)
    try:
        schema_client.delete_schema(name=schema_path)
    except google.api_core.exceptions.NotFound:
        pass

    schema_client.create_schema(request={
        "parent": f'projects/{args.project}',
        "schema_id": args.schema_id,
        "schema": Schema(type_=Schema.Type.AVRO,
                            definition=args.schema.read()),
    })

    if args.message_encoding == 'binary':
        encoding = Encoding.BINARY
    elif args.message_encoding == 'json':
        encoding = Encoding.JSON
    else:
        raise ValueError(f'unknown encoding {args.message_encoding}')

    request['schema_settings'] = {
        'schema': schema_path,
        'encoding': encoding,
    }

topic = publisher.create_topic(request=request)
