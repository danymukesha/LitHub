from flask import Flask, render_template_string
from docx import Document
import os

app = Flask(__name__)

# Assume .docx files are placed in a 'reviews' folder by the user
REVIEWS_DIR = 'reviews'
if not os.path.exists(REVIEWS_DIR):
    os.makedirs(REVIEWS_DIR)

@app.route('/')
def home():
    reviews = [f for f in os.listdir(REVIEWS_DIR) if f.endswith('.docx')]
    html = '''
    <h1>Systematic Literature Reviews Blog</h1>
    <ul>
    {% for review in reviews %}
        <li><a href="/review/{{ review }}">{{ review }}</a></li>
    {% endfor %}
    </ul>
    '''
    return render_template_string(html, reviews=reviews)

@app.route('/review/<name>')
def review(name):
    if not name.endswith('.docx'):
        return "Invalid file", 400
    path = os.path.join(REVIEWS_DIR, name)
    if not os.path.exists(path):
        return "File not found", 404
    doc = Document(path)
    # Extract paragraphs, preserving basic structure (bold/italic via HTML if present)
    content = []
    for para in doc.paragraphs:
        para_html = ''
        for run in para.runs:
            text = run.text
            if run.bold:
                text = f'<b>{text}</b>'
            if run.italic:
                text = f'<i>{text}</i>'
            para_html += text
        content.append(f'<p>{para_html}</p>')
    full_content = ''.join(content)
    html = '''
    <h1>{{ name }}</h1>
    {{ content | safe }}
    <a href="/">Back to home</a>
    '''
    return render_template_string(html, name=name, content=full_content)

if __name__ == '__main__':
    app.run(debug=True)
