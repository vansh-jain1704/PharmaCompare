"""
OCR text extraction, using EasyOCR (as specified in the PPT).

The EasyOCR Reader takes ~15-20s to load into memory the first time it's
used in a running process (it's a neural network). To avoid paying that
cost on every request, we load it once and keep it in memory for as long
as the Flask process runs (a module-level singleton).
"""
import logging
import sys
import threading

import numpy as np
import pypdfium2 as pdfium
import easyocr

from app.config import Config
from app.services import cloud_ocr_service

logger = logging.getLogger(__name__)

PROVIDER_CLOUD = "cloud"
PROVIDER_EASYOCR = "easyocr"

_reader = None
_reader_lock = threading.Lock()

# Below this AVERAGE confidence, we treat the whole prescription as too
# unclear to trust - this is our implementation of the PPT flowchart's
# "Is Prescription Image Clear?" check. It's a pragmatic proxy (EasyOCR's
# own confidence score), not true image-quality/blur analysis.
MIN_CONFIDENCE = 0.35

# Below this PER-LINE confidence, we still keep the line (the image overall
# was readable) but flag that specific line as uncertain rather than
# silently presenting a shaky reading as fact.
LINE_UNCERTAIN_THRESHOLD = 0.55


def _fix_windows_console_encoding():
    # EasyOCR's own download-progress bar prints Unicode block characters
    # ('█'). Windows consoles default to the cp1252 codec, which
    # cannot encode them and crashes with UnicodeEncodeError. Forcing
    # UTF-8 on stdout/stderr avoids that crash.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def get_reader():
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                _fix_windows_console_encoding()
                _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


def _reading_geometry(results):
    """
    Works out which way the text runs on the page.

    A bounding box's first two vertices follow the text's own baseline, so
    summing v0 -> v1 over every word gives the page's reading direction.
    Prescriptions get photographed sideways constantly, and when they are,
    grouping by vertical position welds the entire page into a handful of
    mega-lines: every medicine ends up in one blob alongside "Name" and
    "Diagnosis", and the whole thing is then discarded as letterhead.

    Returns (along, across, direction):
      along     - index of the coordinate text advances along (0=x, 1=y)
      across    - the other one, i.e. the axis that separates lines
      direction - +1 or -1, whether that advance is increasing or decreasing
    """
    dx = dy = 0.0
    for box, text, _ in results:
        if len(box) < 2 or not str(text).strip():
            continue
        dx += box[1][0] - box[0][0]
        dy += box[1][1] - box[0][1]

    if abs(dy) > abs(dx):
        # Text runs vertically. Lines then advance along x, opposite in sign
        # to the baseline, so that the page still reads in its natural order.
        return 1, 0, (1 if dy >= 0 else -1)
    return 0, 1, (1 if dx >= 0 else -1)


