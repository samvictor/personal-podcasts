# Welcome to Cloud Functions for Firebase for Python!
# To get started, simply uncomment the below code or create your own.
# .\functions\venv\Scripts\activate
# pip install -r functions\requirements.txt
# test with firebase emulators:start --only functions
# Deploy with `firebase deploy`
# update timeout https://console.cloud.google.com/functions/list?env=gen2&invt=Abj4RQ&project=personal-podcasts-2

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

testSecret = SecretParam('TEST_SECRET')
OPENAI_KEY = SecretParam('OPENAI_KEY')



initialize_app(options={
    'storageBucket': 'personal-podcasts-2.firebasestorage.app'
})


def print_in_red(text):
    print(f"\033[91m{text}\033[0m")

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

@https_fn.on_request(secrets=[testSecret])
def on_request_example(req: https_fn.Request) -> https_fn.Response:
    print("open", testSecret.value)
    return https_fn.Response("Hello world! Secret is: " + testSecret.value) 



DELAY_BETWEEN_NEWS_FETCH = 0.51
NUM_ARTICLES_PER_CATEGORY = 3
PODCAST_LENGTH = "60 lines"


timezone = timezone('EST')

# # functions 

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

def get_last_n_episodes(num_episodes=5):
    db = firestore.client()
    # num_episodes = int(request.args.get('numEpisodes', 5))  # Default to 5

    episodes = []
    docs = db.collection('episodes').order_by('created_at', direction='DESCENDING').limit(num_episodes).stream()
    # print_in_red("docs:")
    # print(docs)
    for doc in docs:
        episodes.append({
            'id': doc.id,
            'data': doc.to_dict()
        })

    return episodes


# podcast example:
# {
#     "ai_directive": "make a short podcast.",
#     "cover_image_url": "example.net",
#     "created_at": "Sun, 08 Dec 2024 01:23:31 GMT",
#     "description": "A short summary of recent events.",
#     "podcast_id": "PIiVCmdQfcGeSE7BZMj5",
#     "rss_url": "example.com",
#     "title": "Daily Summary",
#     "updated_at": "Sun, 08 Dec 2024 01:24:55 GMT",
#     "user_id": "testUser"
# }

# episode example:
# {
#     "audio_generated": false,
#     "created_at": "Mon, 25 Nov 2024 01:29:01 GMT",
#     "description": "This is your daily podcast fo",
#     "duration": 5,
#     "episode_id": "dzziKg8DEKyg5zliIwDR",
#     "file_name": "daily_update_2024-11-08_",
#     "podcast_id": "1",
#     "script_text": "{\"script\":[{\"voice\":\"fable\",\"text\":\"hi\"}]}",
#     "title": "Daily Podcast for November",
#     "updated_at": "Mon, 25 Nov 2024 01:29:28 GMT",
#     "url": "https://1rfdbdyvforthaxq.publ",
#     "user_id": "testUser"
# },

collection_name_to_id_key = {
    "episodes" : "episode_id",
    "podcasts" : "podcast_id", 
}
def db_insert(data, collection_name="episodes", id=None):    
    # if id not supplied, get id from data supplied
    if (id == None):
        # try:
        id = data[collection_name_to_id_key[collection_name]]
        # except Exception as e:    
        #     print ("error getting id from data", e)
    
    db = firestore.client()    

    # merge true for safety to avoid accidentally deleting data
    db.collection(collection_name).document(id).set(data, merge=True)

# @https_fn.on_request()
def db_update(data, collection_name="podcasts", id=None):    
    data = {
    #     "audio_generated": false,
    #     "created_at": "Mon, 25 Nov 2024 01:29:01 GMT",
    #     "description": "This is your daily podcast fo",
    #     "duration": 5,
        "podcast_id": "dzziKg8DEKyg5zliIwDR",
    #     "file_name": "daily_update_2024-11-08_",
    #     "podcast_id": "1",
    #     "script_text": "{\"script\":[{\"voice\":\"fable\",\"text\":\"hi\"}]}",
        "title": "Daily Podcast for December",
        "updated_at": firestore.SERVER_TIMESTAMP,
        # "url": "https://1rfdbdyvforthaxq.publ",
        # "user_id": "testUser"
    }

    # if id not supplied, get id from data supplied
    if (id == None):
        id = data[collection_name_to_id_key[collection_name]]

    db = firestore.client()    
    db.collection(collection_name).document(id).update(data)


voiceOptions = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
def get_audio_bytes_from_text(openai_client, text="test", voice="alloy"):
    response = openai_client.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text,
        response_format="wav"
    )

    return response.content



