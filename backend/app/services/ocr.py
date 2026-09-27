import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

import httpx

from app.core.config import settings


def extract_text_from_image(image_bytes: bytes, file_name: str) -> tuple[Optional[str], str]:
    python_text, python_message = _try_local_paddleocr_python(image_bytes, file_name)
    if python_text:
        return python_text, python_message

    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    local_text, local_message = _try_local_ocr(image_base64, file_name)
    if local_text:
        return local_text, local_message

    provider = settings.ocr_provider.lower().strip()
    if provider in {"", "none", "disabled"}:
        return None, f"{python_message} {local_message} 未配置远程 OCR API。"
    if not settings.ocr_endpoint:
        return None, f"{python_message} {local_message} 远程 OCR 服务地址未配置，请设置 ASSET_MANAGER_OCR_ENDPOINT。"

    try:
        if provider in {"paddle", "paddleocr", "paddleocr_http"}:
            text = _call_paddleocr_http(_endpoint(), image_base64, file_name, settings.ocr_timeout_seconds, _auth_headers())
        elif provider in {"deepseek", "deepseek_ocr", "openai_compatible_vision"}:
            text = _call_openai_compatible_ocr(image_base64)
        else:
            return None, f"不支持的 OCR_PROVIDER：{settings.ocr_provider}"
    except httpx.HTTPError as exc:
        return None, f"OCR 服务请求失败：{exc}"
    except Exception as exc:
        return None, f"OCR 服务解析失败：{exc}"

    cleaned = text.strip()
    if not cleaned:
        return None, "OCR 服务未返回可用文字，请换一张更清晰的持仓截图。"
    return cleaned, "远程 OCR 识别完成。"


def _try_local_paddleocr_python(image_bytes: bytes, file_name: str) -> tuple[Optional[str], str]:
    python_path = settings.ocr_local_python_path
    if not python_path:
        return None, "未配置本地 PaddleOCR Python 环境。"
    python = Path(python_path)
    if not python.exists():
        return None, f"本地 PaddleOCR Python 不存在：{python_path}。"

    cache_home = Path(settings.ocr_local_python_home) if settings.ocr_local_python_home else settings.ocr_cache_dir
    upload_dir = settings.upload_dir
    cache_home.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file_name).suffix or ".png"
    temp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(dir=upload_dir, suffix=suffix, delete=False) as temp_file:
            temp_file.write(image_bytes)
            temp_path = temp_file.name
        runner = Path(__file__).with_name("paddleocr_runner.py")
        env = os.environ.copy()
        env["HOME"] = str(cache_home)
        env["PADDLE_PDX_CACHE_HOME"] = str(cache_home / ".paddlex")
        env["XDG_CACHE_HOME"] = str(cache_home / ".cache")
        env["PYTHONIOENCODING"] = "utf-8"
        completed = subprocess.run(
            [str(python), str(runner), temp_path],
            capture_output=True,
            text=True,
            timeout=settings.ocr_local_python_timeout_seconds,
            env=env,
            check=False,
        )
        payload = _last_json_line(completed.stdout)
        if payload and payload.get("ok") is True:
            text = str(payload.get("text") or "").strip()
            if text:
                return text, "本地 PaddleOCR Python 识别完成。"
            return None, "本地 PaddleOCR Python 未返回文字。"
        error = payload.get("error") if payload else (completed.stderr or completed.stdout)
        return None, f"本地 PaddleOCR Python 失败：{str(error).strip()[:500]}"
    except subprocess.TimeoutExpired:
        return None, "本地 PaddleOCR Python 超时。"
    except Exception as exc:
        return None, f"本地 PaddleOCR Python 调用失败：{exc}"
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass


def _try_local_ocr(image_base64: str, file_name: str) -> tuple[Optional[str], str]:
    errors: list[str] = []
    for endpoint in settings.ocr_local_endpoints:
        try:
            text = _call_paddleocr_http(endpoint, image_base64, file_name, settings.ocr_local_timeout_seconds, {})
        except httpx.HTTPError as exc:
            errors.append(f"{endpoint}: {exc.__class__.__name__}")
            continue
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")
            continue
        cleaned = text.strip()
        if cleaned:
            return cleaned, f"本地 OCR 识别完成：{endpoint}"
        errors.append(f"{endpoint}: 未返回文字")
    if not settings.ocr_local_endpoints:
        return None, "未配置本地 OCR 服务地址。"
    return None, f"未发现可用本地 OCR 服务（{'; '.join(errors[:3])}）。"


def _call_paddleocr_http(
    endpoint: str,
    image_base64: str,
    file_name: str,
    timeout_seconds: float,
    headers: dict[str, str],
) -> str:
    payload = {
        "imageBase64": image_base64,
        "image": image_base64,
        "fileName": file_name,
    }
    response = _client(timeout_seconds).post(endpoint, json=payload, headers=headers)
    response.raise_for_status()
    return _extract_text_from_payload(response.json())


def _call_openai_compatible_ocr(image_base64: str) -> str:
    model = settings.ocr_model or "deepseek-ocr"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请只提取这张持仓截图中的文字，保留基金代码、名称、金额、份额、收益、净值等数字，不要分析或给投资建议。",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                ],
            }
        ],
        "temperature": 0,
    }
    response = _client(settings.ocr_timeout_seconds).post(
        _endpoint(),
        json=payload,
        headers={**_auth_headers(), "Content-Type": "application/json"},
    )
    response.raise_for_status()
    body = response.json()
    choices = body.get("choices") if isinstance(body, dict) else None
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content
    return _extract_text_from_payload(body)


def _extract_text_from_payload(payload: Any) -> str:
    direct = _first_text(payload, ["text", "ocrText", "rawText", "content", "rec_text"])
    if direct:
        return direct
    fragments: list[str] = []
    _collect_text_fragments(payload, fragments)
    return "\n".join(fragment for fragment in fragments if fragment.strip())


def _collect_text_fragments(value: Any, fragments: list[str]) -> None:
    if isinstance(value, dict):
        direct = _first_text(value, ["text", "ocrText", "rawText", "content", "rec_text"])
        if direct:
            fragments.append(direct)
            return
        for item in value.values():
            _collect_text_fragments(item, fragments)
    elif isinstance(value, list):
        for item in value:
            _collect_text_fragments(item, fragments)
    elif isinstance(value, str):
        fragments.append(value)


def _first_text(payload: Any, keys: list[str]) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _auth_headers() -> dict[str, str]:
    if not settings.ocr_api_key:
        return {}
    return {"Authorization": f"Bearer {settings.ocr_api_key}"}


def _client(timeout_seconds: float) -> httpx.Client:
    return httpx.Client(timeout=timeout_seconds)


def _endpoint() -> str:
    return str(settings.ocr_endpoint)


def _last_json_line(output: str) -> Optional[dict[str, Any]]:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None
