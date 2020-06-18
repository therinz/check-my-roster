import os

from flask import Flask, escape, request, render_template, url_for
from flask_wtf import FlaskForm
from wtforms import SubmitField
from flask_wtf.file import FileField, FileRequired, FileAllowed
from flask_uploads import configure_uploads, UploadSet


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
        filename = allowed_types.save(form.roster.data)
        # TODO Process roster
        # TODO show results
        print(filename)
        return render_template("results.html")

    # Nothing submitted so generate form to upload
    else:
        return render_template("upload.html", form=form)


if __name__ == "__main__":
    app.run(debug=True)