@https_fn.on_request()
def https_generate_rss_text(req):
    return generate_rss_text()

def generate_rss_text():
    bucket = storage.bucket()
    blobFiles = bucket.list_blobs(prefix="audio/testUser/podcastId/")
    print('response is', blobFiles)

    fg = FeedGenerator()
    fg.load_extension('podcast')
    fg.id('testUsersPodcast')
    fg.title('Sam\'s Personal Podcast')
    fg.author( {'name':'Personal Podcasts','email':'samshandymansolutions@gmail.com'} )
    fg.link( href='https://personal-podcasts.vercel.app', rel='alternate' )
    fg.logo('http://example.com/logo.jpg')
    fg.subtitle('Personal Podcasts by Sam')
    fg.language('en')
    for file in blobFiles: 
        print_in_red(file.public_url)
        print_in_red(file.content_type)
        if file.content_type and file.content_type[0:5] == 'audio':
        # if file.content_type and file.content_type[0:5] == 'text/':
            print("file is", file) 
            print("updated at", type(file.time_created)) 
            dt = file.time_created - timedelta(hours = 4)
            human_readable_date = dt.strftime("%B %d, %Y")
            human_readable_time = dt.strftime("%I:%M %p")

            fe = fg.add_entry()
            fe.title("Sam's Daily Podcast for " + human_readable_date)
             
            fe.enclosure(url=file.public_url, length=int(file.size),  type=file.content_type)
            fe.pubDate(file.time_created)
            fe.link(href=file.public_url)
            fe.guid(file.public_url, permalink=True)  
            fe.description(f"""Sam's Daily Podcast for {human_readable_date}. 
This podcast was created entirely by AI. 
It covers the latest news stories and headlines. 
It was created at {human_readable_time}. 
The code to create it was written by Sam Inniss.
Enjoy!  😎
            """)
            # fe.author(name=file.author.name, email=file.author.email)
    return fg.rss_str(pretty=True)




class Line(BaseModel):
    voice: Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    text: str
class Podcast(BaseModel):
    script: list[Line]

def message_ai_structured(openai_client, message="", role="system", chat_history=[], structure=Podcast):
    # chat history must be a list of dicts. Each dict must have role and system
    # not including latest message

    message_list = [{"role": role, "content": message}] + chat_history

    # try:


    completion = openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=message_list,
        response_format=structure,
    )

    parsed_response = completion.choices[0].message.parsed

    # except Exception as e:
    #     print("error getting message from ai", e)
    #     raise Exception("error getting message from AI")

    # print(response_message)
    return parsed_response


def get_full_content_from_rss(url, num_articles = NUM_ARTICLES_PER_CATEGORY):
    # takes rss feed url
    # gets first n aricles
    # scrapes page
    # returns a list of dictionaries with all text on those pages

    feed = feedparser.parse(url)
    
    if feed.status != 200:
        raise Exception("Failed to get RSS feed. Status code:", feed.status) 

    # [print(json.dumps(entry, indent=4)) for entry in feed.entries]

    all_entries = feed.entries

    full_content = []

    local_num_articles = num_articles
    # print ("all entries length", len(all_entries))
    # TODO: fix this. When an article fails to load, we need to get another article to replace it
    # right now, no article replaces it because incrementing local_num_articles doesn't work
    for entry in all_entries[0:local_num_articles]:
        # print("local num articles before", local_num_articles)
        try:
            response = requests.get(entry.link)
            soup = BeautifulSoup(response.content, "html.parser") 
            content = soup.get_text()

            # print("content for", entry.title, "time is", time.time()) 

            # skip live stream
            if entry.title == "LIVE:  ABC News Live":
                # since we couldn't get this article, fetch another article to take its place
                local_num_articles = min(len(all_entries) - 1, local_num_articles + 1)
                # print("local num articles after because of live", local_num_articles)
                time.sleep(DELAY_BETWEEN_NEWS_FETCH)

                continue

            full_content.append({"title": entry.title, "content": content})
            
            # avoid overwhelming servers by putting a delay between requests    
        except Exception as e:
            print("Error getting ", entry.link, ": ", e)
            # since we couldn't get this article, fetch another article to take its place
            local_num_articles = min(len(all_entries) - 1, local_num_articles + 1)
            # print("local num articles after because of exception", local_num_articles)

        time.sleep(DELAY_BETWEEN_NEWS_FETCH)
    return full_content
    

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


# "alloy", "echo", "fable", "nova", "shimmer".    
voice1 = "fable"
voice2 = "nova"

