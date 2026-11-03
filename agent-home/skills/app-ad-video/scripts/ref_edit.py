#!/usr/bin/env python3
"""ref_edit.py: reference-guided image generation with Nano Banana Pro on fal.ai.

    python3 ref_edit.py -p Work/prompt.txt -r Asset/cand_a.png [-r Asset/style.png] -o Asset/key.png \
                        [--ar 9:16] [--res 2K] [--n 1]

- Calls fal-ai/nano-banana-pro/edit with the reference images as image_urls. Use it to keep the same
  person, product or look across shots, or to rebuild a reference frame for our app.
- References are shrunk to about 1536 px JPEG and uploaded to the fal CDN (files already made by `fal`
  reuse their URL).
- The prompt comes from a file so long prompts stay exact and reusable.
- Paid: the cost goes to Logs/fal.csv. Needs FAL_KEY in the environment.
"""
import argparse, os, sys, tempfile, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fal import call, fetch, upload  # noqa: E402


def shrink(path, tmp, side=1536):
    try:
        from PIL import Image
    except ImportError:
        return path
    try:
        im = Image.open(path)
    except Exception:
        return path
    if max(im.size) <= side and path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        return path
    s = side / max(im.size)
    im = im.convert("RGB").resize((round(im.size[0] * s), round(im.size[1] * s)), Image.LANCZOS)
    out = os.path.join(tmp, os.path.splitext(os.path.basename(path))[0] + "_ref.jpg")
    im.save(out, "JPEG", quality=92)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--prompt", required=True, help="prompt text file")
    ap.add_argument("-r", "--ref", action="append", required=True, help="reference image (repeatable)")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--ar", default="9:16", help="aspect ratio, for example 9:16, 4:5, 1:1, auto")
    ap.add_argument("--res", default="2K", choices=["1K", "2K", "4K"])
    ap.add_argument("--n", type=int, default=1, help="number of images")
    ap.add_argument("--endpoint", default="fal-ai/nano-banana-pro/edit")
    a = ap.parse_args()
    prompt = open(a.prompt).read().strip()
    with tempfile.TemporaryDirectory() as tmp:
        urls = [upload(shrink(r, tmp)) for r in a.ref]
    d = call(a.endpoint, {"prompt": prompt, "image_urls": urls, "aspect_ratio": a.ar,
                          "resolution": a.res, "num_images": a.n, "output_format": "png"})
    imgs = [i.get("url") for i in d.get("images") or [] if i.get("url")]
    if not imgs:
        sys.exit(f"no image in the result: {str(d)[:400]}")
    base, ext = os.path.splitext(a.out)
    for k, u in enumerate(imgs):
        out = a.out if len(imgs) == 1 else f"{base}_{k + 1}{ext or '.png'}"
        fetch(u, out)
        print(f"OK  {out}  ({os.path.getsize(out) / 1e6:.2f} MB)  {len(urls)} reference(s)")
        print(f"  url: {u}")
    if d.get("description"):
        print("model note:", d["description"][:300])


if __name__ == "__main__":
    main()
