from datetime import datetime
from pytz import timezone

est_timezone = timezone('EST')

dt = datetime.now(est_timezone)
date_as_text = dt.strftime("%B %d, %Y")
time_as_text = dt.strftime("%H:%M")
datetime_as_text = date_as_text + " at " + time_as_text
weekday_as_text = dt.strftime("%A")

DELAY_BETWEEN_NEWS_FETCH = 0.51
NUM_ARTICLES_PER_CATEGORY = 3
PODCAST_LENGTH = "70 lines"


TEST = "test2"


voiceOptions = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

voice1 = "fable"
voice2 = "nova"

# directives
directive = f"""Create a podcast that is {PODCAST_LENGTH} long using these characters: "Samuel" and "Samantha". 
You are making a daily podcast that has a new episode every day. 
They should introduce themselves. As a podcast, it should be realistic, not fantastical. 
Your response should only be valid JSON. It should be a list of dictionaries. 
Each dictionary should contain 2 keys: "text" for what that character says and "voice" for which character is speaking. 
The voice for "Samuel" should be "{voice1}", and the voice for "Samantha" should be "{voice2}".
"{voice1}" and "{voice2}" are your only options for the contents of the "voice" field.
I will be putting your response directly into a json parser so don't add anything else other than valid json."""

directive_headlines = """ There should be a 'Headlines' section of the podcast.
    During this section, have the characters talk about these articles. 
    They are top headlines and the content of the article: """

directive_sports = """ There should be a 'Sports' section of the podcast.
    # During this section, have the characters talk about these articles. 
    # They are some latest sports articles: """

directive_tech = """ There should be a 'Tech' section of the podcast.
    During this section, have the characters talk about these articles. 
    They are some latest technology articles: """

directive_entertainment = """ There should be a 'Entertainment' section of the podcast.
    During this section, have the characters talk about these articles. 
    They are some latest entertainment articles: """

directive_previous_eps = """Here are the last few episodes. 
    Look at the scripts and try not to repeat things from previous episodes. 
    Also, feel free to make references to the things you talked about yesterday: """

directive_fun_facts = """ At the end there should be a Fun Fact section where they say something interesting or a fun fact about today. 
    Or they could mention something that happened on this day years ago.  """

directive_date = f""" Today's date is {weekday_as_text}, {datetime_as_text}. 
    Make sure you greet the listener at the start of the podcast. In your greeting mention the current day of the week and the date. 
    E.g. 'Today is Monday, June 1st, 2025. Happy Monday! 
    If today is a holiday, wish the listener a happy [holiday] or happy national [xyz] day."""

section_directives = {
    "headlines": directive_headlines,
    "sports": directive_sports,
    "tech": directive_tech,
    "entertainment": directive_entertainment,
    "previous_eps": directive_previous_eps,
    "fun_facts": directive_fun_facts,
    "date": directive_date,
}
