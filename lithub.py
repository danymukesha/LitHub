"""A Flask web application to display systematic literature reviews from .docx files,
allowing users to upload new reviews and comment on them."""

import base64
import os
import re
import sqlite3
from datetime import datetime
from io import BytesIO

from docx import Document  # pyright: ignore[reportMissingImports]
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from flask import redirect  # type: ignore
from flask import Flask, flash, render_template_string, request, url_for
from PIL import Image  # type: ignore

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Needed for session and flashing messages

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
    """Extract content from a .docx file preserving order of paragraphs, tables, images, and lists."""

    def iter_block_items(parent):
        """Yield paragraphs and tables in the order they appear in the document."""
        parent_elm = parent.element.body
        for child in parent_elm.iterchildren():
            if child.tag == qn("w:p"):
                yield Paragraph(child, parent)
            elif child.tag == qn("w:tbl"):
                yield Table(child, parent)

    doc = Document(filepath)
    content = []

    # Title and description (only first two paragraphs)
    title = doc.paragraphs[0].text.strip(
    ) if doc.paragraphs else "Untitled Review"
    description = (
        doc.paragraphs[1].text.strip()
        if len(doc.paragraphs) > 1
        else "No description available."
    )

    # Actual content starts after title + description
    block_items = list(iter_block_items(doc))[2:]

    list_open = None

    for block in block_items:
        # Paragraphs
        if isinstance(block, Paragraph):
            style = block.style.name.lower()
            text = block.text.strip()

            # Skip empty paragraphs
            if not text:
                continue

            # Headings
            if "heading" in style or text.lower().startswith("chapter"):
                if list_open:
                    content.append(f"</{list_open}>")
                    list_open = None
                content.append(
                    f'<h2 class="text-xl font-bold mt-6 mb-2">{text}</h2>')
                continue

            # Lists (bullet or numbered)
            if style.startswith("list") or re.search(r"bullet|number", style):
                tag = "ul" if "bullet" in style else "ol"
                if list_open and list_open != tag:
                    content.append(f"</{list_open}>")
                    list_open = tag
                    content.append(f"<{tag}>")
                elif not list_open:
                    list_open = tag
                    content.append(f"<{tag}>")
                content.append(f"<li>{text}</li>")
                continue
            else:
                if list_open:
                    content.append(f"</{list_open}>")
                    list_open = None

            # Rich text formatting
            para_html = ""
            for run in block.runs:
                run_text = run.text
                if not run_text:
                    continue
                if run.bold:
                    run_text = f"<b>{run_text}</b>"
                if run.italic:
                    run_text = f"<i>{run_text}</i>"
                para_html += run_text

            if para_html.strip():
                content.append(f"<p>{para_html.strip()}</p>")

        # Tables
        elif isinstance(block, Table):
            if list_open:
                content.append(f"</{list_open}>")
                list_open = None
            table_html = (
                '<table class="table-auto border border-collapse border-gray-300 my-4">'
            )
            for row in block.rows:
                table_html += "<tr>"
                for cell in row.cells:
                    table_html += f'<td class="border p-2">{
                        cell.text.strip()}</td>'
                table_html += "</tr>"
            table_html += "</table>"
            content.append(table_html)

    # Close any unclosed list
    if list_open:
        content.append(f"</{list_open}>")

    # Images (appended after all content for now)
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            img_data = rel.target_part.blob
            img = Image.open(BytesIO(img_data))
            img_format = img.format.lower() if img.format else "jpeg"
            img_io = BytesIO()
            img.save(img_io, format=img_format)
            img_base64 = base64.b64encode(img_io.getvalue()).decode("utf-8")
            img_tag = f'<img src="data:image/{img_format};base64,{img_base64}" class="my-4 max-w-full h-auto"/>'
            content.append(img_tag)

    return title, description, "".join(content), []


@app.route("/", methods=["GET", "POST"])
def home():
    """
    Home page displaying a list of reviews and an option to upload a new review.
    """
    query = request.args.get("query", "")
    reviews = [f for f in os.listdir(REVIEWS_DIR) if f.endswith(".docx")]

    reviews_data = []
    for review_data in reviews:
        path = os.path.join(REVIEWS_DIR, review_data)
        title, description, _, _ = extract_docx_content(path)
        created_on = datetime.fromtimestamp(os.path.getctime(path)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        if query.lower() in title.lower() or query.lower() in description.lower():
            reviews_data.append(
                {
                    "filename": review_data,
                    "title": title,
                    "description": description,
                    "created_on": created_on,
                }
            )

    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename.endswith(".docx"):
            filename = file.filename
            file_path = os.path.join(REVIEWS_DIR, filename)
            file.save(file_path)
            flash("File uploaded successfully!", "success")
            return redirect(url_for("home"))
        flash("Invalid file format. Please upload a .docx file.", "danger")

    no_results = len(reviews_data) == 0

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
            <div class="mb-6">
                <!-- Search Bar -->
                <form method="GET" action="/" class="flex items-center space-x-4">
                    <input type="text" name="query" value="{{ query }}" placeholder="Search reviews..."
                        class="w-full p-2 border rounded-lg" />
                    <button type="submit" class="bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700">
                        Search
                    </button>
                </form>
            </div>

            <div class="mb-6">
                {% if no_results %}
                    <div class="bg-yellow-100 text-yellow-800 p-3 rounded-lg">
                        No reviews found for your query.
                    </div>
                {% endif %}
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {% for review in reviews %}
                <div class="bg-white p-6 rounded-lg shadow-md">
                    <h2 class="text-xl font-semibold mb-2">{{ review.title }}</h2>
                    <p class="text-gray-600 mb-4">{{ review.description }}</p>
                    <a href="/review/{{ review.filename }}" class="text-blue-600 hover:underline">
                    Read More
                    </a>
                    <p class="text-gray-500 text-sm">Created on {{ review.created_on }}</p> <!-- Add this line -->
                </div>
                {% endfor %}
            </div>

            <!-- File Upload Form -->
            <div class="mt-8">
                <h2 class="text-xl font-semibold mb-4">Upload New Review</h2>
                <form method="POST" enctype="multipart/form-data">
                    <input type="file" name="file" class="border p-2 rounded-lg mb-4" accept=".docx" required>
                    <button type="submit" class="bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700">
                        Upload Review
                    </button>
                </form>
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                    <div class="mt-4">
                        {% for category, message in messages %}
                        <div class="bg-{{ category }}-100 text-{{ category }}-800 p-3 rounded-lg mb-3">
                            {{ message }}
                        </div>
                        {% endfor %}
                    </div>
                    {% endif %}
                {% endwith %}
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
        html, reviews=reviews_data, query=query, no_results=no_results
    )


