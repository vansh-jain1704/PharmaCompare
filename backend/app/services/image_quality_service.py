"""
Is the photo good enough to read? Plain checks that say WHY a photo is likely to read badly, before (and next to) the OCR.

The OCR already reports how confident it was, but a low average cannot tell the person what to fix. These checks can: they look at the
pixels (sharpness, size, brightness, contrast) and say so in words. They only ever WARN. They never block an upload, never change
what the OCR reads, and never claim a photo is good: "no problems detected" means these four checks found none.

CALIBRATION (honest): the thresholds are heuristic defaults in app/config.py, chosen by measuring the five distinct sample photos in this
project and controlled degradations (blur, darkening, low contrast, shrinking) of a clean synthetic page. On those: the one photo the OCR
read worst (average confidence 0.41) has sharpness 17.7 against 108 or more for the photos it read, blur of sigma 4 or more falls to 2 or
less, darkening to a quarter gives brightness 61, and only the shrunken copy has a short side under 600 px. Five photos cannot validate a
threshold: treat them as defaults to tune on a larger labelled set. A "glare" check was measured and dropped: a clean white page is mostly
pure white, which says nothing about glare.

Sharpness is the variance of the Laplacian of the grey image resized to 1000 px wide, so that photos of different sizes are comparable.
It also depends on how much text is on the page, which is one more reason these are warnings and not verdicts.
"""
import cv2
import numpy as np

from app.config import Config

NORMAL_WIDTH = 1000


def _load(path, ext):
    if (ext or "").lower() == "pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(path)
        try:
            return cv2.cvtColor(np.array(pdf[0].render(scale=2.0).to_pil().convert("RGB")), cv2.COLOR_RGB2BGR)
        finally:
            pdf.close()
    return cv2.imread(path)


def measure(image):
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    normal = cv2.resize(gray, (NORMAL_WIDTH, max(int(height * NORMAL_WIDTH / max(width, 1)), 1)), interpolation=cv2.INTER_AREA)
    return {
        "width": int(width), "height": int(height),
        "sharpness": round(float(cv2.Laplacian(normal, cv2.CV_64F).var()), 1),
        "brightness": round(float(gray.mean()), 1),
        "contrast": round(float(gray.std()), 1),
    }


def warnings_for(m):
    """The plain-language warnings for one set of measurements, using the configured thresholds."""
    found = []
    if min(m["width"], m["height"]) < Config.IMAGE_MIN_SIDE_PIXELS:
        found.append({"code": "low_resolution", "text": f"The image is small ({m['width']} x {m['height']} pixels), so small or thin handwriting may not be readable. "
                                                          "Take the photo closer, or at a higher resolution."})
    if m["sharpness"] < Config.IMAGE_MIN_SHARPNESS:
        found.append({"code": "blurry", "text": "The photo looks blurry or out of focus, which is the most common reason handwriting is misread. "
                                                "Hold the phone steady, let it focus, and retake it."})
    if m["brightness"] < Config.IMAGE_MIN_BRIGHTNESS:
        found.append({"code": "too_dark", "text": "The photo is dark. Retake it in good light, with no shadow across the page."})
    if m["contrast"] < Config.IMAGE_MIN_CONTRAST:
        found.append({"code": "low_contrast", "text": "The writing barely stands out from the paper. Retake it in better light, with the page flat."})
    return found


def assess(path, ext=None):
    """
    {"width", "height", "sharpness", "brightness", "contrast", "warnings": [...], "checked": [...]}  or None when the file cannot be read as an image
    (nothing is then claimed about it).
    """
    try:
        image = _load(path, ext)
        if image is None or image.size == 0:
            return None
        m = measure(image)
    except Exception:
        return None
    return {**m, "warnings": warnings_for(m), "checked": ["size", "sharpness", "brightness", "contrast"]}
