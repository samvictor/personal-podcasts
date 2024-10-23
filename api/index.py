import os
import time
from dotenv import load_dotenv
from pathlib import Path
import feedparser
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, send_file, Response, make_response
from feedgen.feed import FeedGenerator
import json
from datetime import datetime, timedelta
from pytz import timezone
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel
from typing import Literal

DELAY_BETWEEN_NEWS_FETCH = 0.21
NUM_ARTICLES_PER_CATEGORY = 3
PODCAST_LENGTH = "20 lines"


timezone = timezone('EST')

# Load environment variables from .env.development.local file
env_path = Path('.') / '.env.development.local'
load_dotenv(dotenv_path=env_path)

import vercel_blob
blob_key = os.environ.get('BLOB_READ_WRITE_TOKEN')

from openai import OpenAI
openai_key = os.environ.get('OPENAI_KEY')
openai_client = OpenAI(api_key=openai_key)

news_api_key = os.environ.get('NEWS_API_KEY')

vercel_blob_base = "https://1rfdbdyvforthaxq.public.blob.vercel-storage.com"

# functions 
def get_db_connection():
    db_url = os.environ.get("POSTGRES_URL_NON_POOLING")
    if not db_url:
        raise ValueError("POSTGRES_URL_NON_POOLING environment variable is not set")
    
    try:
        connection = psycopg2.connect(db_url)
        return connection
    except Exception as e:
        print(f"\033[91mError connecting to database: {str(e)}\033[0m")
        return None

def get_all_podcasts():
    connection = get_db_connection()
    if not connection:
        raise Exception("Unable to connect to the database")
        return None
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('SELECT * FROM podcasts;')
            result = cursor.fetchall()
            # for row in result:
            #     print(row)
            cursor.close()
            return jsonify(result)
    finally:
        connection.close()

