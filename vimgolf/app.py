from distutils.dir_util import copy_tree
import datetime
import functools
import json
from collections import defaultdict
from operator import itemgetter
from os import getenv, listdir
from tempfile import mkdtemp

from flask import Flask, abort, render_template, request

from vimgolf.keys import IGNORED_KEYSTROKES, parse_keycodes
from vimgolf.models.models import Score
from vimgolf.models.orm import db
from vimgolf.utils import docker_init, get_scores

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = getenv(
    "SQLALCHEMY_DATABASE_URI", "sqlite:////tmp/vimrace.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)
db.create_all(app=app)

total_challenges = 0
CHALLENGE_PATH = "challenges/"
NUM_FILES_PER_CHALLENGE = 3  # in, out, desc
CHALLENGE_DATA = {}

d = docker_init()


def init_setup():
    global total_challenges
    challenge_files = listdir(CHALLENGE_PATH)

    for challenge_idx, _idx in enumerate(challenge_files):
        data = {}
        PREF = f"{CHALLENGE_PATH}/{challenge_idx}"

        file_names = listdir(PREF)
        assert len(file_names) % NUM_FILES_PER_CHALLENGE == 0

        with open(f"{PREF}/0.in") as f:
            data["in"] = f.read()
        with open(f"{PREF}/0.out") as f:
            data["out"] = f.read()
        with open(f"{PREF}/0.desc") as f:
            lines = f.readlines()
            data["title"] = lines[0].strip()
            data["desc"] = "\n".join(lines[1:]).strip()

        CHALLENGE_DATA[challenge_idx] = data


@app.route("/test")
def healthcheck():
    return "Hello World"


def is_valid_challenge_id(challenge_id):
    return challenge_id is not None and (
        int(challenge_id) < total_challenges or int(challenge_id) >= 0
    )


def validate_challenge_id(func):
    @functools.wraps(func)
    def wrapper(challenge_id):
        if is_valid_challenge_id(challenge_id):
            return func(challenge_id)
        return f"Not found challenge: {challenge_id}", 404

    return wrapper


def get_name_email_username(req):
    heads = req.headers
    return (
        heads["x-fname"] + heads["x-lname"],
        heads["x-email"],
        heads["x-username"],
    )


def setup_gui_route(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        filename, args = func(*args, **kwargs)
        name, email, username = get_name_email_username(request)
        return render_template(
            filename, **args, name=name, email=email, username=username, logged_in=True
        )

    return wrapper


@app.route("/challenges/<int:challenge_id>")
@validate_challenge_id
@setup_gui_route
def challenge(challenge_id):
    data = CHALLENGE_DATA[challenge_id]

    return "challenge.html", {
        "intxt": data["in"],
        "out": data["out"],
        "title": data["title"],
        "desc": data["desc"],
    }


@app.route("/challenges/<int:challenge_id>.json")
@validate_challenge_id
def challenge_two(challenge_id):
    return CHALLENGE_DATA[challenge_id]


def test_keystrokes(challenge_id, keystrokestring):
    global d

    tmpdir = mkdtemp()
    challenge_dir = f"{CHALLENGE_PATH}/{challenge_id}"
    copy_tree(challenge_dir, tmpdir)

    with open(f"{tmpdir}/solve", "wb") as solution:
        solution.write(keystrokestring)

    (corr, wrong), logs = get_scores(d, tmpdir)

    return corr > 0


def get_score_from_raw_keys(raw_keys):
    # list of parsed keycode byte strings
    keycodes = parse_keycodes(raw_keys)
    keycodes = [keycode for keycode in keycodes if keycode not in IGNORED_KEYSTROKES]

    score = len(keycodes)
    return score


# TODO:
# instead of keystrokestring, upload the vim -s file as a file to the server
# give yoogottam a temporary directory containing the submitted file
# he will pick up in and out from challenges directory
# yoogottam will give me a partial score (how many files gave `diff -w` exit code zero)
@app.route("/submit/<int:challenge_id>", methods=["POST"])
@validate_challenge_id
def submit(challenge_id):
    name, email, username = get_name_email_username(request)

    # this shouldn't really happen
    assert name is not None

    if "entry" not in request.form:
        return "Provide entry", 403

    raw_keys = request.form["entry"].encode("utf-8")

    if not raw_keys:
        return "No raw keys supplied", 403

    result = test_keystrokes(challenge_id, raw_keys)

    if not result:
        return "Invalid keystroke for given challenge id", 403

    score_value = get_score_from_raw_keys(raw_keys)
    exists = Score.query.filter(
        Score.useremail == email and Score.challenge_code == challenge_id
    ).first()

    if exists:
        if exists.keystrokes <= score_value:
            # content not modified
            return "Same or better score already exists", 304
        db.session.delete(exists)

    timestamp = datetime.datetime.now()
    new_score = Score(
        useralias=username,
        useremail=email,
        challenge_code=challenge_id,
        keystrokes=score_value,
        timestamp=timestamp,
    )
    db.session.add(new_score)
    db.session.commit()

    return "Sucess", 200


@app.route("/")
@app.route("/view")
@setup_gui_route
def view():
    name, email, username = get_name_email_username(request)
    global_rank, _scores = get_global_leaderboard_data(username)
    challenges = []

    for challenge_id, c_data in CHALLENGE_DATA.items():
        data = {"name": c_data["title"], "id": challenge_id, "best": 100}
        challenges.append(data)

    return "challenge_list.html", {
        "title": "List of Active Challenges",
        "challenges": challenges,
        "global_rank": str(global_rank),
    }


@app.route("/list")
def send_list():
    return CHALLENGE_DATA


@app.route("/challenges_leaderboard/<int:challenge_id>.json")
@validate_challenge_id
def get_leaderboard(challenge_id):
    return json.dumps(get_challenge_leaderboard_data(challenge_id))


def get_challenge_leaderboard_data(challenge_code):
    scores = Score.query.filter(Score.challenge_code == challenge_code).all()
    scores = sorted(scores, key=lambda score: score.keystrokes)
    return [{"alias": score.useralias, "score": score.keystrokes} for score in scores]


def get_global_leaderboard_data(specific_alias=None):
    scores = Score.query.all()
    countsolved = defaultdict(int)
    totalkeys = defaultdict(int)
    lasttimestamp = defaultdict(lambda: datetime.datetime(1970, 1, 1))
    usernames = set([])

    default_score_gen = lambda: ["-" for _ in range(total_challenges)]
    score_dict = defaultdict(default_score_gen)

    for score in scores:
        alias = score.useralias
        countsolved[alias] += 1
        totalkeys[alias] += score.keystrokes
        lasttimestamp[alias] = max(lasttimestamp[alias], score.timestamp)
        score_dict[alias][score.challenge_code] = str(score.keystrokes)
        usernames.add(alias)

    usernames = list(usernames)
    score_list = [
        ((-countsolved[alias], totalkeys[alias], lasttimestamp[alias]), alias)
        for alias in usernames
    ]

    score_list = sorted(score_list, key=itemgetter(0))

    leaders = []
    for rank, sorted_item in enumerate(score_list):
        alias = sorted_item[1]
        if specific_alias == alias:
            return rank, score_dict[alias]
        leaders.append(
            {
                "rank": rank,
                "username": alias,
                "score": totalkeys[alias],
                "solved": countsolved[alias],
                "timestamp": lasttimestamp[alias].strftime("%d %B %Y %I:%M%p"),
                "scores": score_dict[alias],
            }
        )

    if specific_alias is not None:
        return len(score_list), default_score_gen()

    return leaders


@app.route("/leaderboard")
@setup_gui_route
def leaderboard():
    cha_ids = list(range(total_challenges))
    leaders = get_global_leaderboard_data()
    return "leaderboard.html", {
        "leaders": leaders,
        "title": "Global leaderboard",
        "cha_ids": cha_ids,
    }


@app.route("/apikey")
@setup_gui_route
def apikey():
    authorization_key = "authorization"
    token = request.headers[authorization_key]

    return "apikey.html", {"apikey": token}


init_setup()

if __name__ == "__main__":
    app.run(debug=True)
