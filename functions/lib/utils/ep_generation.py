# functions specifically used for generating an episode
import json

from lib.constants.global_constants import directive, directive_entertainment, directive_fun_facts 
from lib.constants.global_constants import directive_headlines, directive_previous_eps, directive_tech
from lib.constants.global_constants import datetime_as_text, date_as_text, time_as_text

from lib.utils.utility_functions import get_full_content_from_rss, get_last_n_episodes, get_audio_bytes_from_text

def build_full_directive(): 
    headline_articles = get_full_content_from_rss('https://abcnews.go.com/abcnews/topstories') 

    headlines_section_of_text_for_ai = directive_headlines
    for this_article in headline_articles:
        headlines_section_of_text_for_ai += f"Title: {this_article.get("title")}, Content: {this_article.get("content")}. "
    
    
    # sports_articles = get_full_content_from_rss('https://abcnews.go.com/abcnews/sportsheadlines') 

    # sports_section_of_text_for_ai = directive_sports
    # for this_article in sports_articles:
    #     sports_section_of_text_for_ai += f"Title: {this_article.get("title")}, Content: {this_article.get("content")}. "
    
    
    tech_articles = get_full_content_from_rss('https://abcnews.go.com/abcnews/technologyheadlines') 

    tech_section_of_text_for_ai = directive_tech
    for this_article in tech_articles:
        tech_section_of_text_for_ai += f"Title: {this_article.get("title")}, Content: {this_article.get("content")}. "
    
    
    entertainment_articles = get_full_content_from_rss('https://abcnews.go.com/abcnews/entertainmentheadlines') 

    entertainment_section_of_text_for_ai = directive_entertainment
    for this_article in entertainment_articles:
        entertainment_section_of_text_for_ai += f"Title: {this_article.get("title")}, Content: {this_article.get("content")}. "
    


    previous_eps = get_last_n_episodes(5)
    # trimming eps to help ai focus on important content
    trimmed_eps = [{
        "created_at": this_ep.get("created_at"), 
        "script_text": this_ep.get("script_text")
        } for this_ep in previous_eps]
    previous_eps_as_text = json.dumps(trimmed_eps, default=str)
    previous_eps_section = directive_previous_eps + previous_eps_as_text

    fun_facts_section = directive_fun_facts
    
    
    current_datetime_section = f" Today's date is {datetime_as_text}. "

    return (directive 
                    + headlines_section_of_text_for_ai
                    #  + sports_section_of_text_for_ai
                    + tech_section_of_text_for_ai
                    + entertainment_section_of_text_for_ai 
                    + current_datetime_section
                    + fun_facts_section
                    + previous_eps_section)



# take podcast script (list of podcast lines with voices)
# generate audio for lines individually
# combine individual audio segments into full podcast
# returns list of audio bytes
def get_audio_from_script(podcast_script, openai_client):
    audio_bytes = []
    for script_line in podcast_script:
        audio_bytes.append(get_audio_bytes_from_text(openai_client=openai_client, 
                            text=script_line.text,
                            voice=script_line.voice.lower()))

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

    return combined_audio_bytes


def upload_audio(combined_audio_bytes, bucket): 
    
    audio_file_name = "daily_update_" + date_as_text + "_" + time_as_text + ".wav"
    file_path = "audio/testUser/podcastId/" + audio_file_name

    
    blob = bucket.blob(file_path)
    
    # Upload the audio bytes
    blob.upload_from_string(combined_audio_bytes, content_type="audio/wav") 
    blob.make_public()

    audio_url = blob.public_url

    return {"file_name": audio_file_name, "url": audio_url}