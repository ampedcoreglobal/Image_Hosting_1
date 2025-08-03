from flask import Flask, request, jsonify, send_from_directory, Response
import os, subprocess
from pathlib import Path

app = Flask(__name__)
UPLOAD_DIR = Path("source_images")
UPLOAD_DIR.mkdir(exist_ok=True)

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    for file in request.files.getlist('files'):
        filepath = UPLOAD_DIR / file.filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        file.save(filepath)
    return jsonify({"status": "uploaded"})

@app.route('/process', methods=['POST'])
def process_images():
    def run_script():
        process = subprocess.Popen(
            ["python3", "upload_images_to_github.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in process.stdout:
            yield line
    return Response(run_script(), mimetype='text/plain')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
