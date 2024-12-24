# Welcome to Cloud Functions for Firebase for Python!
# To get started, simply uncomment the below code or create your own.
# .\functions\venv\Scripts\activate
# pip install -r functions\requirements.txt
# test with firebase emulators:start --only functions
# Deploy with `firebase deploy`
# update timeout https://console.cloud.google.com/functions/list?env=gen2&invt=Abj4RQ&project=personal-podcasts-2

import time
import random
from firebase_functions import https_fn
from firebase_admin import initialize_app
from firebase_functions import scheduler_fn
from firebase_admin import firestore
from firebase_admin import storage
from openai import OpenAI

from lib.constants.global_constants import date_as_text, time_as_text
from lib.utils.utility_functions import print_in_red, message_ai_structured, db_insert
from lib.utils.ep_generation import build_full_directive, get_audio_from_script, upload_audio
from lib.tests.https_tests import generate_rss_text
from lib.constants.secrets import OPENAI_KEY

initialize_app(options={
    'storageBucket': 'personal-podcasts-2.firebasestorage.app'
})


# # functions 
@https_fn.on_request()
def https_generate_rss_text(req):
    return generate_rss_text()

# generate new episode by visiting url 
@https_fn.on_request(secrets=[OPENAI_KEY])
def new_episode_https(req: https_fn.Request) -> https_fn.Response: 
    return new_episode(req=req)

# target for scheduler to generate new episode
@scheduler_fn.on_schedule(schedule="every day 09:00", secrets=[OPENAI_KEY])
def new_episode_schedule(event: scheduler_fn.ScheduledEvent):
    return new_episode(event=event)

def new_episode(req=None, event=None):
    openai_client = OpenAI(api_key=OPENAI_KEY.value)
    # generate script

    directive = build_full_directive()
    
    print_in_red("about to generate script")
    podcast_response = message_ai_structured(openai_client=openai_client,
                            message=directive
                            )
    print_in_red("script generated")

    try:
        podcast_script = podcast_response.script
    except Exception:
        print("error getting script from podcast:", podcast_response)
        raise Exception("Error getting script from podcast:", podcast_response) 

    # print("podcast script is", podcast_response.model_dump_json()) 

    
    # create a new function with openai built in
    
    combined_audio_bytes = get_audio_from_script(podcast_script, openai_client)
    
    print_in_red("audio generated and combined")

    bucket = storage.bucket()

    upload_results = upload_audio(combined_audio_bytes, bucket)

    print_in_red("audio uploaded to bucket")
    

    episode_id = "ep_" + str(round(time.time() * 1000)) + "_" + str(random.randrange(0, 9999))
    db_insert(collection_name="episodes", data={
        # id is ep_[current time in ms]_[random number 0 to 9999]
        "episode_id": episode_id,
        "podcast_id": 1, 
        "user_id": "testUser",
        "title": f"Daily Podcast for {date_as_text}", 
        "description": f"This is your daily podcast for {date_as_text}. It was created at {time_as_text}", 
        "script_text": podcast_response.model_dump_json(),
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
        "file_name": upload_results.get("file_name"),
        "url": upload_results.get("url"),
        "duration": 0,
        "audio_generated": True,
    })

    print_in_red("db updated")

    rss_text = generate_rss_text()

    print_in_red("rss generated")

    # write the rss to a file in the blob storage
    blob = bucket.blob("rss/testUser/podcastId/testRss.xml")    
    # blob.upload_from_string(rss_text, content_type="application/rss+xml")
    blob.upload_from_string(rss_text, content_type="text/xml")
    blob.make_public()

    rss_url = blob.public_url

    print_in_red("rss uploaded. done. rss url is: " + rss_url)
    
    # downloaded_text = blob.download_as_text()
    # print_in_red("content:")
    # print("Uploaded content length:", len(downloaded_text))
    
    # send the rss as a response
    # response = make_response(rss_text)
    # response.headers.set('Content-Type', 'application/rss+xml')

    return f"<p>Episode audio generated. Rss url is {rss_url}</p>"
