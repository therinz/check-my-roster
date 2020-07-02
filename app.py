import os

from flask import Flask, render_template, send_from_directory, redirect, url_for
from flask_wtf import FlaskForm
from werkzeug.utils import secure_filename
from wtforms import SubmitField
from flask_wtf.file import FileField, FileRequired, FileAllowed
from flask_uploads import configure_uploads, UploadSet

from process import ParseRoster, read_html, only_count


app = Flask(__name__)

app.config["SECRET_KEY"] = "b5dee181aca93daa90cbe38a0791d175"
app.config["UPLOADED_HTML_DEST"] = "uploads"

allowed_types = UploadSet("html", ("html", "htm"))
configure_uploads(app, allowed_types)


class UploadForm(FlaskForm):
    roster = FileField("HTML file", validators=[
        FileRequired(),
        FileAllowed(allowed_types, "Only HTML files")
    ])
    submit = SubmitField("Upload file")


@app.route('/', methods=["GET", "POST"])
def home():
    """Ask user to upload roster file and present processed results"""

    form = UploadForm()

    # User submitted roster via form
    if form.validate_on_submit():
        f = form.roster.data
        filename = secure_filename(f.filename)
        f.save(os.path.join(app.root_path, 'uploads', filename))
        return redirect(url_for("results", filename=str(filename)))

    # Nothing submitted so generate form to upload
    return render_template("upload.html", form=form)


@app.route('/results/')
@app.route('/results/<filename>')
def results(filename=None):
    """Ask user to upload roster file and present processed results"""
    if not filename:
        filename = "19-01.htm"
    filename = os.path.join(app.config["UPLOADED_HTML_DEST"], filename)
    pr = ParseRoster()
    days = pr.results(read_html(filename))
    return render_template("results.html",
                           days=enumerate(days),
                           count=only_count(days))


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOADED_HTML_DEST"],
                               filename)


if __name__ == "__main__":
    app.run(debug=True)
