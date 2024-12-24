# test by visiting these paths

import time
import random
import feedparser
from feedgen.feed import FeedGenerator
import json
from datetime import datetime, timedelta
from pytz import timezone
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel
from typing import Literal
from functools import partial

from firebase_functions import https_fn
from firebase_admin import initialize_app
from firebase_functions.params import SecretParam
from firebase_functions import scheduler_fn
from firebase_admin import firestore
from firebase_admin import credentials
from firebase_admin import storage
from openai import OpenAI

from lib.utils.utility_functions import *
from lib.constants.secrets import OPENAI_KEY
from lib.constants.global_constants import directive



@https_fn.on_request()
def storage_test(req: https_fn.Request) -> https_fn.Response:
    bucket = storage.bucket()
    #The path to file
    # blob = bucket.blob("rss/testUser/podcastId/testRss.xml")
    # blob.make_public()
    # return https_fn.Response(f"public urls is {blob.public_url}")

    blobs = bucket.list_blobs(prefix="rss/testUser/podcastId/")
    retText = " HEY ".join(map(lambda b: f"name: {b.name}, url: {b.public_url}", blobs))
    # for blob in blobs:
    #     retText += "\n" + blob.name
    return https_fn.Response(f"blobs found {retText}")


@https_fn.on_request()
def get_n_podcasts(request, num_podcasts=100):
    db = firestore.client()
    num_podcasts = int(request.args.get('numPodcasts', 100))  # Default to 5

    podcasts = []
    docs = db.collection('podcasts').order_by('created_at', direction='DESCENDING').limit(num_podcasts).stream()
    
    podcasts = list(map(lambda doc : {
            'id': doc.id,
            'data': doc.to_dict()
        }, docs))

    print ("podcasts is", podcasts)

    return podcasts


@https_fn.on_request(secrets=[OPENAI_KEY])
def get_speech(request):
    openai_client = OpenAI(api_key=OPENAI_KEY.value)

    # print_in_red("before get_audio_bytes_from_text")
    audio_bytes = get_audio_bytes_from_text(
        openai_client=openai_client,
        text="Hello, hello? Is this thing on? this is a test!",
        voice="alloy"
    )

    # print_in_red("after get_audio_bytes_from_text")
    
    # Ensure audio_bytes is in bytes format
    if not isinstance(audio_bytes, bytes):
        return https_fn.Response("Error: audio_bytes is not in bytes format", status=400)

    # Upload to Google Cloud Storage
    bucket = storage.bucket()
    blob = bucket.blob("audio/testUser/podcastId/testAudio2.wav")
    
    # Upload the audio bytes
    blob.upload_from_string(audio_bytes, content_type="audio/wav") 
    # blob.upload_from_string(audio_bytes)
    blob.make_public()

    return https_fn.Response(f"Public URL is {blob.public_url}")


@https_fn.on_request()
def news_test(req: https_fn.Request) -> https_fn.Response:
    full_content = get_full_content_from_rss('https://abcnews.go.com/abcnews/topstories') 

    return https_fn.Response(f"<p style='white-space:pre-wrap'>{json.dumps(full_content, indent=4)}</p>")



@https_fn.on_request(secrets=[OPENAI_KEY])
def open_test(req: https_fn.Request) -> https_fn.Response: 
    
    openai_client = OpenAI(api_key=OPENAI_KEY.value)
    response_message = message_ai_structured(openai_client, directive)

    print(response_message)
    # print(response_message)
    return https_fn.Response(f"<p>{response_message}</p>")

@https_fn.on_request()
def eps_test(req):
    eps = get_last_n_episodes(5)
    trimmed_eps = [{
        "created_at": this_ep.get("created_at"), 
        "script_text": this_ep.get("script_text")
        } for this_ep in eps]
    print(trimmed_eps)
    return eps