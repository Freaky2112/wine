
import os
from flask import Flask, render_template, request, redirect
from flask import url_for, flash, session, Response, abort
from flask_login import LoginManager, login_user, logout_user
from flask_login import login_required, current_user
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, inspect, text
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError
from io import StringIO
import csv
import uuid
import functools
import click

from models import db, User, Wine, Tasting
from translations import TRANSLATIONS

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.environ.get(
    "UPLOAD_FOLDER", "static/uploads"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

db.init_app(app)
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def tr(key):
    lang = session.get(
        "language",
        current_user.language if current_user.is_authenticated else "fr"
    )
    return TRANSLATIONS.get(lang, TRANSLATIONS["fr"]).get(key, key)


@app.context_processor
def inject_translations():
    lang = session.get(
        "language",
        current_user.language if current_user.is_authenticated else "fr"
    )
    return {
        "t": TRANSLATIONS.get(lang, TRANSLATIONS["fr"]),
        "lang": lang
    }


@app.route("/language/<language>")
@login_required
def change_language(language):
    if language not in ("en", "fr"):
        abort(404)
    current_user.language = language
    db.session.commit()
    session["language"] = language
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/")
@login_required
def dashboard():
    wines = Wine.query.filter_by(user_id=current_user.id).all()

    count = len(wines)
    avg = db.session.query(func.avg(Tasting.score)).join(
        Wine, Tasting.wine_id == Wine.id
    ).filter(Wine.user_id == current_user.id).scalar()

    recent = Tasting.query.join(Wine).filter(
        Wine.user_id == current_user.id
    ).order_by(Tasting.tasted_at.desc()).limit(5).all()

    return render_template(
        "dashboard.html",
        count=count,
        average=round(avg or 0, 1),
        recent=recent,
        wines=wines
    )


def admin_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        language = request.form.get("language", "fr")
        make_admin = request.form.get("is_admin") == "on"
        if language not in ("en", "fr"):
            language = "fr"

        if len(username) < 3 or len(username) > 80:
            flash(tr("msg_username_len"))
        elif "@" not in email or len(email) > 180:
            flash(tr("msg_bad_email"))
        elif len(password) < 12:
            flash(tr("msg_password_len"))
        elif User.query.filter(
            db.or_(User.username == username, User.email == email)
        ).first():
            flash(tr("msg_user_exists"))
        else:
            user = User(username=username, email=email,
                        language=language, is_admin=make_admin)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(tr("msg_user_created"))
        return redirect(url_for("admin_users"))

    users = User.query.order_by(User.created_at).all()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@admin_required
def admin_toggle_role(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == current_user.id:
        flash(tr("msg_self_role"))
    else:
        user.is_admin = not user.is_admin
        db.session.commit()
        flash(tr("msg_role_updated"))
    return redirect(url_for("admin_users"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            session["language"] = user.language
            return redirect(url_for("dashboard"))

        flash(tr("msg_bad_login"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("login"))


def owned_wine(wine_id):
    wine = Wine.query.filter_by(
        id=wine_id,
        user_id=current_user.id
    ).first_or_404()
    return wine


@app.route("/wines")
@login_required
def wines():
    search = request.args.get("q", "").strip()

    query = Wine.query.filter_by(user_id=current_user.id)

    if search:
        query = query.filter(
            db.or_(
                Wine.name.ilike(f"%{search}%"),
                Wine.producer.ilike(f"%{search}%"),
                Wine.region.ilike(f"%{search}%"),
                Wine.country.ilike(f"%{search}%"),
                Wine.grape.ilike(f"%{search}%")
            )
        )

    results = query.order_by(Wine.created_at.desc()).all()

    return render_template("wines.html", wines=results, search=search)


@app.route("/wine/add", methods=["GET", "POST"])
@login_required
def add_wine():
    if request.method == "POST":
        wine = Wine(
            user_id=current_user.id,
            name=request.form.get("name", "").strip(),
            producer=request.form.get("producer", "").strip(),
            country=request.form.get("country", "").strip(),
            region=request.form.get("region", "").strip(),
            grape=request.form.get("grape", "").strip(),
            appellation=request.form.get("appellation", "").strip(),
            vintage=request.form.get("vintage") or None,
            wine_type=request.form.get("wine_type", "red"),
            alcohol=request.form.get("alcohol") or None,
            price=request.form.get("price") or None,
            currency=request.form.get("currency", "CAD")
        )

        if not wine.name:
            flash(tr("msg_name_required"))
            return render_template("wine_form.html", wine=None)

        db.session.add(wine)
        db.session.commit()

        flash(tr("msg_wine_added"))
        return redirect(url_for("wine_detail", wine_id=wine.id))

    return render_template("wine_form.html", wine=None)


@app.route("/wine/<int:wine_id>")
@login_required
def wine_detail(wine_id):
    wine = owned_wine(wine_id)
    return render_template("wine_detail.html", wine=wine)


@app.route("/wine/<int:wine_id>/tasting", methods=["POST"])
@login_required
def add_tasting(wine_id):
    wine = owned_wine(wine_id)

    try:
        score = int(request.form.get("score", ""))
    except ValueError:
        abort(400)

    if not 0 <= score <= 100:
        abort(400)

    tasting = Tasting(
        wine_id=wine.id,
        score=score,
        appearance=request.form.get("appearance", ""),
        nose=request.form.get("nose", ""),
        palate=request.form.get("palate", ""),
        acidity=request.form.get("acidity", ""),
        tannins=request.form.get("tannins", ""),
        body=request.form.get("body", ""),
        finish=request.form.get("finish", ""),
        food_pairing=request.form.get("food_pairing", ""),
        comments=request.form.get("comments", "")
    )

    db.session.add(tasting)
    db.session.commit()

    flash(tr("msg_tasting_saved"))
    return redirect(url_for("wine_detail", wine_id=wine.id))


@app.route("/export")
@login_required
def export_csv():
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Wine", "Producer", "Country", "Region", "Grape",
        "Vintage", "Type", "Tasting date", "Score",
        "Appearance", "Nose", "Palate", "Finish", "Comments"
    ])

    tastings = Tasting.query.join(Wine).filter(
        Wine.user_id == current_user.id
    ).order_by(Tasting.tasted_at.desc()).all()

    for tasting in tastings:
        wine = tasting.wine
        writer.writerow([
            wine.name, wine.producer, wine.country, wine.region,
            wine.grape, wine.vintage, wine.wine_type,
            tasting.tasted_at, tasting.score,
            tasting.appearance, tasting.nose, tasting.palate,
            tasting.finish, tasting.comments
        ])

    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                "attachment; filename=wine-journal.csv"
        }
    )


@app.route("/wine/<int:wine_id>/photo", methods=["POST"])
@login_required
def upload_photo(wine_id):
    wine = owned_wine(wine_id)
    photo = request.files.get("photo")

    if not photo or not photo.filename:
        flash(tr("msg_select_photo"))
        return redirect(url_for("wine_detail", wine_id=wine.id))

    try:
        image = Image.open(photo.stream)
        image.verify()
        photo.stream.seek(0)

        image = Image.open(photo.stream).convert("RGB")
        image.thumbnail((1600, 1600))

        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        filename = f"{uuid.uuid4().hex}.jpg"
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image.save(path, "JPEG", quality=85)

    except (UnidentifiedImageError, OSError, ValueError):
        flash(tr("msg_bad_image"))
        return redirect(url_for("wine_detail", wine_id=wine.id))

    wine.photo = filename
    db.session.commit()

    flash(tr("msg_photo_uploaded"))
    return redirect(url_for("wine_detail", wine_id=wine.id))


def ensure_admin_column():
    cols = [c["name"] for c in inspect(db.engine).get_columns("user")]
    if "is_admin" not in cols:
        try:
            with db.engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE `user` ADD COLUMN is_admin "
                    "BOOLEAN NOT NULL DEFAULT 0"
                ))
        except Exception:
            db.session.rollback()  # another worker added it first


