from flask import Flask, request, render_template, abort
import functools
from os import listdir, getenv
import json
from server.models.orm import db
from server.models.models import Score
from collections import defaultdict
from operator import itemgetter
from server.keys import get_keycode_repr, parse_keycodes, IGNORED_KEYSTROKES

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


def init_setup():
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


def is_valid_challenge_id(challenge_id):
    return challenge_id >= total_challenges or challenge_id < 0


def validate_challenge_id(func):
    @functools.wraps(func)
    def wrapper(challenge_id):
        if is_valid_challenge_id(challenge_id):
            return func(challenge_id)
        return f"Not found challenge: {challenge_id}", 404

    return wrapper


# in theory, I should be able to get a jwt token to work
# so that it can be used to submit via the CLI
def get_key(name, email):
    return f"key-{name}-{email}"


def get_name_email(req):
    name_key = "X-Fname"
    email_key = "X-Email"
    heads = req.headers
    if name_key not in heads or email_key not in heads:
        return None, None
    return heads[name_key], heads[email_key]


def setup_gui_route(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        filename, args = func(*args, **kwargs)
        name = "Gaurang"
        email = "gaurang.tandon@students.iiit.ac.in"
        # name, email = get_name_email(request)
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


def test_keystrokes(challenge_id, keystrokestring):
    return True


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
@app.route("/submit", methods=["POST"])
def submit():
    name, email = get_name_email(request)

    # this shouldn't really happen
    if name is None:
        abort(403, "User not logged in")

    raw_keys = request.args.get("entry")
    challenge_code = request.args.get('challenge_id')

    if not is_valid_challenge_id(challenge_code):
        abort(403, "Invalid challenge id")

    result = test_keystrokes(challenge_code, raw_keys)

    if not result:
        abort(403, "Invalid keystroke for given challenge id")

    score_value = get_score_from_raw_keys(raw_keys)
    exists = Score.query.filter(Score.email == email and Score.challenge_code == challenge_code).first()

    if exists:
        db.session.delete(exists)

    new_score = Score(useralias=name, useremail=email, challenge_code=challenge_code, keystrokes=score_value)
    db.session.add(new_score)
    db.session.commit()

    return 200


@app.route("/")
@app.route("/view")
@setup_gui_route
def view():
    challenges = []

    for challenge_id, c_data in CHALLENGE_DATA.items():
        data = {"name": c_data["title"], "id": challenge_id, "best": 100}
        challenges.append(data)

    return "challenge_list.html", {"title": "List of Active Challenges", "challenges": challenges}


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


def get_global_leaderboard_data():
    scores = Score.query.all()
    countsolved = defaultdict(int)
    totalkeys = defaultdict(int)
    usernames = set([])

    for score in scores:
        countsolved[score.useralias] += 1
        totalkeys[score.useralias] += score.keystrokes
        usernames.add(score.useralias)

    usernames = list(usernames)
    score_list = [((-countsolved[alias], totalkeys[alias]), alias) for alias in usernames]

    score_list = sorted(score_list, key=itemgetter(0))

    leaders = []
    for rank, sorted_item in enumerate(score_list):
        alias = sorted_item[1]
        leaders.append({"rank": rank, "username": alias, "score": totalkeys[alias], "solved": countsolved[alias]})

    return leaders


@app.route("/leaderboard")
@setup_gui_route
def leaderboard():
    cha_ids = list(range(total_challenges))
    leaders = get_global_leaderboard_data()
    return render_template("leaderboard.html", leaders=leaders, title="Global leaderboard", cha_ids=cha_ids)


init_setup()

if __name__ == "__main__":
    app.run(debug=True)
