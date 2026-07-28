"""Isolated OpenCV 5 + PaddleOCR worker. Writes exactly one JSON object to stdout."""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

import cv2
import fitz
import numpy as np
from paddleocr import PaddleOCR


def _result_payload(result) -> dict:
    value = getattr(result, "json", result)
    if callable(value):
        value = value()
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict) and "res" in value:
        value = value["res"]
    return value if isinstance(value, dict) else {}


def _order_quad(points: np.ndarray) -> np.ndarray:
    result = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    result[0] = points[np.argmin(sums)]
    result[2] = points[np.argmax(sums)]
    result[1] = points[np.argmin(differences)]
    result[3] = points[np.argmax(differences)]
    return result


def _document_warp(image: np.ndarray) -> tuple[np.ndarray, bool]:
    """Correct a photographed page only when a dominant, page-like quad is unambiguous."""
    height, width = image.shape[:2]
    scale = min(1.0, 1400 / max(height, width))
    preview = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image.copy()
    gray = cv2.cvtColor(preview, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    page_area = preview.shape[0] * preview.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        perimeter = cv2.arcLength(contour, True)
        quad = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(quad) != 4 or cv2.contourArea(quad) < page_area * 0.55:
            continue
        points = _order_quad(quad.reshape(4, 2).astype(np.float32) / scale)
        top, right, bottom, left = points
        target_width = int(max(np.linalg.norm(right - top), np.linalg.norm(bottom - left)))
        target_height = int(max(np.linalg.norm(left - top), np.linalg.norm(bottom - right)))
        if target_width < 600 or target_height < 600:
            continue
        ratio = target_width / target_height
        if not 0.55 <= ratio <= 1.8:
            continue
        target = np.array(
            [
                [0, 0],
                [target_width - 1, 0],
                [target_width - 1, target_height - 1],
                [0, target_height - 1],
            ],
            dtype=np.float32,
        )
        matrix = cv2.getPerspectiveTransform(points, target)
        return cv2.warpPerspective(
            image, matrix, (target_width, target_height), borderValue=(255, 255, 255)
        ), True
    return image, False


def _deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    coordinates = np.column_stack(np.where(binary > 0))
    if len(coordinates) < 200:
        return gray, 0.0
    angle = cv2.minAreaRect(coordinates[:, ::-1].astype(np.float32))[-1]
    angle = angle - 90 if angle > 45 else angle
    if not math.isfinite(angle) or abs(angle) < 0.25 or abs(angle) > 12:
        return gray, 0.0
    height, width = gray.shape
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(
        gray,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    ), float(angle)


def _preprocess(image: np.ndarray) -> tuple[np.ndarray, dict]:
    warped, perspective = _document_warp(image)
    height, width = warped.shape[:2]
    if max(height, width) < 1800:
        scale = 1800 / max(height, width)
        warped = cv2.resize(warped, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    elif max(height, width) > 3600:
        scale = 3600 / max(height, width)
        warped = cv2.resize(warped, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 7, 7, 21)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gray, angle = _deskew(gray)
    # Paddle's recognizer benefits from normalized grayscale while retaining
    # antialiased glyph edges.
    normalized = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    return normalized, {"perspective_corrected": perspective, "deskew_degrees": round(angle, 3)}


def _source_pages(path: Path) -> list[np.ndarray]:
    if path.suffix.lower() == ".pdf":
        document = fitz.open(path)
        try:
            pages = []
            for page in document:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False)
                pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                    pixmap.height, pixmap.width, pixmap.n
                )
                pages.append(cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR))
            return pages
        finally:
            document.close()
    image = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("opencv_document_decode_failed")
    return [image]


def _ocr(engine: PaddleOCR, paths: list[Path]) -> list[dict]:
    best: dict[str, dict] = {}
    for path in paths:
        for result in engine.predict(str(path)):
            payload = _result_payload(result)
            texts = payload.get("rec_texts") or []
            scores = payload.get("rec_scores") or []
            for index, raw in enumerate(texts):
                text = str(raw).strip()
                if not text:
                    continue
                confidence = float(scores[index]) if index < len(scores) else 0.0
                key = " ".join(text.casefold().split())
                if key not in best or confidence > best[key]["confidence"]:
                    best[key] = {"text": text, "confidence": confidence}
    return list(best.values())


def _merge_lines(target: dict[str, dict], lines: list[dict]) -> None:
    for item in lines:
        key = " ".join(str(item.get("text", "")).casefold().split())
        if key and (
            key not in target or float(item.get("confidence", 0)) > target[key]["confidence"]
        ):
            target[key] = item


def _run(path: Path, model_choices: tuple[tuple[str, str], ...]) -> dict:
    if int(cv2.__version__.split(".", 1)[0]) < 5:
        raise RuntimeError("opencv5_runtime_required")
    pages = _source_pages(path)
    telemetry = []
    with tempfile.TemporaryDirectory(prefix="caresync-opencv5-") as directory:
        processed_paths = []
        for index, page in enumerate(pages):
            processed, page_telemetry = _preprocess(page)
            enhanced = Path(directory) / f"page-{index + 1}-enhanced.png"
            gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
            binary_image = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 13
            )
            binary = Path(directory) / f"page-{index + 1}-binary.png"
            if not cv2.imwrite(str(enhanced), processed, [cv2.IMWRITE_PNG_COMPRESSION, 3]):
                raise RuntimeError("opencv_preprocessed_page_write_failed")
            if not cv2.imwrite(str(binary), binary_image, [cv2.IMWRITE_PNG_COMPRESSION, 3]):
                raise RuntimeError("opencv_binary_page_write_failed")
            processed_paths.extend((enhanced, binary))
            telemetry.append(
                {
                    "page": index + 1,
                    **page_telemetry,
                    "width": processed.shape[1],
                    "height": processed.shape[0],
                }
            )
        merged: dict[str, dict] = {}
        successful_models = []
        last_error: Exception | None = None
        for models in model_choices:
            try:
                engine = PaddleOCR(
                    text_detection_model_name=models[0],
                    text_recognition_model_name=models[1],
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
                _merge_lines(merged, _ocr(engine, processed_paths))
                successful_models.append("+".join(models))
            except Exception as exc:
                last_error = exc
        if not successful_models:
            raise last_error or RuntimeError("ocr_models_unavailable")
    return {
        "engine": "opencv5+paddleocr",
        "vision": {
            "library": "OpenCV",
            "version": cv2.__version__,
            "pipeline": "document-v2-fused",
            "variants_per_page": 2,
            "pages": telemetry,
        },
        "model": "fusion:" + "|".join(successful_models),
        "models": successful_models,
        "lines": list(merged.values()),
    }


def main() -> int:
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        return 2
    path = Path(sys.argv[1])
    choices = (
        ("PP-OCRv6_tiny_det", "PP-OCRv6_tiny_rec"),
        ("PP-OCRv5_mobile_det", "latin_PP-OCRv5_mobile_rec"),
    )
    try:
        print(json.dumps(_run(path, choices)))
        return 0
    except Exception as exc:  # worker boundary reports failure only through its exit code
        print(type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
