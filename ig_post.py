"""
ig_post.py — Image preparation + Instagram posting
- Smart crop to 4:5 (fills frame, no black bars)
- Watermark removal (bottom-right corner patch)
- Cloudinary upload + Instagram Graph API post
"""
import os
import io
import requests
import cloudinary
import cloudinary.uploader
from PIL import Image, ImageFilter
from dotenv import load_dotenv

load_dotenv(override=True)

IG_TOKEN   = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = "34617611521215522"

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)


def remove_watermark(img: Image.Image) -> Image.Image:
    """
    Remove Gemini's small diamond watermark from bottom-right corner.
    Copies clean pixels from just above the watermark region.
    Works for any background since it mirrors adjacent content.
    """
    import numpy as np
    arr = np.array(img)
    h, w = arr.shape[:2]

    # Watermark is roughly 60x60px in the bottom-right
    patch_h, patch_w = 70, 70

    # Source: clean region just above the watermark
    src = arr[h - patch_h*2 : h - patch_h, w - patch_w : w]
    # Destination: watermark region
    arr[h - patch_h : h, w - patch_w : w] = src

    return Image.fromarray(arr)


def smart_crop(img: Image.Image, tw=1080, th=1350) -> Image.Image:
    """
    Smart crop to 4:5 Instagram portrait.
    Scales to fill the frame completely, then center-crops.
    Subject (character) is usually centered so this works well.
    """
    target_ratio = tw / th
    src_ratio = img.width / img.height

    if src_ratio > target_ratio:
        # Image wider than target — scale by height, crop sides
        new_h = th
        new_w = int(img.width * th / img.height)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        x = (new_w - tw) // 2
        img = img.crop((x, 0, x + tw, th))
    else:
        # Image taller than target — scale by width, crop top/bottom
        new_w = tw
        new_h = int(img.height * tw / img.width)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        # Crop from top 1/3 (character is usually in upper portion)
        y = max(0, (new_h - th) // 3)
        img = img.crop((0, y, tw, y + th))

    return img.resize((tw, th), Image.LANCZOS)


def prepare_image(src_path: str) -> str:
    out = src_path + "_ig.jpg"
    img = Image.open(src_path).convert("RGB")

    print(f"[IG] Original: {img.width}x{img.height}")

    # Step 1: Remove Gemini watermark
    try:
        import numpy as np
        img = remove_watermark(img)
        print("[IG] Watermark removed ✓")
    except ImportError:
        print("[IG] numpy not installed — skipping watermark removal")

    # Step 2: Smart crop to 1080x1350
    img = smart_crop(img)
    print(f"[IG] Cropped to: {img.width}x{img.height}")

    img.save(out, "JPEG", quality=95)
    return out


def post(image_path: str, caption: str) -> bool:
    ig_path = prepare_image(image_path)

    print("[IG] Uploading to Cloudinary...")
    result = cloudinary.uploader.upload(ig_path, folder="aura_posts")
    image_url = result["secure_url"]
    print(f"[IG] URL: {image_url}")

    r1 = requests.post(
        f"https://graph.instagram.com/v18.0/{IG_USER_ID}/media",
        data={"image_url": image_url, "caption": caption, "access_token": IG_TOKEN}
    )
    container_id = r1.json().get("id")
    if not container_id:
        print(f"[IG] Container failed: {r1.json()}")
        return False

    r2 = requests.post(
        f"https://graph.instagram.com/v18.0/{IG_USER_ID}/media_publish",
        data={"creation_id": container_id, "access_token": IG_TOKEN}
    )
    ok = bool(r2.json().get("id"))
    print(f"[IG] Published: {r2.json()}")
    return ok