import os
import subprocess
from flask import Flask, request, send_from_directory, Response

app = Flask(__name__)
UPLOAD_FOLDER = "source_images"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ✅ Serve the index.html UI
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# ✅ Handle file uploads
@app.route('/upload', methods=['POST'])
def upload_files():
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    for file in request.files.getlist('files'):
        save_path = os.path.join(UPLOAD_FOLDER, file.filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        file.save(save_path)
    return "✅ Files uploaded"

# ✅ Trigger the processing script and stream logs
@app.route('/process', methods=['POST'])
def process_files():
    def run_script():
        process = subprocess.Popen(
            ["python3", "upload_images_to_github.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        for line in iter(process.stdout.readline, ''):
            yield line
        process.stdout.close()
        process.wait()

    return Response(run_script(), mimetype='text/plain')

# ✅ Run Flask on Replit
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