def bootstrap_admin():
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    if not email:
        app.logger.warning(
            "ADMIN_EMAIL is not set: no admin can create users."
        )
        return
    try:
        user = User.query.filter_by(email=email).first()
        if user:
            if not user.is_admin:
                user.is_admin = True
                db.session.commit()
            return
        username = os.environ.get("ADMIN_USERNAME", "admin").strip()
        password = os.environ.get("ADMIN_PASSWORD", "")
        if User.query.filter_by(username=username).first():
            app.logger.warning(
                "Username %r already exists with another email. Run: "
                "flask --app run create-admin %s --username %s",
                username, email, username
            )
            return
        if len(password) < 12:
            app.logger.warning(
                "ADMIN_EMAIL has no account yet: set ADMIN_PASSWORD "
                "(12+ characters) to create it."
            )
            return
        user = User(username=username, email=email, is_admin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        app.logger.warning("Admin account created for %s", email)
    except IntegrityError:
        db.session.rollback()  # another worker created it first


@app.cli.command("create-admin")
@click.argument("email")
@click.option("--username", default="admin", show_default=True)
@click.password_option()
def create_admin(email, username, password):
    """Create an admin, or reset the password of an existing one."""
    email = email.strip().lower()
    if len(password) < 12:
        raise click.ClickException("Password must be at least 12 characters.")
    username = username.strip()
    user = (User.query.filter_by(email=email).first()
            or User.query.filter_by(username=username).first())
    if user is None:
        user = User(username=username, email=email)
        db.session.add(user)
    elif user.email != email:
        click.echo(f"Existing account '{user.username}' "
                   f"({user.email}) now uses {email}.")
        user.email = email
    user.is_admin = True
    user.set_password(password)
    db.session.commit()
    click.echo(f"Admin ready: {email}")


with app.app_context():
    db.create_all()
    ensure_admin_column()
    bootstrap_admin()