def get_last_n_episodes(num_episodes):
    if not type(num_episodes) == int:
        raise TypeError("num_episodes must be an int")
    connection = get_db_connection()
    if not connection:
        raise Exception("Unable to connect to the database")
    
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                           SELECT * FROM episodes 
                           ORDER BY created_at DESC
                           LIMIT %s;
                           """, (num_episodes, ))
            result = cursor.fetchall()
            # for row in result:
            #     print(row)
            cursor.close()
            episodes = [dict(row) for row in result] 
            return episodes
    finally:
        connection.close()


table_name_options = ["podcasts", "users", "episodes"]
key_options = {
    "podcasts": ["user_id", "title", "description", 
                    "ai_directives_by_section", "rss_url", "cover_image_url"],
    "episodes": ["cover_image_url", "podcast_id", "user_id", "title", "description", 
                    "file_name", "url", "duration", "script_text", "audio_generated"],
    "users": ["user_id", "username", "podcast_ids"]
}

def db_sanitize_table_name(table_name="podcasts"):
    # check if table_name is valid to avoid sql injection
    if table_name not in table_name_options:
        raise Exception("Invalid table name")
    
def db_sanitize_keys(table_name="podcasts", data={}):
    # check if data keys are valid to avoid sql injection
    table_items = data.items()
    for key, _ in table_items:
        if key not in key_options[table_name]:
            raise Exception(f"Invalid key, {key} not in {key_options[table_name]}")

def db_insert(table_name="podcasts", data={}):
    # sanitize the table name and data keys
    db_sanitize_table_name(table_name)
    db_sanitize_keys(table_name, data)

    # connect to vercel postgres database using psycopg2
    connection = get_db_connection()
    if not connection:
        raise Exception("Unable to connect to the database")
    
    # get keys and values sepearatly. guaranteed to be in matching order
    table_items = data.items()
    keys = ", ".join([key for key, _ in table_items])
    values = tuple(value for _, value in table_items)
    placeholders = ", ".join(["%s" for _ in values])

    try:
        cursor = connection.cursor()
        cursor.execute(f"INSERT INTO {table_name} ({keys}) VALUES ({placeholders})",
            values)
        connection.commit()
    finally:
        cursor.close()
        connection.close()

        

def db_update(table_name="podcasts", id_column_name="podcast_id", id=0, data={}):
    # sanitize the table name and data keys
    db_sanitize_table_name(table_name)
    db_sanitize_keys(table_name, data)
    
    # connect to vercel postgres database using psycopg2
    connection = get_db_connection()
    if not connection:
        raise Exception("Unable to connect to the database")
    
    # get keys and values sepearatly. guaranteed to be in matching order
    table_items = data.items()
    # we're looking for something that looks like: "field1=%s, field2=%s, ..."
    keys = "=%s, ".join([key for key, _ in table_items])
    values = tuple(value for _, value in table_items)
    values_with_id = values + (id,)

    try:
        cursor = connection.cursor()
        # =%s after {keys} because the join won't add it after the last key
        cursor.execute(f"UPDATE {table_name} SET {keys}=%s WHERE {id_column_name} = %s",
            values_with_id)
        connection.commit()
    finally:
        cursor.close()
        connection.close()


voiceOptions = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
def get_audio_bytes_from_text(text="test", voice="alloy"):
    response = openai_client.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text,
        response_format="wav"
    )

    # print("content is", response.content)

    
    # audio_content = BytesIO(response.content)
    # print('content is', audio_content)
    # audio_content.seek(0)
    # return audio_content.read()
    return response.content


def generate_rss_text():
    blobFiles = vercel_blob.list({"prefix": "audio/"}).get('blobs')
    # print('response is', blobFiles)
    fg = FeedGenerator()
    fg.load_extension('podcast')
    fg.id('testUsersPodcast')
    fg.title('Sam\'s Personal Podcast')
    fg.author( {'name':'Personal Podcasts','email':'samshandymansolutions@gmail.com'} )
    fg.link( href='https://personal-podcasts.vercel.app', rel='alternate' )
    fg.logo('http://example.com/logo.jpg')
    fg.subtitle('Personal Podcasts by Sam')
    # fg.link( href='http://larskiesow.de/test.atom', rel='self' ) 
    fg.language('en')
    for file in blobFiles: 
        if file.get('contentType') and file.get('contentType')[0:5] == 'audio':
            # print("file is", file) 
            # print("updated at", file.get("uploadedAt")) 
            # process time stamp into something more human readable
            timestamp_str = file.get("uploadedAt").replace("Z", "+00:00")
            dt = datetime.fromisoformat(timestamp_str) - timedelta(hours = 4)
            human_readable_date = dt.strftime("%B %d, %Y")
            human_readable_time = dt.strftime("%I:%M %p")

            fe = fg.add_entry()
            fe.title("Sam's Daily Podcast for " + human_readable_date)
             
            fe.enclosure(url=file.get('url'), length=int(file.get('size')/100),  type=file.get('contentType'))
            fe.pubDate(file.get('uploadedAt'))
            fe.link(href=file.get('url'))
            fe.guid(file.get('url'), permalink=True)  
            fe.description(f"""Sam's Daily Podcast for {human_readable_date}. 
