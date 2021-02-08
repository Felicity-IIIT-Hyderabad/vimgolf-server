from flask import Flask, request, render_template
import re
import functools
from os import listdir
import json

app = Flask(__name__)

total_challenges = 0
CHALLENGE_PATH = "challenges/"
NUM_FILES_PER_CHALLENGE = 3  # in, out, desc
CHALLENGE_DATA = {}


def setup():
    global total_challenges
    challenge_files = listdir(CHALLENGE_PATH)
    file_count = len(challenge_files)
    assert (file_count % NUM_FILES_PER_CHALLENGE == 0)
    total_challenges = file_count // NUM_FILES_PER_CHALLENGE

    for challenge_idx in range(total_challenges):
        data = {}
        PREF = f"{CHALLENGE_PATH}{challenge_idx}"

        with open(f"{PREF}.in") as f:
            data["in"] = f.read()
        with open(f"{PREF}.out") as f:
            data["out"] = f.read()
        with open(f"{PREF}.desc") as f:
            lines = f.readlines()
            data["title"] = lines[0].strip()
            data["desc"] = "\n".join(lines[1:]).strip()

        CHALLENGE_DATA[challenge_idx] = data


@app.route("/")
def healthcheck():
    return "Hello World"


def validate_challenge_id(func):
    @functools.wraps(func)
    def wrapper(challenge_id):
        if challenge_id >= total_challenges or challenge_id < 0:
            return f"Not found challenge: {challenge_id}", 404
        return func(challenge_id)

    return wrapper


@app.route("/challenges/<int:challenge_id>")
@validate_challenge_id
def challenge(challenge_id):
    data = CHALLENGE_DATA[challenge_id]

    # how to display monospaced text in jinja?
    # keys = ["out", "desc", "in"]
    # for key in keys:
    #     data[key] = re.sub("\n", "<br>", data[key])
    # data["out"] = f"<code>\n{data['out']}</code>"

    return render_template("challenge.html", intxt=data["in"], out=data["out"], title=data["title"], desc=data["desc"])


@app.route("/challenges/<int:challenge_id>.json")
@validate_challenge_id
def challenge_two(challenge_id):
    return CHALLENGE_DATA[challenge_id]


@app.route("/submit", methods=["POST"])
def submit():
    print(request)


@app.route("/view")
def view():
    return render_template("challenge_list.html")


@app.route("/list")
def send_list():
    return CHALLENGE_DATA


@app.route("/challenges_leaderboard/<int:challenge_id>.json")
@validate_challenge_id
def get_leaderboard(challenge_id):
    return json.dumps([])


@app.route("/leaderboard")
def leaderboard():
    return render_template("leaderboard.html")


setup()
