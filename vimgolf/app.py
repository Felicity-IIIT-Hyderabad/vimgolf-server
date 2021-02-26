from distutils.dir_util import copy_tree
import datetime
import functools
import json
from collections import defaultdict
from operator import itemgetter
from os import getenv, listdir
from tempfile import mkdtemp
import re

from flask import Flask, render_template, request, url_for, redirect

from vimgolf.keys import IGNORED_KEYSTROKES, parse_keycodes
from vimgolf.models.models import Score
from vimgolf.models.orm import db
from vimgolf.utils import docker_init, get_scores

from flask_limiter import Limiter
from flask_limiter.util import get_ipaddr

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = getenv(
    "SQLALCHEMY_DATABASE_URI", "sqlite:////tmp/vimrace.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)
db.create_all(app=app)
limiter = Limiter(app, key_func=get_ipaddr)

total_challenges = 0
CHALLENGE_PATH = "challenges"
NUM_FILES_PER_CHALLENGE = 3  # in, out, desc
CHALLENGE_DATA = {}

d = docker_init()


def init_setup():
    global total_challenges
    challenge_files = listdir(CHALLENGE_PATH)
    total_challenges = len(challenge_files)

    for challenge_idx, _idx in enumerate(challenge_files):
        data = {}
        PREF = f"{CHALLENGE_PATH}/{challenge_idx}"

        with open(f"{PREF}/0.in") as f:
            data["in"] = f.read()
        with open(f"{PREF}/0.out") as f:
            data["out"] = f.read()
        with open(f"{PREF}/desc") as f:
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
        heads.get("x-fname", "yay") + " " + heads.get("x-lname", "boo"),
        heads.get("x-email", "yay@boo"),
        heads.get("x-username", "yay.boo"),
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

    desc_parsed = data["desc"].replace("\n", "<br>")
    # desc_parsed = re.sub("(<br>){3,}", "<br><br>", desc_parsed)
    desc_parsed = re.sub("(<br>)+", "<br>", desc_parsed)

    return "challenge.html", {
        "intxt": data["in"],
        "out": data["out"],
        "title": data["title"],
        "desc": desc_parsed
    }


@app.route("/challenges/<int:challenge_id>.json")
@validate_challenge_id
def challenge_two(challenge_id):
    return json.dumps(CHALLENGE_DATA[challenge_id])


def test_keystrokes(challenge_id, keystrokestring):
    global d

    tmpdir = mkdtemp()
    challenge_dir = f"{CHALLENGE_PATH}/{challenge_id}"
    copy_tree(challenge_dir, tmpdir)

    with open(f"{tmpdir}/solve", "wb") as solution:
        solution.write(keystrokestring)

    (corr, wrong), logs = get_scores(d, tmpdir)

    return corr > 0, logs


def get_score_from_raw_keys(raw_keys):
    # list of parsed keycode byte strings
    keycodes = parse_keycodes(raw_keys)
    keycodes = [keycode for keycode in keycodes if keycode not in IGNORED_KEYSTROKES]

    score = len(keycodes)
    return score


@app.route("/submit/<int:challenge_id>", methods=["POST"])
@limiter.limit("1 per minute")
@validate_challenge_id
def submit(challenge_id):
    with open("x", "a") as f:
        f.write(f"!{challenge_id}\n")

    name, email, username = get_name_email_username(request)

    # this shouldn't really happen
    assert name is not None

    with open("x", "a") as f:
        f.write(f"!{challenge_id}\n")

    if "entry" not in request.form:
        return "Provide entry", 403

    raw_keys = request.form["entry"].encode("utf-8")

    with open("x", "a") as f:
        f.write(f"!{challenge_id}\n")

    if not raw_keys:
        return "No raw keys supplied", 403

    result, logs = test_keystrokes(challenge_id, raw_keys)
    with open("x", "a") as f:
        f.write(f"!{challenge_id}\n")

    if not result:
        return f"Invalid keystroke for given challenge id\n", 403

    score_value = get_score_from_raw_keys(raw_keys)
    exists = Score.query.filter(
        Score.useremail == email and Score.challenge_code == challenge_id
    ).first()

    if exists:
        with open("x", "a") as f:
            f.write(f"{exists}, {exists.keystrokes}, {challenge_id}, {email}\n")
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


GOD_MODE = [
    "gaurang.tandon@students.iiit.ac.in",
    "yoogottam.khandelwal@students.iiit.ac.in",
    "kunwar.shaanjeet@students.iiit.ac.in",
]


@app.before_request
def before_request():
    name, email, username = get_name_email_username(request)

    if email in GOD_MODE:
        return None

    if request.path == "home" or request.path == "/":
        return None

    is_iiith = request.headers.get("x-iiith", "1")
    if int(is_iiith) != 1:
        return redirect(url_for("homepage"))

    curr_time = datetime.datetime.now()
    start_time = datetime.datetime(2021, 1, 25, 12, 00, 00)

    if curr_time < start_time:
        return redirect(url_for("homepage"))


@app.errorhandler(404)
def give_error(_):
    return render_template("404.html")


@app.route("/home")
@app.route("/")
@setup_gui_route
def homepage():
    return "rules.html", {"title": "Home for IIITH VimGolf'21"}


@app.route("/challenges")
@limiter.limit("10 per minute")
@setup_gui_route
def view():
    name, email, username = get_name_email_username(request)
    global_rank, _ = get_global_leaderboard_data(username)
    challenges = []

    for challenge_id, c_data in CHALLENGE_DATA.items():
        data = {"name": c_data["title"], "id": challenge_id,
                "my": get_best_score(challenge_id, username), "best": get_best_score(challenge_id)}
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
@limiter.limit("10 per minute")
@validate_challenge_id
def get_leaderboard(challenge_id):
    return json.dumps(get_challenge_leaderboard_data(challenge_id))


def get_challenge_leaderboard_data(challenge_code):
    scores = Score.query.filter(Score.challenge_code == challenge_code).all()
    scores = sorted(scores, key=lambda score: score.keystrokes)
    return [{"alias": score.useralias, "score": score.keystrokes} for score in scores]


def get_best_score(challenge_id, alias=None):
    if alias:
        with open("y", "a") as f:
            f.write(f"!{alias} {challenge_id}\n")
            res = Score.query.filter(Score.challenge_code == challenge_id, Score.useralias == alias).all()
            for uu in res:
                f.write(f"{uu}\n")
            f.write(f"!{alias} {challenge_id}\n")
        if res:
            return res[0].keystrokes
        else:
            return -1

    res = Score.query.filter(Score.challenge_code == challenge_id).all()

    INF = int(1e10)
    least_keystrokes = INF

    for x in res:
        least_keystrokes = min(x.keystrokes, least_keystrokes)

    if least_keystrokes == INF:
        least_keystrokes = -1

    return least_keystrokes


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
@limiter.limit("10 per minute")
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

    return "apikey.html", {"apikey": token, "title": "Private apikey"}


init_setup()

if __name__ == "__main__":
    app.run(debug=True)