This podcast was created entirely by AI. 
It covers the latest news stories and headlines. 
It was created at {human_readable_time}. 
The code to create it was written by Sam Inniss.
Enjoy!  😎
            """)
            # fe.author(name=file.author.name, email=file.author.email)
    return fg.rss_str(pretty=True)


def message_ai(message="", role="system", chat_history=[]):
    # chat history must be a list of dicts. Each dict must have role and system
    # not including latest message

    message_list = [{"role": role, "content": message}] + chat_history

    response_message = ""
    # try:
    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=message_list
    )

    response_message = completion.choices[0].message.content
    # except Exception as e:
    #     print("error getting message from ai", e)
    #     raise Exception("error getting message from AI")

    # print(response_message)
    return response_message


class Line(BaseModel):
    voice: Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    text: str
class Podcast(BaseModel):
    script: list[Line]

def message_ai_structured(message="", role="system", chat_history=[], structure=Podcast):
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

    for entry in all_entries[0:num_articles]:
        response = requests.get(entry.link)
        soup = BeautifulSoup(response.content, "html.parser") 
        content = soup.get_text()

        # print("content for", entry.title, "time is", time.time())

        full_content.append({"title": entry.title, "content": content})
        
        # avoid overwhelming servers by putting a delay between requests    
        time.sleep(DELAY_BETWEEN_NEWS_FETCH) 

    return full_content
# Flask app
app = Flask(__name__)

@app.route("/api/test-insert")
def test_insert():
    db_insert(table_name="podcasts", data={
        "user_id": 1, 
        "title": "test title", 
        "description": "test description    ", 
        "ai_directives_by_section": json.dumps([{"section": "test1", "directives": "test1"}, {"section": "test2", "directives": "test2"}]),
        "rss_url": "test rss url", 
        "cover_image_url": "test cover image url"
    })
    return "<p>Inserted!</p>"

@app.route("/api/test-update")
def test_update():
    db_update(table_name="podcasts", id_column_name="podcast_id", id=1, data={
        "title": "Daily Summary", 
        # "description": "test2 description", 
        # "ai_directives_by_section": json.dumps([{"section": "test3", "directives": "test3"}, {"section": "test4", "directives": "test4"}]), 
        # "rss_url": "test2 rss url", 
        # "cover_image_url": "test2 cover image url"
    })
    return "<p>Updated!</p>"

@app.route("/api/podcasts")
def get_podcasts():
   return get_all_podcasts()

@app.route("/api/python")
def hello_world():
    return "<p>Hello, World!</p>"

@app.route("/api/speech")
def get_speech():
    audio_bytes = get_audio_bytes_from_text(
        text="Hello, hello? Is this thing on? this is a test!",
        voice="alloy"
    )
    vercel_blob.put(path='/audio/testUser/podcastId/testAudio.mp3',
        data=audio_bytes,
        options={
            "addRandomSuffix": "false",
        })
    return "<p>Audio saved!</p>"


@app.route('/api/update-rss')
def update_rss():
    rss_text = generate_rss_text()

    # write the rss to a file in the blob storage
    vercel_blob.put(path='/rss/testUser/podcastId/testRss.xml', data=rss_text, options={
                "addRandomSuffix": "false",
            })

    # send the rss as a response
    response = make_response(rss_text)
    response.headers.set('Content-Type', 'application/rss+xml')

    return response

@app.route('/api/cron')
def cron():
    print('cron job running')
    return jsonify({'message': 'Cron job executed successfully'})

@app.route('/api/news-test')
def news_test():
    full_content = get_full_content_from_rss('https://abcnews.go.com/abcnews/topstories') 

    return f"<p style='white-space:pre-wrap'>{json.dumps(full_content, indent=4)}</p>" 


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

@app.route('/api/open-test')
def open_test():
    response_message = message_ai(directive)

    print(json.loads(response_message))
    # print(response_message)
    return f"<p>{response_message}</p>"

@app.route('/api/eps-test')
def eps_test():
    eps = get_last_n_episodes(100)
    trimmed_eps = [{
        "created_at": this_ep.get("created_at"), 
        "script_text": this_ep.get("script_text")
        } for this_ep in eps]
    print(trimmed_eps)
    return eps


# @app.route('/api/struct-test')
# def struct_test():
#     completion = openai_client.beta.chat.completions.parse(
#         model="gpt-4o-mini",
#         messages=[
#             {"role": "system", "content": "make a short podcast"},
#         ],
#         response_format=Podcast,
#     )

#     podcast = completion.choices[0].message.parsed
#     print("event is", podcast.model_dump_json()) 
#     return  ["text:"+line.text + " voice:"+line.voice  for line in podcast.script]
 
@app.route('/api/new-episode') 
def new_episode():
    #  ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    
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
    
    current_datetime_section = f" Today's date is {datetime_as_text}. "
    
    text_list = []
    voice_list = []

    podcast_response = message_ai_structured(directive 
                             + headlines_section_of_text_for_ai
                            #  + sports_section_of_text_for_ai
                             + tech_section_of_text_for_ai
                             + entertainment_section_of_text_for_ai 
                             + current_datetime_section
                             + fun_facts_section
                             + previous_eps_section
                            )
    try:
        podcast_script = podcast_response.script
    except Exception:
        print("error getting script from podcast:", podcast_response)
        raise Exception("Error getting script from podcast:", podcast_response) 

    # print("podcast script is", podcast_response.model_dump_json()) 

    for script_line in podcast_script:
        text_list.append(script_line.text)
        voice_list.append(script_line.voice.lower())
        
    audio_bytes = list(map(get_audio_bytes_from_text, text_list, voice_list))

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


    audio_file_name = "daily_update_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".mp3"
    file_path = "/audio/testUser/podcastId/" + audio_file_name

    blob_response = vercel_blob.put(path=file_path,
        data=combined_audio_bytes,
        options={
            "addRandomSuffix": "false",
        })
    # print("blob response",    blob_response)
    
    # file_head = vercel_blob.head(file_path)
    # print('file head is', file_head)
    audio_url = vercel_blob_base + file_path

    db_insert(table_name="episodes", data={
        "podcast_id": 1, 
        "user_id": "testUser",
        "title": f"Daily Podcast for {date_as_text}", 
        "description": f"This is your daily podcast for {date_as_text}. It was created at {time_as_text}", 
        "file_name": audio_file_name,
        "url": audio_url,
        "duration": audio_duration,
        "script_text": podcast_response.model_dump_json(),
        "audio_generated": True,
    })
    rss_text = generate_rss_text()
    # write the rss to a file in the blob storage
    vercel_blob.put(path='/rss/testUser/podcastId/testRss.xml', data=rss_text, options={
                "addRandomSuffix": "false",
            })
    
    # send the rss as a response
    response = make_response(rss_text)
    response.headers.set('Content-Type', 'application/rss+xml')

    return response


 
@app.route('/api/new-script') 
def new_script():
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
    
    current_datetime_section = f" Today's date is {datetime_as_text}. "
    
    text_list = []
    voice_list = []

    podcast_response = message_ai_structured(directive 
                             + headlines_section_of_text_for_ai
                            #  + sports_section_of_text_for_ai
                             + tech_section_of_text_for_ai
                             + entertainment_section_of_text_for_ai 
                             + current_datetime_section
                             + fun_facts_section
                             + previous_eps_section
                            )
    try:
        podcast_script = podcast_response.script
    except Exception:
        print("error getting script from podcast:", podcast_response)
        raise Exception("Error getting script from podcast:", podcast_response) 

    # print("podcast script is", podcast_response.model_dump_json()) 

    for script_line in podcast_script:
        text_list.append(script_line.text)
        voice_list.append(script_line.voice.lower())
    

    db_insert(table_name="episodes", data={
        "podcast_id": 1, 
        "user_id": "testUser",
        "title": f"Daily Podcast for {date_as_text}", 
        "description": f"This is your daily podcast for {date_as_text}. It was created at {time_as_text}", 
        # "file_name": audio_file_name,
        # "url": audio_url,
        # "duration": audio_duration,
        "script_text": podcast_response.model_dump_json(),
        "audio_generated": False,
    })
    

    return "<p>Audio generated</p>"


@app.route("/api/make-audio-for-latest-ep")
def latest_ep_audio():
    latest_ep = get_last_n_episodes(1)[0]
    if (latest_ep.get("audio_generated")):
        # audio already generated
        raise Exception("audio already generated for this episode")

    text_list = []
    voice_list = []

    podcast_script = json.loads(latest_ep.get("script_text")).get("script")
    # print("podcast script is", podcast_script) 
    for script_line in podcast_script:
        text_list.append(script_line.get("text"))
        voice_list.append(script_line.get("voice").lower())
        
    audio_bytes = list(map(get_audio_bytes_from_text, text_list, voice_list))

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


    audio_file_name = "daily_update_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".mp3"
    file_path = "/audio/testUser/podcastId/" + audio_file_name

    blob_response = vercel_blob.put(path=file_path,
        data=combined_audio_bytes,
        options={
            "addRandomSuffix": "false",
        })
    
    audio_url = vercel_blob_base + file_path

    db_update(table_name="episodes", id=latest_ep.get("episode_id"), id_column_name="episode_id", data={
        "file_name": audio_file_name,
        "url": audio_url,
        "duration": audio_duration,
        "audio_generated": True,
    })

    # rss_text = generate_rss_text()
    # # write the rss to a file in the blob storage
    # vercel_blob.put(path='/rss/testUser/podcastId/testRss.xml', data=rss_text, options={
    #             "addRandomSuffix": "false",
    #         })
    
    # send the rss as a response
    # response = make_response(rss_text)
    # response.headers.set('Content-Type', 'application/rss+xml')

    return "<p>Episode audio generated</p>"
