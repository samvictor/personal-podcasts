import os
from dotenv import load_dotenv
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, send_file

# Bark imports
# from bark import SAMPLE_RATE, generate_audio, preload_models
# from scipy.io.wavfile import write as write_wav

# import io
# import scipy.io.wavfile

# Load environment variables from .env.development.local file
env_path = Path('.') / '.env.development.local'
load_dotenv(dotenv_path=env_path)


# download and load all Bark models
# preload_models(
#     text_use_small=True,
#     coarse_use_small=True,
#     fine_use_small=True,
# )


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


# @app.route("/api/bark")
# def bark():
#     text_prompt = """
#         Hello, my name is Suno. And, uh — and I like pizza. [laughs] 
#         But I also have other interests such as playing tic tac toe.
#     """
#     audio_array = generate_audio(text_prompt)
#     # write_wav("output.wav", SAMPLE_RATE, audio_array)
#     # return send_file("output.wav")
    
#     # Convert the audio array to WAV format
#     wav_io = io.BytesIO()
#     scipy.io.wavfile.write(wav_io, samplerate, audio_array)
#     wav_io.seek(0)

#     # Create a Flask Response with the WAV data
#     return Response(wav_io.read(), mimetype="audio/wav")

