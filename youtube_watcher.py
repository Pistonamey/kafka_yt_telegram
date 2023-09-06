#!/usr/bin/python

import logging
import sys
import requests
import os
from pprint import pformat
import json
from dotenv import load_dotenv
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.serialization import StringSerializer
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka import SerializingProducer

load_dotenv()

API_KEY = os.getenv("API_KEY")
YOUTUBE_PLAYLIST_ID = os.getenv("youtube_playlist_id")


def fetch_playlist_items_page(google_api_key, youtube_playlist_id, page_token):
    response = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", params={
        "key": google_api_key,
        "playlistId": youtube_playlist_id,
        "part": "contentDetails",
        "pageToken": page_token
    })

    payload = json.loads(response.text)
    logging.debug("GOT %s", payload)
    return payload


def fetch_playlist_items(google_api_key, youtube_playlist_id, page_token=None):
    payload = fetch_playlist_items_page(
        google_api_key, youtube_playlist_id, page_token)

    yield from payload["items"]
    next_page_token = payload.get("nextPageToken")

    if next_page_token is not None:
        yield from fetch_playlist_items(google_api_key, youtube_playlist_id, next_page_token)


def fetch_videos_page(google_api_key, video_id, page_token):

    response = requests.get("https://www.googleapis.com/youtube/v3/videos", params={
        "key": google_api_key,
        "id": video_id,
        "part": "snippet,statistics",
        "pageToken": page_token
    })

    payload = json.loads(response.text)

    logging.debug("GOT %s", payload)
    return payload


def fetch_videos(google_api_key, video_id, page_token=None):
    payload = fetch_videos_page(google_api_key, video_id, page_token)

    yield from payload["items"]
    next_page_token = payload.get("nextPageToken")

    if next_page_token is not None:
        yield from fetch_videos(google_api_key, video_id, next_page_token)


def summarize_video(video):
    return {
        "video_id": video["id"],
        "title": video["snippet"]["title"],
        "views": int(video["statistics"].get("viewCount", 0)),
        "likes": int(video["statistics"].get("likeCount", 0)),
        "comments": int(video["statistics"].get("commentCount", 0)),

    }


def on_delivery(err, record):
    pass


def main():
    logging.info("START")
    schema_registry_client = SchemaRegistryClient({
        "url": "https://psrc-9jzo5.us-central1.gcp.confluent.cloud",
        "basic.auth.user.info": "CXIKHWXWKELV7C4J:XU8lSnGbPEHFi7y8Z/D7MDVPphBik1wbgU+r9GUdt1d12e7jfuDbIB1ga6q7/PVW",
    })
    youtube_videos_value_schema = schema_registry_client.get_latest_version(
        "youtube_videos-value")
    kafka_config = {
        "bootstrap.servers": "pkc-6ojv2.us-west4.gcp.confluent.cloud:9092",
        "security.protocol": "sasl_ssl",
        "sasl.mechanism": "PLAIN",
        "sasl.username": "H7NXERNKFOFEJDA5",
        "sasl.password": "SowRAvo8ezrfXyP4ocRnPKDJuwU565lWqwplC0vsk/zo4hY6FcaSEK+ULQIl3Fbu"
    } | {
        "key.serializer": StringSerializer(),
        "value.serializer": AvroSerializer(
            schema_registry_client,
            youtube_videos_value_schema.schema.schema_str,
        ),
    }
    producer = SerializingProducer(kafka_config)
    for video_items in fetch_playlist_items(API_KEY, YOUTUBE_PLAYLIST_ID):
        video_id = video_items["contentDetails"]["videoId"]
        for video in fetch_videos(API_KEY, video_id):
            logging.info("GOT %s", pformat(summarize_video(video)))

        producer.produce(
            topic="youtube_videos",
            key=video_id,
            value={

                "TITLE": video["snippet"]["title"],
                "VIEWS": int(video["statistics"].get("viewCount", 0)),
                "LIKES": int(video["statistics"].get("likeCount", 0)),
                "COMMENTS": int(video["statistics"].get("commentCount", 0)),

            },
            on_delivery=on_delivery
        )
    producer.flush()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
