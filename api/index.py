import os
from dotenv import load_dotenv
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, send_file, Response, make_response
from feedgen.feed import FeedGenerator
import io

# Load environment variables from .env.development.local file
env_path = Path('.') / '.env.development.local'
load_dotenv(dotenv_path=env_path)

import vercel_blob
blob_key = os.environ.get('BLOB_READ_WRITE_TOKEN')

from openai import OpenAI
openai_key = os.environ.get('OPENAI_KEY')
client = OpenAI(api_key=openai_key)

app = Flask(__name__)

def get_db_connection():
    print("\033[94mEnvironment variables:\033[0m")
    print(f"POSTGRES_URL_NON_POOLING: {os.environ.get('POSTGRES_URL_NON_POOLING')}")
    print(f"POSTGRES_HOST: {os.environ.get('POSTGRES_HOST')}")
    print(f"POSTGRES_DATABASE: {os.environ.get('POSTGRES_DATABASE')}")
    print(f"POSTGRES_USER: {os.environ.get('POSTGRES_USER')}")
    print(f"POSTGRES_PASSWORD: {os.environ.get('POSTGRES_PASSWORD')}")
    
    db_url = os.environ.get("POSTGRES_URL_NON_POOLING")
    if not db_url:
        raise ValueError("POSTGRES_URL_NON_POOLING environment variable is not set")
    
    print(f"\033[94mUsing database URL: {db_url}\033[0m")
    try:
        connection = psycopg2.connect(db_url)
        return connection
    except Exception as e:
        print(f"\033[91mError connecting to database: {str(e)}\033[0m")
        return None

@app.route("/api/podcasts")
def get_podcasts():
    connection = get_db_connection()
    if connection:
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('SELECT * FROM podcasts;')
                result = cursor.fetchall()
                for row in result:
                    print(row)
                return jsonify(result)
        finally:
            connection.close()
    else:
        return jsonify({"error": "Unable to connect to the database"}), 500

@app.route("/api/python")
def hello_world():
    return "<p>Hello, World!</p>"

@app.route("/api/apiExample")
def api_example():
    return {"message": "Hello from Flask!"}

@app.route("/api/speech")
def get_speech():
    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input="Today is a wonderful day to build something people love!"
    )
    
    audio_content = io.BytesIO(response.content)
    audio_content.seek(0)
    
    return Response(audio_content, mimetype="audio/mpeg")


@app.route('/api/blob')
def blob():
    blobFiles = vercel_blob.list().get('blobs')
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
        if file.get('size') > 0:
            fe = fg.add_entry()
            fe.title(file.get('pathname'))
            fe.enclosure(url=file.get('url'), length=file.get('size'), type=file.get('contentType'))
            fe.pubDate(file.get('uploadedAt'))
            fe.link(href=file.get('url'))
            fe.guid(file.get('url'), permalink=True) 
            # fe.description(file.description)
            # fe.author(name=file.author.name, email=file.author.email)

    # write the rss to a file in the blob storage
    vercel_blob.put(path='/rss/testUser/testRss.xml', data=fg.rss_str(pretty=True))

    # send the rss as a response
    response = make_response(fg.rss_str(pretty=True))
    response.headers.set('Content-Type', 'application/rss+xml')

    return response

@app.route('/api/cron')
def cron():
    print('cron job running')
    return jsonify({'message': 'Cron job executed successfully'})