directive = f"""Create a podcast that is {PODCAST_LENGTH} long using these characters: "Samuel" and "Samantha". 
You are making a daily podcast that has a new episode every day. 
They should introduce themselves. As a podcast, it should be realistic, not fantastical. 
Your response should only be valid JSON. It should be a list of dictionaries. 
Each dictionary should contain 2 keys: "text" for what that character says and "voice" for which character is speaking. 
The voice for "Samuel" should be "{voice1}", and the voice for "Samantha" should be "{voice2}".
"{voice1}" and "{voice2}" are your only options for the contents of the "voice" field.
I will be putting your response directly into a json parser so don't add anything else other than valid json."""

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

 
@https_fn.on_request(secrets=[OPENAI_KEY])
def new_episode_https(req: https_fn.Request) -> https_fn.Response: 
    return new_episode(req=req)

@scheduler_fn.on_schedule(schedule="every day 09:00", secrets=[OPENAI_KEY])
def new_episode_schedule(event: scheduler_fn.ScheduledEvent):
    return new_episode(event=event)

def new_episode(req=None, event=None):
    openai_client = OpenAI(api_key=OPENAI_KEY.value)
    # generate script

    
    headline_articles = get_full_content_from_rss('https://abcnews.go.com/abcnews/topstories') 

    headlines_section_of_text_for_ai = """ There should be a 'Headlines' section of the podcast.
    During this section, have the characters talk about these articles. 
    They are top headlines and the content of the article: """
    for this_article in headline_articles:
        headlines_section_of_text_for_ai += f"Title: {this_article.get("title")}, Content: {this_article.get("content")}. "
    
    
    # sports_articles = get_full_content_from_rss('https://abcnews.go.com/abcnews/sportsheadlines') 

    # sports_section_of_text_for_ai = """ There should be a 'Sports' section of the podcast.
    # During this section, have the characters talk about these articles. 
    # They are some latest sports articles: """
    # for this_article in sports_articles:
    #     sports_section_of_text_for_ai += f"Title: {this_article.get("title")}, Content: {this_article.get("content")}. "
    
    
    tech_articles = get_full_content_from_rss('https://abcnews.go.com/abcnews/technologyheadlines') 

    tech_section_of_text_for_ai = """ There should be a 'Tech' section of the podcast.
    During this section, have the characters talk about these articles. 
    They are some latest technology articles: """
    for this_article in tech_articles:
        tech_section_of_text_for_ai += f"Title: {this_article.get("title")}, Content: {this_article.get("content")}. "
    
    
    entertainment_articles = get_full_content_from_rss('https://abcnews.go.com/abcnews/entertainmentheadlines') 

    entertainment_section_of_text_for_ai = """ There should be a 'Entertainment' section of the podcast.
    During this section, have the characters talk about these articles. 
    They are some latest entertainment articles: """
    for this_article in entertainment_articles:
        entertainment_section_of_text_for_ai += f"Title: {this_article.get("title")}, Content: {this_article.get("content")}. "
    


    previous_eps = get_last_n_episodes(5)
    # trimming eps to help ai focus on important content
    trimmed_eps = [{
        "created_at": this_ep.get("created_at"), 
        "script_text": this_ep.get("script_text")
        } for this_ep in previous_eps]
    previous_eps_as_text = json.dumps(trimmed_eps, default=str)
    previous_eps_section = """Here are the last few episodes. 
    Look at the scripts and try not to repeat things from previous episodes. 
    Also, feel free to make references to the things you talked about yesterday: """ + previous_eps_as_text



    fun_facts_section = """ At the end there should be a Fun Fact section where they say something interesting or a fun fact about today.
    If today is a holiday, they could wish the listener a happy [holiday] or national [xyz] day. 
    Or they could mention something that happened on this day years ago.  """
    
    date_as_text = datetime.now(timezone).strftime("%B %d, %Y")
    time_as_text = datetime.now(timezone).strftime("%H:%M")
    datetime_as_text = date_as_text + " at " + time_as_text
    
    current_datetime_section = f" Today's date is {datetime_as_text}. Make sure you greet the listener at the start of the podcast. In your greeting mention the current day of the week and the date. E.g. 'Today is Monday, June 1st, 2025. Happy Monday! "
    
    print_in_red("about to generate script")
    print(previous_eps_section)
    podcast_response = message_ai_structured(openai_client=openai_client,
                            message=directive 
                             + headlines_section_of_text_for_ai
                            #  + sports_section_of_text_for_ai
                             + tech_section_of_text_for_ai
                             + entertainment_section_of_text_for_ai 
                             + current_datetime_section
                             + fun_facts_section
                             + previous_eps_section
                            )
    print_in_red("script generated")
    try:
        podcast_script = podcast_response.script
    except Exception:
        print("error getting script from podcast:", podcast_response)
        raise Exception("Error getting script from podcast:", podcast_response) 

    # print("podcast script is", podcast_response.model_dump_json()) 

    
    episode_id = "ep_" + str(round(time.time() * 1000)) + "_" + str(random.randrange(0, 9999))

    db_insert(collection_name="episodes", data={
        # id is ep_[current time in ms]_[random number 0 to 9999]
        "episode_id": episode_id,
        "podcast_id": 1, 
        "user_id": "testUser",
        "title": f"Daily Podcast for {date_as_text}", 
        "description": f"This is your daily podcast for {date_as_text}. It was created at {time_as_text}", 
        # "file_name": audio_file_name,
        # "url": audio_url,
        # "duration": audio_duration,
        "script_text": podcast_response.model_dump_json(),
        "audio_generated": False,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })
    
    # create a new function with openai built in
    openai_client = OpenAI(api_key=OPENAI_KEY.value)
    get_audio_bound_client = partial(get_audio_bytes_from_text, openai_client)

    # for every line in script, generate audio
    text_list = []
    voice_list = []

    # for script_line in podcast_script:
    #     text_list.append(script_line.text)
    #     voice_list.append(script_line.voice.lower())

    audio_bytes = []
    for script_line in podcast_script:
        # print_in_red("turned this to speech:")
        # print(script_line.text)
        # avoid rate limit
        # time.sleep(DELAY_BETWEEN_NEWS_FETCH)
        audio_bytes.append(get_audio_bytes_from_text(openai_client=openai_client, 
                            text=script_line.text,
                            voice=script_line.voice.lower()))
    # list(map(get_audio_bound_client, text_list, voice_list))

    delay_length_between_audio_clips = 2000
    def fade_in_audio(audio_bytes):
        # mute first and last 100 bytes of audio (set to 0)
        # helps with combining clips without popping
        # actually removing some kind of meta data from beginning
        # can't do this to first clip

        CHANGE_RANGE = 100
        audio_length = len(audio_bytes)
        if audio_length <= CHANGE_RANGE:
            return audio_bytes
        
        audio_list = list(audio_bytes)

        for i in range(0, CHANGE_RANGE):
            # mute first 100 bytes
            audio_list[i] = 0
        #     # mute last 100 bytes
            audio_list[audio_length - i - 1] = 0
        
        # add some empty space at the beginning
        # to simulate a pause before speech
        audio_list = [0] * delay_length_between_audio_clips + audio_list

        return bytes(audio_list)
    
    def sum_bytes(bytes_list):
        if not bytes_list or len(bytes_list) < 1:
            raise ValueError("Bad input for bytes_list")
        if len(bytes_list) == 1:
            return bytes_list[0]

        combined_bytes = bytes_list[0]
        for i in range(1, len(bytes_list)):
            combined_bytes += bytes_list[i]
        
        return combined_bytes


    combined_audio_bytes = audio_bytes[0]
    if len(audio_bytes) > 1:
        combined_audio_bytes += sum_bytes( list(map(fade_in_audio, audio_bytes[1:])))
    audio_duration  =0


    audio_file_name = "daily_update_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".wav"
    file_path = "audio/testUser/podcastId/" + audio_file_name

    
    bucket = storage.bucket()
    blob = bucket.blob(file_path)
    
    # Upload the audio bytes
    blob.upload_from_string(combined_audio_bytes, content_type="audio/wav") 
    blob.make_public()

    audio_url = blob.public_url

    db_update(collection_name="episodes", id=episode_id, data={
        "file_name": audio_file_name,
        "url": audio_url,
        "duration": audio_duration,
        "audio_generated": True,
    })

    rss_text = generate_rss_text()

    # write the rss to a file in the blob storage
    blob = bucket.blob("rss/testUser/podcastId/testRss.xml")    
    # blob.upload_from_string(rss_text, content_type="application/rss+xml")
    blob.upload_from_string(rss_text, content_type="text/xml")
    blob.make_public()

    rss_url = blob.public_url
    
    downloaded_text = blob.download_as_text()
    print_in_red("content:")
    print("Uploaded content length:", len(downloaded_text))
    
    # send the rss as a response
    # response = make_response(rss_text)
    # response.headers.set('Content-Type', 'application/rss+xml')

    return f"<p>Episode audio generated. Rss url is {rss_url}</p>"
