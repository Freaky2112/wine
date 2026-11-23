
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    language = db.Column(db.String(2), default="fr")
    is_admin = db.Column(db.Boolean, nullable=False, default=False,
                         server_default=db.false())
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    wines = db.relationship("Wine", backref="owner",
                            cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Wine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"),
                        nullable=False)

    name = db.Column(db.String(180), nullable=False)
    producer = db.Column(db.String(180))
    country = db.Column(db.String(100))
    region = db.Column(db.String(120))
    appellation = db.Column(db.String(120))
    grape = db.Column(db.String(180))
    vintage = db.Column(db.Integer)
    wine_type = db.Column(db.String(30), default="red")
    alcohol = db.Column(db.Float)
    price = db.Column(db.Float)
    currency = db.Column(db.String(3), default="CAD")
    photo = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tastings = db.relationship(
        "Tasting",
        backref="wine",
        cascade="all, delete-orphan",
        order_by="Tasting.tasted_at.desc()"
    )


class Tasting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wine_id = db.Column(db.Integer, db.ForeignKey("wine.id"),
                        nullable=False)

    tasted_at = db.Column(db.DateTime, default=datetime.utcnow)
    score = db.Column(db.Integer, nullable=False)

    appearance = db.Column(db.Text)
    nose = db.Column(db.Text)
    palate = db.Column(db.Text)
    acidity = db.Column(db.String(30))
    tannins = db.Column(db.String(30))
    body = db.Column(db.String(30))
    finish = db.Column(db.Text)
    food_pairing = db.Column(db.Text)
    comments = db.Column(db.Text)

    def __repr__(self):
        return f"<Tasting {self.id}: {self.score}/100>"
