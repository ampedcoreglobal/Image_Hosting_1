import os
import shutil
import subprocess
from pathlib import Path
from flask import Flask, request, send_from_directory, Response
from PIL import Image, ImageChops

# === CONFIG ===
BASE_DIR = Path(__file__).parent
LOCAL_REPO = BASE_DIR
IMAGES_DIR = LOCAL_REPO / "images"
SOURCE_DIR = LOCAL_REPO / "source_images"
REMOTE_URL = "https://github.com/ampedcoreglobal/Image_Hosting_1.git"

TARGET_WIDTH = 3000
TARGET_HEIGHT = 3000

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(SOURCE_DIR, exist_ok=True)

# === Flask app ===
app = Flask(__name__)

# === Helpers ===
def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stderr:
        print(result.stderr.strip())
    return result.stdout.strip()

def ensure_git_repo():
    if not (LOCAL_REPO / ".git").exists():
        run_cmd("git init")
        run_cmd(f"git remote add origin {REMOTE_URL}")
        run_cmd("git fetch origin main || true")
        run_cmd("git checkout -b main || git checkout main")

def get_source_skus():
    skus = set()
    for root, dirs, files in os.walk(SOURCE_DIR):
        rel_path = Path(root).relative_to(SOURCE_DIR)
        if rel_path != Path('.'):
            skus.add(rel_path.name)
        else:
            for f in files:
                sku = Path(f).stem.split("-")[0]
                skus.add(sku)
    return skus

def reset_staging_area():
    source_files = [f for f in SOURCE_DIR.rglob("*")
                    if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png"]]
    if not source_files:
        yield "❌ ERROR: source_images has no valid image files. Aborting.\n"
        return False

    if IMAGES_DIR.exists():
        shutil.rmtree(IMAGES_DIR)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    yield "📥 Preparing staging area...\n"
    return True

def copy_source_to_staging():
    sku_counts = {}
    for root, dirs, files in os.walk(SOURCE_DIR):
        rel_path = Path(root).relative_to(SOURCE_DIR)
        sku_name = rel_path.name if rel_path != Path('.') else None
        dest_dir = IMAGES_DIR / sku_name if sku_name else IMAGES_DIR
        dest_dir.mkdir(parents=True, exist_ok=True)

        for f in files:
            ext = Path(f).suffix.lower()
            if ext not in [".jpg", ".jpeg", ".png"]:
                continue
            src = Path(root) / f

            if rel_path == Path('.'):
                sku_name = Path(f).stem.rsplit("-", 1)[0]
                dest_dir = IMAGES_DIR / sku_name
                dest_dir.mkdir(parents=True, exist_ok=True)
                dst = dest_dir / f
            else:
                dst = dest_dir / f

            shutil.copyfile(src, dst)
            sku = rel_path.name if rel_path != Path('.') else Path(f).stem.split("-")[0]
            sku_counts.setdefault(sku, 0)
            sku_counts[sku] += 1
            yield f"📥 Copied {src} -> {dst}\n"

    for sku, count in sku_counts.items():
        staged_path = IMAGES_DIR / sku if (IMAGES_DIR / sku).exists() else IMAGES_DIR
        staged_count = len([f for f in staged_path.glob("*") if f.suffix.lower() in [".jpg", ".jpeg", ".png"]])
        if staged_count != count:
            yield f"❌ ERROR: Mismatch for {sku} (Source: {count}, Staged: {staged_count})\n"
            return
        else:
            yield f"✅ SKU {sku}: {count} images copied successfully\n"

processed_count = 0

def autocrop_and_resize(img_path):
    global processed_count
    img = Image.open(img_path).convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 0))
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()
    if bbox:
        img = img.crop(bbox)

    img_w, img_h = img.size
    scale = min(TARGET_WIDTH / img_w, TARGET_HEIGHT / img_h)
    new_w, new_h = int(img_w * scale), int(img_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (255, 255, 255, 0))
    x = (TARGET_WIDTH - new_w) // 2
    y = (TARGET_HEIGHT - new_h) // 2
    canvas.paste(img, (x, y), img)

    png_path = img_path.with_suffix(".png")
    canvas.save(png_path, "PNG", optimize=True, compress_level=6)
    if png_path != img_path:
        os.remove(img_path)
    img_path = png_path
    processed_count += 1
    return f"[CROPPED+RESIZED+OPTIMIZED] {img_path} -> {new_w}x{new_h}\n"

def process_images():
    exts = (".jpg", ".jpeg", ".png")
    for root, dirs, files in os.walk(IMAGES_DIR):
        for name in files:
            old_path = Path(root) / name
            if name.lower().endswith(exts):
                yield autocrop_and_resize(old_path)

def update_remote_images(source_skus):
    run_cmd("git fetch origin main")
    run_cmd("git checkout main")
    run_cmd("git reset --hard origin/main")

    for sku in source_skus:
        sku_path = IMAGES_DIR / sku
        if sku_path.exists():
            for file in sku_path.rglob("*"):
                if file.is_file():
                    rel_path = file.relative_to(LOCAL_REPO)
                    run_cmd(f"git add '{rel_path}'")

    run_cmd('git commit -m "Partial SKU update (safe)" --allow-empty || true')
    run_cmd("git push origin main --force")
    return f"✅ Uploaded {processed_count} images for SKUs: {', '.join(source_skus)}\n"

# === Flask Routes ===
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/upload', methods=['POST'])
def upload():
    for file in request.files.getlist('files'):
        file_path = SOURCE_DIR / file.filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file.save(file_path)
    return "Files uploaded", 200

@app.route('/process', methods=['POST'])
def process():
    def generate():
        ensure_git_repo()
        run_cmd("git fetch origin main")
        run_cmd("git reset --hard origin/main")

        if not (yield from reset_staging_area()):
            return

        yield from copy_source_to_staging()
        yield "🔍 Starting processing...\n"
        yield from process_images()
        source_skus = get_source_skus()
        yield update_remote_images(source_skus)

        # ✅ Cleanup source_images
        if SOURCE_DIR.exists():
            shutil.rmtree(SOURCE_DIR)
            SOURCE_DIR.mkdir(parents=True, exist_ok=True)
            run_cmd("git add source_images")
            run_cmd('git commit -m "Cleanup source_images after processing" || true')
            run_cmd("git push origin main --force")
            yield "🧹 Cleaned up source_images folder after processing.\n"

    return Response(generate(), mimetype='text/plain')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
