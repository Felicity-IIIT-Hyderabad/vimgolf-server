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


@app.route("/test")
def healthcheck():
    return "Hello World"


def validate_challenge_id(func):
    @functools.wraps(func)
    def wrapper(challenge_id):
        if challenge_id >= total_challenges or challenge_id < 0:
            return f"Not found challenge: {challenge_id}", 404
        return func(challenge_id)

    return wrapper


# in theory, I should be able to get a jwt token to work
# so that it can be used to submit via the CLI
def get_key(name, email):
    return f"key-{name}-{email}"


def setup_gui_route(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        filename, args = func(*args, **kwargs)
        name = "Gaurang"  # request.headers["X-Fname"]
        email = "gaurang.tandon@students.iiit.ac.in"  # request.headers["X-Email"]
        return render_template(filename, **args, name=name, apikey=get_key(name, email), logged_in=True)

    return wrapper


@app.route("/challenges/<int:challenge_id>")
@validate_challenge_id
@setup_gui_route
def challenge(challenge_id):
    data = CHALLENGE_DATA[challenge_id]

    return "challenge.html", {"intxt": data["in"], "out": data["out"], "title": data["title"], "desc": data["desc"]}


@app.route("/challenges/<int:challenge_id>.json")
@validate_challenge_id
def challenge_two(challenge_id):
    return CHALLENGE_DATA[challenge_id]


@app.route("/submit", methods=["POST"])
def submit():
    print(request)


@app.route("/")
@app.route("/view")
@setup_gui_route
def view():
    challenges = []

    for challenge_id, c_data in CHALLENGE_DATA.items():
        data = {"name": c_data["title"], "id": challenge_id, "best": 100}
        challenges.append(data)

    return "challenge_list.html", {"title": "List of Active Challenges", "challenges": challenges, "logged_in": False}


@app.route("/list")
def send_list():
    return CHALLENGE_DATA


@app.route("/challenges_leaderboard/<int:challenge_id>.json")
@validate_challenge_id
def get_leaderboard(challenge_id):
    return json.dumps([])


@app.route("/leaderboard")
@setup_gui_route
def leaderboard():
    leaders = [{"rank": 1, "username": "sigma_g", "score": 100, 'scores': [-100]},
               {"rank": 2, "username": "yoogottamk", "score": -100, "scores": [-100]}]
    cha_ids = list(range(total_challenges))
    return render_template("leaderboard.html", leaders=leaders, title="Global leaderboard", cha_ids=cha_ids)


setup()

if __name__ == "__main__":
    app.run(debug=True)
