from PIL import Image, ImageDraw, ImageFont
import os, shutil

icons_dir = r"C:\Users\25791\Desktop\OpsPilot\frontend\src-tauri\icons"
os.makedirs(icons_dir, exist_ok=True)

def make(size, path):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = max(2, int(size * 0.15))
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=(56, 139, 253, 255))
    fs = max(8, int(size * 0.36))
    try:
        f = ImageFont.truetype("arial.ttf", fs)
    except Exception:
        f = ImageFont.load_default()
    bbox = d.textbbox((0, 0), "OP", font=f)
    x = (size - bbox[2] + bbox[0]) // 2 - bbox[0]
    y = (size - bbox[3] + bbox[1]) // 2 - bbox[1]
    d.text((x, y), "OP", fill=(255, 255, 255, 255), font=f)
    img.save(path)

for sz, name in [(32, "32x32.png"), (128, "128x128.png"), (256, "128x128@2x.png"), (256, "icon.png")]:
    make(sz, os.path.join(icons_dir, name))

ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
imgs = []
for sz_w, sz_h in ico_sizes:
    img = Image.new("RGBA", (sz_w, sz_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = max(1, int(sz_w * 0.15))
    d.rounded_rectangle([0, 0, sz_w - 1, sz_h - 1], radius=r, fill=(56, 139, 253, 255))
    fs = max(6, int(sz_w * 0.36))
    try:
        f = ImageFont.truetype("arial.ttf", fs)
    except Exception:
        f = ImageFont.load_default()
    bbox = d.textbbox((0, 0), "OP", font=f)
    d.text(((sz_w - bbox[2] + bbox[0]) // 2 - bbox[0], (sz_h - bbox[3] + bbox[1]) // 2 - bbox[1]), "OP",
           fill=(255, 255, 255, 255), font=f)
    imgs.append(img)
img.save(os.path.join(icons_dir, "icon.ico"), format="ICO")
shutil.copy2(os.path.join(icons_dir, "128x128@2x.png"), os.path.join(icons_dir, "icon.icns"))
print("icons:", os.listdir(icons_dir))
