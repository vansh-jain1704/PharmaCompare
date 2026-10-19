"""
Draws the SYNTHETIC prescription used to demonstrate the "Needs verification" workflow.

It is not a real prescription: there is no patient, doctor, clinic or hospital in it, and nothing on it is medical
advice. Each medicine line is chosen so the real pipeline (OCR -> matcher) gives a different, known outcome:

  Tab Dolo 650   ...  read and matched automatically       (settled: priced, alternatives, savings)
  Tab Azee 500   ...  read and matched automatically       (settled)
  Cap Omez 20    ...  matched, but the form differs        ("Check match": the line says capsule, the product is a tablet)
  Tab Zincovit   ...  only look-alikes exist in the dataset ("Needs verification" with candidates and reasons)
  Tab Shelcal 500 ... nothing on file resembles it          ("Needs verification" with no candidates)

Durations are written "for N days" (not "x N days"): OCR reads a lone "x" with low confidence, and one weak word makes
the matcher treat the whole line as "read with low confidence" - which would hide the very states this page demonstrates.

Run:  backend\\venv\\Scripts\\python.exe demo\\make_synthetic_prescription.py
Writes demo\\synthetic_prescription.png next to this file.
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "synthetic_prescription.png")

LINES = [
    ("title", "DEMO CLINIC (SYNTHETIC)"),
    ("small", "Sample prescription for software testing only. Not a real person. Not medical advice."),
    ("gap", ""),
    ("text", "Rx"),
    ("med", "1.  Tab Dolo 650        1-0-1        for 5 days"),
    ("med", "2.  Tab Azee 500        1-0-0        for 3 days"),
    ("med", "3.  Cap Omez 20         1-0-0        for 7 days"),
    ("med", "4.  Tab Zincovit        1-0-0        for 10 days"),
    ("med", "5.  Tab Shelcal 500     0-1-0        for 30 days"),
]


def font(size, bold=False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    width, height = 1100, 900
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([30, 30, width - 30, height - 30], outline=(40, 40, 120), width=3)
    y = 70
    for kind, text in LINES:
        if kind == "title":
            draw.text((70, y), text, fill=(20, 20, 90), font=font(40, True)); y += 70
        elif kind == "small":
            draw.text((70, y), text, fill=(90, 90, 90), font=font(22)); y += 50
        elif kind == "gap":
            y += 20
        elif kind == "text":
            draw.text((70, y), text, fill=(0, 0, 0), font=font(44, True)); y += 85
        else:
            draw.text((90, y), text, fill=(0, 0, 0), font=font(38)); y += 95
    image.save(OUT)
    print("wrote", OUT, image.size)


if __name__ == "__main__":
    main()