def _group_into_rows(results):
    """
    Rejoins detections that sit on the SAME physical line of the page.

    EasyOCR returns each visually separated chunk of text as its own
    detection, so one printed line - "Tab Dolo 650   twice daily x 5 days" -
    comes back as three unrelated fragments. Matching then sees a medicine
    with no dosage attached, and the dosage fragments look like junk. Since
    EasyOCR already tells us where each chunk sits on the page, grouping by
    vertical position reconstructs the line as printed.

    A rebuilt row carries two different judgements, and they must not be
    collapsed into one number:
      - `confidence` is a length-weighted average of its fragments, i.e. how
        well the row was read overall. This is what the readability gate
        averages, so it has to stay comparable to a per-fragment score.
        Using the row's WORST fragment here instead dragged the whole-page
        average down far enough to reject scans that read fine before.
      - `uncertain` stays pessimistic: if ANY fragment was shaky, the row is
        flagged, so nothing dubious is quietly presented as solid.
    """
    if not results:
        return []

    along, across, direction = _reading_geometry(results)

    boxed = []
    for box, text, conf in results:
        if not str(text).strip():
            continue
        across_values = [point[across] for point in box]
        boxed.append({
            "text": text,
            "conf": float(conf),
            # Which line this chunk sits on, and where along that line.
            "centre": sum(across_values) / len(across_values),
            "height": max(across_values) - min(across_values),
            "x": direction * min(point[along] for point in box),
        })
    if not boxed:
        return []

    # Lines advance opposite to the baseline when the page is sideways, so
    # that a rotated prescription still reads in its original order.
    line_order = 1 if along == 0 else -direction
    boxed.sort(key=lambda d: line_order * d["centre"])
    typical_height = sorted(d["height"] for d in boxed)[len(boxed) // 2]
    # Two chunks belong to the same printed line when their centres are
    # closer together than roughly half a line of text.
    tolerance = max(typical_height * 0.6, 1.0)

    rows = [[boxed[0]]]
    for chunk in boxed[1:]:
        if abs(chunk["centre"] - rows[-1][-1]["centre"]) <= tolerance:  # same line
            rows[-1].append(chunk)
        else:
            rows.append([chunk])

    grouped = []
    for row in rows:
        row.sort(key=lambda d: d["x"])
        weights = [max(len(d["text"]), 1) for d in row]
        confidence = sum(d["conf"] * w for d, w in zip(row, weights)) / sum(weights)
        grouped.append({
            "text": " ".join(d["text"] for d in row),
            "confidence": round(confidence, 4),
            "uncertain": any(d["conf"] < LINE_UNCERTAIN_THRESHOLD for d in row),
        })
    return grouped


def _pdf_first_page_to_array(pdf_path):
    """
    Renders page 1 to an array, then closes the document.

    The close matters: pdfium keeps the PDF open, and on Windows an open
    handle makes the file undeletable - so leaving it open would leak a lock
    on every uploaded PDF for the lifetime of the process, and silently
    defeat file cleanup when a user deletes that prescription.
    """
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        bitmap = pdf[0].render(scale=2.0)
        return np.array(bitmap.to_pil().convert("RGB"))
    finally:
        pdf.close()


def _empty_result(provider):
    return {"text": "", "lines": [], "confidence": 0.0, "readable": False, "provider": provider}


def _build_result(word_triples, provider):
    """
    Turns (box, text, confidence) triples - from either OCR engine - into the
    single shape the rest of the pipeline consumes. Both engines go through
    the same line grouping, so a cloud read and a local read are structurally
    identical downstream.
    """
    if not word_triples:
        return _empty_result(provider)
    lines = _group_into_rows(word_triples)
    if not lines:
        return _empty_result(provider)

    avg_confidence = round(sum(line["confidence"] for line in lines) / len(lines), 4)
    return {
        "text": "\n".join(line["text"] for line in lines),
        "lines": lines,
        "confidence": avg_confidence,
        "readable": avg_confidence >= MIN_CONFIDENCE,
        "provider": provider,
    }


def extract_text_easyocr(file_path, file_ext):
    """Local OCR. Always available, weak on handwriting."""
    reader = get_reader()
    source = _pdf_first_page_to_array(file_path) if file_ext == "pdf" else file_path
    # (bool(...) inside the grouper: EasyOCR confidences are numpy float32,
    # and comparing them yields numpy.bool_, which json.dumps() can't handle.)
    return _build_result(reader.readtext(source), PROVIDER_EASYOCR)


def extract_text(file_path, file_ext):
    """
    Runs OCR on an uploaded prescription file (image or PDF's first page).

    Cloud OCR runs first when credentials are configured, because local
    EasyOCR cannot read handwritten prescriptions. If the cloud call fails
    for ANY reason - no key, no network, quota, malformed response - this
    falls back to EasyOCR so uploads keep working and the manual
    identification flow still has lines to work with. Set OCR_PROVIDER to
    pin one engine ("cloud" refuses to fall back; "easyocr" never calls out).

    Returns a dict:
      - text: raw extracted text, one detected line per line (unmodified,
        never auto-corrected)
      - lines: per-line objects carrying that line's own confidence, so
        uncertain readings can be flagged individually instead of hidden
        inside a single average
      - confidence: the average across lines, used to decide readability
      - readable: whether the average clears MIN_CONFIDENCE
      - provider: which engine actually produced this result
      - fallback: True only when the cloud engine was tried, failed, and EasyOCR
        produced this result instead (absent otherwise)
    """
    provider = (Config.OCR_PROVIDER or "auto").lower()

    if provider == PROVIDER_EASYOCR:
        return extract_text_easyocr(file_path, file_ext)

    wants_cloud = provider == PROVIDER_CLOUD or (provider == "auto" and cloud_ocr_service.is_configured())
    if not wants_cloud:
        return extract_text_easyocr(file_path, file_ext)

    try:
        return _build_result(cloud_ocr_service.extract_words(file_path, file_ext), PROVIDER_CLOUD)
    except Exception:
        if provider == PROVIDER_CLOUD:
            # Explicitly pinned to cloud: surface the failure rather than
            # quietly returning a worse result the caller didn't ask for.
            raise
        # same diagnostics as logger.exception (message and full traceback), with the API key removed
        logger.error("Cloud OCR failed; falling back to EasyOCR: %s", cloud_ocr_service.redacted_traceback(sys.exc_info()[1]))
        result = extract_text_easyocr(file_path, file_ext)
        result["fallback"] = True
        return result
