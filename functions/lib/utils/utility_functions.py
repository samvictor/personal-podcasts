# useful functions that might be used across multiple modules
from lib.constants.global_constants import DELAY_BETWEEN_NEWS_FETCH, NUM_ARTICLES_PER_CATEGORY, date_as_text, time_as_text


import time
import feedparser
from feedgen.feed import FeedGenerator
from datetime import timedelta
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel
from typing import Literal

from firebase_admin import firestore
from firebase_admin import storage


def print_in_red(text):
    print(f"\033[91m{text}\033[0m")

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


# voiceOptions = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
def get_audio_bytes_from_text(openai_client, text="test", voice="alloy"):
    response = openai_client.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text,
        response_format="wav"
    )

    return response.content



def generate_rss_text():
    bucket = storage.bucket()
    blobFiles = bucket.list_blobs(prefix="audio/testUser/podcastId/")
    # print('response is', blobFiles)

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
        # print_in_red(file.public_url)
        # print_in_red(file.content_type)
        if file.content_type and file.content_type[0:5] == 'audio':
        # if file.content_type and file.content_type[0:5] == 'text/':
            # print("file is", file) 
            # print("updated at", type(file.time_created)) 
            dt = file.time_created - timedelta(hours = 4)
            human_readable_date = date_as_text
            human_readable_time = time_as_text

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