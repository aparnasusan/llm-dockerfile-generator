import os

from flask import Flask

app = Flask(__name__)


@app.get("/")
def hello():
    return {"message": "Hello from Flask in Docker!"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
