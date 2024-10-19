import os
from dotenv import load_dotenv
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from flask import Flask, jsonify, send_file, Response, make_response
from feedgen.feed import FeedGenerator
from io import BytesIO
import json
import time
import datetime
from pydub import AudioSegment

# Load environment variables from .env.development.local file
env_path = Path('.') / '.env.development.local'
load_dotenv(dotenv_path=env_path)

import vercel_blob
blob_key = os.environ.get('BLOB_READ_WRITE_TOKEN')

from openai import OpenAI
openai_key = os.environ.get('OPENAI_KEY')
client = OpenAI(api_key=openai_key)

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
        return None;
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('SELECT * FROM podcasts;')
            result = cursor.fetchall()
            for row in result:
                print(row)
            cursor.close()
            return jsonify(result)
    finally:
        connection.close()

table_name_options = ["podcasts", "users", "episodes"]
key_options = {
    "podcasts": ["user_id", "title", "description", 
                    "ai_directives_by_section", "rss_url", "cover_image_url"],
    "episodes": ["cover_image_url", "podcast_id", "user_id", "title", "description", 
                    "file_name", "url", "duration"],
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
    response = client.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text
    )
    
    audio_content = BytesIO(response.content)
    # audio_content.seek(0)
    # return audio_content.read()
    return audio_content


def generate_rss_text():
    blobFiles = vercel_blob.list({"prefix": "audio/"}).get('blobs')
    print('response is', blobFiles)
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
            fe = fg.add_entry()
            fe.title(file.get('pathname'))
            fe.enclosure(url=file.get('url'), length=file.get('size'), type=file.get('contentType'))
            fe.pubDate(file.get('uploadedAt'))
            fe.link(href=file.get('url'))
            fe.guid(file.get('url'), permalink=True)  
            # fe.description(file.description)
            # fe.author(name=file.author.name, email=file.author.email)
    return fg.rss_str(pretty=True)

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
    ).getvalue()    
    vercel_blob.put(path='/audio/testUser/podcastId/testAudio.mp3',
        data=audio_bytes,
        options={
            "addRandomSuffix": "false",
        })
    return "<p>Audio saved!</p>"


@app.route('/api/blob')
def blob():
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

@app.route('/api/update-test')
def update_test():
    alloy_audio_content = get_audio_bytes_from_text(
        text="Hello, my name is Alloy. Nice to meet you!",
        voice="alloy"
    )

    shimmer_audio_content = get_audio_bytes_from_text(
        text="Hi, I'm Shimmer. Nice to meet you, too!",
        voice="shimmer"
    )
    
    alloy_segment = AudioSegment.from_file(alloy_audio_content, format='mp3')  # Change format if necessary
    shimmer_segment = AudioSegment.from_file(shimmer_audio_content, format='mp3')
    combined_segment = alloy_segment + shimmer_segment

    combined_audio_bytes = BytesIO()
    combined_segment.export(combined_audio_bytes, format='mp3')

    combined_audio_data = combined_audio_bytes.getvalue()
    audio_duration = combined_audio_bytes.duration_seconds

    audio_file_name = "daily_update_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".mp3"
    file_path = "/audio/testUser/podcastId/" + audio_file_name
    vercel_blob.put(path=file_path,
        data=audio_bytes,
        options={
            "addRandomSuffix": "false",
        })
    audio_url = vercel_blob_base + file_path

    month_as_text = datetime.date.today().strftime("/B")
    date_as_text = month_as_text + " " + time.strftime(" %d, %Y")
    time_as_text = time.strftime("%H:%M")
    db_insert(table_name="episodes", data={
        "podcast_id": 1, 
        "title": "Daily Podcast for {date_as_text}", 
        "description": "This is your daily podcast for {date_as_text}. It was created at {time_as_text}", 
        "file_name": audio_file_name,
        "url": audio_url,
        "duration": duration,
    })
    rss_text = generate_rss_text()
    # write the rss to a file in the blob storage
    vercel_blob.put(path='/rss/testUser/testRss.xml', data=rss_text, options={
                "addRandomSuffix": "false",
            })
