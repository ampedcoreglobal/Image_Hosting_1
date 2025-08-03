import os
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageChops

# === CONFIG ===
LOCAL_REPO = Path(".").resolve()
IMAGES_DIR = LOCAL_REPO / "images"
SOURCE_DIR = LOCAL_REPO / "source_images"
REMOTE_URL = "https://github.com/ampedcoreglobal/Image_Hosting_1.git"

TARGET_WIDTH = 3000
TARGET_HEIGHT = 3000

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(SOURCE_DIR, exist_ok=True)

# === Helpers ===
def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stderr.strip():
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
        print("❌ ERROR: source_images has no valid image files. Aborting.")
        exit(1)

    if IMAGES_DIR.exists():
        os.makedirs(IMAGES_DIR, exist_ok=True)
    else:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return len(source_files)

def copy_source_to_staging():
    for root, dirs, files in os.walk(SOURCE_DIR):
        rel_path = Path(root).relative_to(SOURCE_DIR)
        dest_dir = IMAGES_DIR / rel_path
        dest_dir.mkdir(parents=True, exist_ok=True)

        for f in files:
            ext = Path(f).suffix.lower()
            if ext not in [".jpg", ".jpeg", ".png"]:
                continue
            src = Path(root) / f
            dst = dest_dir / f
            shutil.copyfile(src, dst)
            print(f"📥 Copied {src} -> {dst}")

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
    processed_count += 1
    print(f"[CROPPED+RESIZED+OPTIMIZED] {img_path} -> {new_w}x{new_h}")

def process_images():
    exts = (".jpg", ".jpeg", ".png")
    for root, dirs, files in os.walk(IMAGES_DIR):
        for name in files:
            old_path = Path(root) / name
            if name.lower().endswith(exts):
                autocrop_and_resize(old_path)

def update_remote_images(source_skus):
    run_cmd("git config user.name 'GitHub Action'")
    run_cmd("git config user.email 'action@github.com'")
    run_cmd("git add images")
    run_cmd('git commit -m "Processed and optimized images" || true')
    run_cmd("git push origin main")

def main():
    ensure_git_repo()
    run_cmd("git fetch origin main")
    run_cmd("git reset --hard origin/main")

    print("📥 Preparing staging area...")
    reset_staging_area()
    copy_source_to_staging()

    print("🔍 Starting processing...")
    process_images()

    print(f"📸 Processed {processed_count} images.")
    source_skus = get_source_skus()
    update_remote_images(source_skus)

    if SOURCE_DIR.exists():
        shutil.rmtree(SOURCE_DIR)
        SOURCE_DIR.mkdir(parents=True, exist_ok=True)
        run_cmd("git add source_images")
        run_cmd('git commit -m "Cleanup source_images after processing" || true')
        run_cmd("git push origin main")
        print("🧹 Cleaned up source_images folder after processing.")

if __name__ == "__main__":
    main()
