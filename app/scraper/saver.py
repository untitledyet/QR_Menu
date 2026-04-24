"""
Saver — handles all persistence: menu items, glovo items, menu photos.
Replaces saveMenuItems.py, saveGlovoItems.py, saveMenuPhotos.py.
"""
import os
import json
import requests


def save_menu_json(menu: dict, output_dir: str) -> str:
    """Save final merged menu to JSON. Returns file path."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "menu_output.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(menu, f, ensure_ascii=False, indent=2)
    print("[Saver] Menu saved to " + path)
    return path


def save_photo(url: str, dest_path: str) -> bool:
    """Download a photo from URL and save to dest_path. Returns True on success."""
    try:
        r = requests.get(url, timeout=15)
        if len(r.content) < 5000:
            return False
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        print("[Saver] Photo download error: " + str(e))
        return False


def save_glovo_photos(glovo_data: dict, photos_dir: str) -> dict:
    """
    Download Glovo item images locally.
    Returns mapping: {item_name_lower: local_path}
    """
    os.makedirs(photos_dir, exist_ok=True)
    mapping = {}
    idx = 0
    for cat, items in glovo_data.items():
        for it in items:
            url = it.get("image", "")
            if not url or not url.startswith("http"):
                continue
            name_key = it.get("name", "").lower().strip()
            fname = "glovo_" + str(idx).zfill(4) + ".jpg"
            dest = os.path.join(photos_dir, fname)
            if save_photo(url, dest):
                mapping[name_key] = dest
                idx += 1
    print("[Saver] Downloaded " + str(len(mapping)) + " Glovo photos")
    return mapping


def save_google_photos(photo_urls: list, photos_dir: str) -> list:
    """
    Download Google menu photos locally.
    Returns list of local file paths.
    """
    os.makedirs(photos_dir, exist_ok=True)
    paths = []
    for i, base_url in enumerate(photo_urls):
        url = base_url + "=w2000"
        dest = os.path.join(photos_dir, "menu_photo_" + str(i + 1).zfill(3) + ".jpg")
        if save_photo(url, dest):
            paths.append(dest)
            print("[Saver] Saved Google photo " + os.path.basename(dest))
    print("[Saver] Downloaded " + str(len(paths)) + " Google menu photos")
    return paths
