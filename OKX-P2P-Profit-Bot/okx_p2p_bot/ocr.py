from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageEnhance, ImageFilter


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def configure_tesseract(pytesseract_module) -> None:
    candidates = [
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]
    if pytesseract_module.pytesseract.tesseract_cmd:
        configured = Path(pytesseract_module.pytesseract.tesseract_cmd)
        if configured.exists():
            return
    for candidate in candidates:
        if candidate.exists():
            pytesseract_module.pytesseract.tesseract_cmd = str(candidate)
            break
    local_tessdata = PROJECT_ROOT / "tessdata"
    if local_tessdata.exists():
        os.environ["TESSDATA_PREFIX"] = str(local_tessdata)


def choose_language(lang: str) -> str:
    tessdata_dirs = [
        PROJECT_ROOT / "tessdata",
        Path(r"C:\Program Files\Tesseract-OCR\tessdata"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tessdata"),
    ]
    available = set()
    for tessdata_dir in tessdata_dirs:
        if tessdata_dir.exists():
            available.update(path.stem for path in tessdata_dir.glob("*.traineddata"))
    if not available:
        return lang
    requested = [part for part in lang.split("+") if part in available]
    return "+".join(requested) if requested else "eng"


def image_to_text(file: BinaryIO | bytes, lang: str = "vie+eng") -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("Chưa cài pytesseract. Hãy cài requirements.txt và Tesseract OCR.") from exc

    configure_tesseract(pytesseract)
    lang = choose_language(lang)
    data = file if isinstance(file, bytes) else file.read()
    image = Image.open(BytesIO(data))
    try:
        images = [image, preprocess_image(image)]
        chunks: list[str] = []
        for prepared in images:
            chunks.append(image_to_row_text(pytesseract, prepared, lang, psm=6))
            chunks.append(image_to_row_text(pytesseract, prepared, lang, psm=11))
            chunks.append(pytesseract.image_to_string(prepared, lang=lang, config="--psm 6"))
            chunks.append(pytesseract.image_to_string(prepared, lang=lang, config="--psm 11"))
        return "\n".join(chunk for chunk in chunks if chunk.strip())
    except Exception as exc:
        raise RuntimeError(f"OCR thất bại: {exc}") from exc


def preprocess_image(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    width, height = gray.size
    resized = gray.resize((width * 2, height * 2), Image.Resampling.LANCZOS)
    contrasted = ImageEnhance.Contrast(resized).enhance(1.7)
    return contrasted.filter(ImageFilter.SHARPEN)


def image_to_row_text(pytesseract_module, image: Image.Image, lang: str, psm: int) -> str:
    data = pytesseract_module.image_to_data(
        image,
        lang=lang,
        output_type=pytesseract_module.Output.DICT,
        config=f"--psm {psm}",
    )
    rows: dict[tuple[int, int, int], list[tuple[int, str]]] = {}
    for idx, text in enumerate(data.get("text", [])):
        text = (text or "").strip()
        if not text:
            continue
        key = (data["block_num"][idx], data["par_num"][idx], data["line_num"][idx])
        rows.setdefault(key, []).append((data["left"][idx], text))
    lines = []
    for words in rows.values():
        ordered = [text for _, text in sorted(words, key=lambda item: item[0])]
        lines.append(" ".join(ordered))
    return "\n".join(lines)
