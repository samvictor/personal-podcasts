# Welcome to Cloud Functions for Firebase for Python!
# To get started, simply uncomment the below code or create your own.
# Deploy with `firebase deploy`

from firebase_functions import https_fn
from firebase_admin import initialize_app
from firebase_functions.params import SecretParam

testSecret = SecretParam('TEST_SECRET')

initialize_app()


@https_fn.on_request(secrets=[testSecret])
def on_request_example(req: https_fn.Request) -> https_fn.Response:
    return https_fn.Response("Hello world! Secret is: " + testSecret.value)