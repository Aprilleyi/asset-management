import json
import sys
from typing import Any


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "image path is required"}, ensure_ascii=False))
        return 2
    image_path = sys.argv[1]
    try:
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            lang="ch",
        )
        if hasattr(ocr, "predict"):
            result = ocr.predict(image_path)
        else:
            result = ocr.ocr(image_path, cls=True)
        fragments: list[str] = []
        _collect_text(result, fragments)
        text = "\n".join(fragment for fragment in fragments if fragment.strip())
        print(json.dumps({"ok": True, "text": text}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


def _collect_text(value: Any, fragments: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for key in ["rec_text", "text", "ocr_text"]:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                fragments.append(item.strip())
        for key in ["rec_texts", "texts"]:
            item = value.get(key)
            if isinstance(item, list):
                for text in item:
                    if isinstance(text, str) and text.strip():
                        fragments.append(text.strip())
        for item in value.values():
            _collect_text(item, fragments)
    elif isinstance(value, list):
        if len(value) >= 2 and isinstance(value[1], tuple) and value[1] and isinstance(value[1][0], str):
            fragments.append(value[1][0].strip())
        for item in value:
            _collect_text(item, fragments)
    elif isinstance(value, str) and value.strip():
        fragments.append(value.strip())


if __name__ == "__main__":
    raise SystemExit(main())
