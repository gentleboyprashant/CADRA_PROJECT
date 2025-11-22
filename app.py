from flask import Flask, render_template, request, redirect, url_for
from detector import analyze
import os

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def run_analyze():
    text = request.form.get("doc_text", "").strip()
    if not text:
        return redirect(url_for("index"))
    report = analyze(text)
    return render_template("result.html", text=text, report=report)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
