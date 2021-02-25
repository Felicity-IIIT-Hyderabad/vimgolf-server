from vimgolf.models.orm import db


class Score(db.Model):
    __tablename__ = "score"

    id = db.Column(db.Integer, primary_key=True)
    keystrokes = db.Column(db.Integer)
    useremail = db.Column(db.String(64))
    challenge_code = db.Column(db.Integer)
    useralias = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime)

    # @staticmethod
    # def __json__():
    #     return {
    #         "keystrokes": fields.String,
    #     }

    def __repr__(self):
        return f"{self.useralias} achieved a score of {self.keystrokes} on challenge {self.challenge_code}"
