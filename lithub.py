"""
This is a Flask application for displaying and commenting on systematic literature reviews.
Users can upload `.docx` files, view them with their content (text and images), and leave comments.

The app uses SQLite to store comments and serves the reviews dynamically.
"""

import base64
import os
import sqlite3
from datetime import datetime
from io import BytesIO

from docx import Document  # pyright: ignore[reportMissingImports]
from flask import (Flask, redirect, render_template_string,  # type: ignore
                   request, url_for)
# Removed unused Inches import
from PIL import Image  # type: ignore

app = Flask(__name__)

REVIEWS_DIR = "reviews"
DB_FILE = "comments.db"
if not os.path.exists(REVIEWS_DIR):
    os.makedirs(REVIEWS_DIR)


def init_db():
    """Initialize the SQLite database and create comments table if it doesn't exist."""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS comments
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      review_name TEXT,
                      comment TEXT,
                      timestamp TEXT)"""
        )
        conn.commit()


init_db()


def extract_docx_content(filepath):
    """Extract text and images from a .docx file and convert to HTML."""
    doc = Document(filepath)
    content = []
    images = []
    title = None
    description = None

    if len(doc.paragraphs) > 0:
        title = doc.paragraphs[0].text.strip() or "Untitled Review"
    if len(doc.paragraphs) > 1:
        description = doc.paragraphs[1].text.strip(
        ) or "No description available."

    for para in doc.paragraphs[2:]:
        style = para.style.name.lower()
        para_html = ""

        if "heading" in style or para.text.strip().lower().startswith("chapter"):
            chapter_title = para.text.strip()
            if chapter_title:
                content.append(
                    f'<h2 class="text-xl font-bold mt-6 mb-2">{chapter_title}</h2>')
            continue

        for run in para.runs:
            text = run.text
            if text.strip():
                if run.bold:
                    text = f"<b>{text}</b>"
                if run.italic:
                    text = f"<i>{text}</i>"
                para_html += text
        if para_html:
            content.append(f"<p>{para_html}</p>")

    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            img_data = rel.target_part.blob
            img = Image.open(BytesIO(img_data))
            img_format = img.format.lower() if img.format else "jpeg"
            img_io = BytesIO()
            img.save(img_io, format=img_format)
            img_base64 = base64.b64encode(img_io.getvalue()).decode("utf-8")
            images.append(f"data:image/{img_format};base64,{img_base64}")

    return title, description, "".join(content), images


@app.route("/")
def home():
    """
    Home page displaying a list of reviews.
    """
    reviews = [f for f in os.listdir(REVIEWS_DIR) if f.endswith(".docx")]
    reviews_data = []
    for review_data in reviews:
        path = os.path.join(REVIEWS_DIR, review_data)
        title, description, _, _ = extract_docx_content(path)
        reviews_data.append(
            {"filename": review_data, "title": title, "description": description}
        )
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Systematic Literature Reviews</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100 font-sans">
        <header class="bg-blue-600 text-white py-6">
            <div class="container mx-auto px-4">
                <h1 class="text-3xl font-bold">Systematic Literature Reviews</h1>
                <p class="mt-2">A collection of peer-reviewed systematic literature reviews</p>
            </div>
        </header>
        <main class="container mx-auto px-4 py-8">
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {% for review in reviews %}
                <div class="bg-white p-6 rounded-lg shadow-md">
                    <h2 class="text-xl font-semibold mb-2">{{ review.title }}</h2>
                    <p class="text-gray-600 mb-4">{{ review.description }}</p>
                    <a href="/review/{{ review.filename }}" class="text-blue-600 hover:underline">
                    Read More
                    </a>
                </div>
                {% endfor %}
            </div>
        </main>
        <footer class="bg-gray-800 text-white py-4">
            <div class="container mx-auto px-4 text-center">
                <p>&copy; 2025 Systematic Reviews Blog. All rights reserved.</p>
            </div>
        </footer>
    </body>
    </html>
    """
    return render_template_string(html, reviews=reviews_data)


@app.route("/review/<name>", methods=["GET", "POST"])
def review(name):
    """Display a specific review and handle comments."""
    if not name.endswith(".docx"):
        return "Invalid file", 400
    path = os.path.join(REVIEWS_DIR, name)
    if not os.path.exists(path):
        return "File not found", 404

    if request.method == "POST":
        comment = request.form.get("comment")
        if comment:
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO comments (review_name, comment, timestamp) \
                  VALUES (?, ?, ?)",
                    (name, comment, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )
                conn.commit()
        return redirect(url_for("review", name=name))

    title, description, content, images = extract_docx_content(path)

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT comment, timestamp FROM comments WHERE review_name = ? \
              ORDER BY timestamp DESC",
            (name,),
        )
        comments = c.fetchall()

    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{{ title }}</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100 font-sans">
        <header class="bg-blue-600 text-white py-6">
            <div class="container mx-auto px-4">
                <h1 class="text-3xl font-bold">{{ title }}</h1>
                <p class="mt-2">{{ description }}</p>
            </div>
        </header>
        <main class="container mx-auto px-4 py-8">
            <div class="bg-white p-6 rounded-lg shadow-md">
                <div class="prose max-w-none">
                    {{ content | safe }}
                    {% for img in images %}
                    <img src="{{ img }}" alt="Document Image" class="my-4 max-w-full h-auto">
                    {% endfor %}
                </div>
                <a href="/" class="text-blue-600 hover:underline mt-4 inline-block">Back to Home</a>
            </div>
            <div class="mt-8">
                <h2 class="text-2xl font-semibold mb-4">Comments</h2>
                <form method="POST" class="mb-6">
                    <textarea name="comment" rows="4" class="w-full p-3 border rounded-lg"
                        placeholder="Add your comment..." required></textarea>
                    <button type="submit" class="bg-blue-600 text-white py-2 px-4 rounded-lg
                        hover:bg-blue-700">Submit Comment</button>
                </form>
                {% if comments %}
                <div class="space-y-4">
                    {% for comment in comments %}
                    <div class="bg-gray-50 p-4 rounded-lg">
                        <p class="text-gray-800">{{ comment[0] }}</p>
                        <p class="text-gray-500 text-sm">{{ comment[1] }}</p>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <p class="text-gray-600">No comments yet. Be the first to comment!</p>
                {% endif %}
            </div>
        </main>
        <footer class="bg-gray-800 text-white py-4">
            <div class="container mx-auto px-4 text-center">
                <p>&copy; 2025 Systematic Reviews Blog. All rights reserved.</p>
            </div>
        </footer>
    </body>
    </html>
    """
    return render_template_string(
        html,
        title=title,
        description=description,
        content=content,
        images=images,
        comments=comments,
    )


if __name__ == "__main__":
    app.run(debug=True)