@app.route("/review/<name>", methods=["GET", "POST"])
def review(name):
    """Display a specific review and handle comments."""
    if not name.endswith(".docx"):
        return "Invalid file", 400
    path = os.path.join(REVIEWS_DIR, name)
    if not os.path.exists(path):
        return "File not found", 404

    # Handle new comment submission
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

    # Extract document content (title, description, and formatted content)
    title, description, content, images = extract_docx_content(path)

    # Retrieve comments from the database for this specific review
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT comment, timestamp FROM comments WHERE review_name = ? \
              ORDER BY timestamp DESC",
            (name,),
        )
        comments = c.fetchall()

    # Render the review page with comments and content
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
                    <a href="/edit/{{ name }}" class="text-green-600 hover:underline mt-4 inline-block
                    bg-green-600 text-white py-2 px-4 rounded-lg hover:bg-green-700 mt-4 inline-block">
                    Edit Review
                </a>
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
        name=name,
    )


@app.route("/edit/<filename>", methods=["GET", "POST"])
def edit_review(filename):
    """Allow users to edit a specific review."""
    # Make sure the file exists
    path = os.path.join(REVIEWS_DIR, filename)
    if not os.path.exists(path):
        return "File not found", 404

    # Extract document content for editing
    title, description, content, _ = extract_docx_content(path)

    if request.method == "POST":
        new_title = request.form.get("title")
        new_description = request.form.get("description")
        file = request.files.get("file")  # Handle file upload

        if new_title and new_description:
            # Update title and description
            doc = Document(path)
            doc.paragraphs[0].text = new_title
            doc.paragraphs[1].text = new_description
            doc.save(path)
            flash("Title and Description updated successfully!", "success")
            return redirect(url_for("home"))

        if file and file.filename.endswith(".docx"):
            # Replace entire file content with a new .docx file
            filename = file.filename
            file_path = os.path.join(REVIEWS_DIR, filename)
            file.save(file_path)

            # Extract and update content with the new file
            title, description, content, _ = extract_docx_content(file_path)

            # Now update the document with the new content
            doc = Document(file_path)
            doc.paragraphs[0].text = title
            doc.paragraphs[1].text = description
            doc.save(file_path)
            flash("Review content replaced with new file successfully!", "success")
            return redirect(url_for("home"))

        # Flash error if neither title/description nor file were provided
        flash(
            "No changes were made. Please update either the title/description or upload a file.",
            "danger",
        )

        return redirect(url_for("edit_review", filename=filename))

    # Render the edit page
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Edit Review</title>
        <link href="https://cdn.quilljs.com/1.3.6/quill.snow.css" rel="stylesheet">
        <script src="https://cdn.quilljs.com/1.3.6/quill.min.js"></script>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100 font-sans">
        <header class="bg-blue-600 text-white py-6">
            <div class="container mx-auto px-4">
                <h1 class="text-3xl font-bold">Edit Review: {{ title }}</h1>
            </div>
        </header>
        <main class="container mx-auto px-4 py-8">
            <form method="POST">
                <div class="mb-4">
                    <label for="title" class="block text-gray-700">Title</label>
                    <input type="text" name="title" id="title" value="{{ title }}" class="w-full p-2 border rounded-lg" required>
                </div>
                <div class="mb-4">
                    <label for="description" class="block text-gray-700">Description</label>
                    <textarea name="description" id="description" rows="4" class="w-full p-2 border rounded-lg" required>{{ description }}</textarea>
                </div>
                <p>At the moment, editing the main content is not supported, only changes to the title and description.
                If you want to make major changes, please upload a new .docx file to replace the content.</p>
                <div class="mb-4">
                    <label for="file" class="block text-gray-700">Upload New DOCX (Optional)</label>
                    <input type="file" name="file" id="file" class="w-full p-2 border rounded-lg" accept=".docx">
                </div>
                <button type="submit" class="bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700">Save Changes</button>
            </form>
            <a href="/review/{{ name }}" class="text-blue-600 hover:underline mt-4 inline-block">Back to Review</a>
        </main>

        <script>
            // Initialize Quill editor
            var quill = new Quill('#editor', {
                theme: 'snow',
                modules: {
                    toolbar: [
                        [{ 'header': '1'}, {'header': '2'}, { 'font': [] }],
                        [{ 'list': 'ordered'}, { 'list': 'bullet' }],
                        ['bold', 'italic', 'underline'],
                        [{ 'align': [] }],
                        ['link', 'image']
                    ]
                }
            });

            // Add initial content from the backend (using Quill's insertText method)
            quill.root.innerHTML = `{{ content|safe }}`;
        </script>
    </body>
    </html>

    """
    return render_template_string(
        html,
        title=title,
        description=description,
        content=content,
        name=filename)


if __name__ == "__main__":
    app.run(debug=True)
