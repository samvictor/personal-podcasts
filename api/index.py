from flask import Flask
app = Flask(__name__)

@app.route("/api/python")
def hello_world():
    return "<p>Hello, World!</p>"

@app.route("/api/apiExample")
def api_example():
    return {"message": "Hello from Flask!"}