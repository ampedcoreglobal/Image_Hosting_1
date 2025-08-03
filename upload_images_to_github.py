import os
from pathlib import Path
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageChops

# === CONFIG ===
from pathlib import Path
import os

LOCAL_REPO = Path(__file__).resolve().parent
os.chdir(LOCAL_REPO)  # always work from repo root
IMAGES_DIR = LOCAL_REPO / "images"
SOURCE_DIR = LOCAL_REPO / "source_images"
REMOTE_URL = "https://github.com/ampedcoreglobal/Image_Hosting_1.git"

TARGET_WIDTH = 3000
TARGET_HEIGHT = 3000

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(SOURCE_DIR, exist_ok=True)
os.chdir(LOCAL_REPO)

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

# === Get list of SKUs from source ===
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

# === Reset staging area ===
def reset_staging_area():
    source_files = [f for f in SOURCE_DIR.rglob("*")
                    if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png"]]
    if not source_files:
        print("❌ ERROR: source_images has no valid image files. Aborting.")
        exit(1)

    if IMAGES_DIR.exists():
        shutil.rmtree(IMAGES_DIR)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return len(source_files)

# === Copy source images into staging ===
def copy_source_to_staging():
    sku_counts = {}
    for root, dirs, files in os.walk(SOURCE_DIR):
        rel_path = Path(root).relative_to(SOURCE_DIR)
        dest_dir = IMAGES_DIR / rel_path
        dest_dir.mkdir(parents=True, exist_ok=True)

        for f in files:
            ext = Path(f).suffix.lower()
            if ext not in [".jpg", ".jpeg", ".png"]:
                continue
            src = Path(root) / f

            # ✅ Always create folder based on SKU from filename if file is in root
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
            print(f"📥 Copied {src} -> {dst}")

    for sku, count in sku_counts.items():
        staged_path = IMAGES_DIR / sku if (IMAGES_DIR / sku).exists() else IMAGES_DIR
        staged_count = len([f for f in staged_path.glob("*") if f.suffix.lower() in [".jpg", ".jpeg", ".png"]])
        if staged_count != count:
            print(f"❌ ERROR: Mismatch for {sku} (Source: {count}, Staged: {staged_count})")
            exit(1)
        else:
            print(f"✅ SKU {sku}: {count} images copied successfully")

    return sum(sku_counts.values())

# === Crop + resize ===
processed_count = 0

def autocrop_and_resize(img_path):
    global processed_count
    img = Image.open(img_path).convert("RGBA")

    # === Step 1: Remove white/transparent borders ===
    bg = Image.new("RGBA", img.size, (255, 255, 255, 0))
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()
    if bbox:
        img = img.crop(bbox)

    # === Step 2: Resize to fill as much of 3000x3000 as possible ===
    img_w, img_h = img.size
    scale = min(TARGET_WIDTH / img_w, TARGET_HEIGHT / img_h)
    new_w, new_h = int(img_w * scale), int(img_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # === Step 3: Center on 3000x3000 with minimal padding ===
    canvas = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (255, 255, 255, 0))
    x = (TARGET_WIDTH - new_w) // 2
    y = (TARGET_HEIGHT - new_h) // 2
    canvas.paste(img, (x, y), img)

    # === Step 4: Save optimized PNG (lossless) ===
    png_path = img_path.with_suffix(".png")
    canvas.save(png_path, "PNG", optimize=True, compress_level=6)
    if png_path != img_path:
        os.remove(img_path)  # delete old .jpg/.jpeg
    img_path = png_path
    os.utime(img_path, None)
    processed_count += 1
    print(f"[CROPPED+RESIZED+OPTIMIZED] {img_path} -> {new_w}x{new_h}")


def process_images():
    exts = (".jpg", ".jpeg", ".png")
    for root, dirs, files in os.walk(IMAGES_DIR):
        for name in files:
            old_path = Path(root) / name
            if name.lower().endswith(exts):
                autocrop_and_resize(old_path)

# === Safe Git Update (NO MASS DELETE, NO RESURRECT) ===
def update_remote_images(source_skus):
    print("🔄 Updating matching SKUs on remote (SAFE)...")
    run_cmd("git fetch origin main")
    run_cmd("git checkout main")

    # ✅ Do not allow local unstaged changes to conflict with remote deletes
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
    print(f"✅ Uploaded {processed_count} images for SKUs: {', '.join(source_skus)}")

# === MAIN ===
def main():
    ensure_git_repo()

    # ✅ Sync local to remote first so we respect remote deletes
    run_cmd("git fetch origin main")
    run_cmd("git reset --hard origin/main")

    print("📥 Preparing staging area...")
    expected_files = reset_staging_area()
    copied_files = copy_source_to_staging()

    print(f"🔍 {copied_files} images copied to staging. Starting processing...")
    process_images()

    print(f"📸 Processed {processed_count} images.")
    source_skus = get_source_skus()
    update_remote_images(source_skus)

if __name__ == "__main__":
    main()
