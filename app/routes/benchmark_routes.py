"""AI provider benchmark — image generation and OCR side-by-side comparison.

Routes:
    GET  /backoffice/benchmark       — UI page
    POST /backoffice/benchmark/run   — parallel execution, returns JSON
"""
from __future__ import annotations

import base64
import concurrent.futures
import json
import os
import time

from flask import Blueprint, jsonify, render_template, request

# Pre-import all openai sub-modules at load time — the library uses lazy imports
# that deadlock when multiple threads trigger the same import simultaneously.
try:
    import openai  # noqa: F401
    import openai.resources.chat  # noqa: F401
    import openai.resources.chat.completions  # noqa: F401
    import openai.resources.images  # noqa: F401
except ImportError:
    pass

bench_bp = Blueprint('benchmark', __name__, url_prefix='/backoffice/benchmark')


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(fn) -> dict:
    """Execute fn, capture result + elapsed ms + any error."""
    t0 = time.time()
    try:
        result = fn()
        return {'ok': True, 'time_ms': int((time.time() - t0) * 1000), **result}
    except Exception as exc:
        return {'ok': False, 'time_ms': int((time.time() - t0) * 1000), 'error': str(exc)}


# ── Image Generation ──────────────────────────────────────────────────────────

def _gen_dalle(prompt: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    resp = client.images.generate(
        model='dall-e-3',
        prompt=prompt,
        n=1,
        size='1024x1024',
        response_format='b64_json',
    )
    b64 = resp.data[0].b64_json
    revised = resp.data[0].revised_prompt or ''
    return {'image': f'data:image/png;base64,{b64}', 'note': revised[:120] if revised else ''}


def _gen_imagen(prompt: str) -> dict:
    from google import genai
    from google.genai import types as gtypes
    client = genai.Client(api_key=os.environ['GOOGLE_API_KEY'])
    resp = client.models.generate_images(
        model='imagen-4.0-generate-001',
        prompt=prompt,
        config=gtypes.GenerateImagesConfig(number_of_images=1),
    )
    image_bytes = resp.generated_images[0].image.image_bytes
    b64 = base64.b64encode(image_bytes).decode()
    return {'image': f'data:image/png;base64,{b64}', 'note': ''}


# ── OCR ───────────────────────────────────────────────────────────────────────

def _ocr_gpt(image_b64: str, mime: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    resp = client.chat.completions.create(
        model='gpt-4o',
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{image_b64}'}},
                {'type': 'text', 'text': 'Extract all text from this image exactly as it appears. Return only the extracted text, preserve layout and line breaks.'},
            ],
        }],
        max_tokens=2000,
    )
    return {'text': resp.choices[0].message.content}


def _ocr_gemini(image_b64: str, mime: str) -> dict:
    from google import genai
    from google.genai import types as gtypes
    client = genai.Client(api_key=os.environ['GOOGLE_API_KEY'])
    image_bytes = base64.b64decode(image_b64)
    resp = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            gtypes.Part.from_bytes(data=image_bytes, mime_type=mime),
            'Extract all text from this image exactly as it appears. Return only the extracted text, preserve layout and line breaks.',
        ],
    )
    return {'text': resp.text}


def _ocr_vision(image_b64: str) -> dict:
    from google.cloud import vision as gv
    from google.oauth2 import service_account
    creds_info = json.loads(os.environ['GOOGLE_VISION_CREDENTIALS_JSON'])
    credentials = service_account.Credentials.from_service_account_info(creds_info)
    client = gv.ImageAnnotatorClient(credentials=credentials)
    image = gv.Image(content=base64.b64decode(image_b64))
    response = client.document_text_detection(image=image)
    text = response.full_text_annotation.text or ''
    return {'text': text}


# ── Routes ────────────────────────────────────────────────────────────────────

@bench_bp.route('/', methods=['GET'])
def benchmark_page():
    return render_template('backoffice/benchmark.html')


@bench_bp.route('/run', methods=['POST'])
def benchmark_run():
    data = request.get_json(force=True) or {}
    mode = data.get('mode', 'both')       # 'generate' | 'ocr' | 'both'
    prompt = (data.get('prompt') or '').strip()
    image_b64 = data.get('image_b64', '')
    image_mime = data.get('image_mime', 'image/jpeg')

    futures_map: dict[str, concurrent.futures.Future] = {}
    results: dict[str, dict] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        if mode in ('generate', 'both') and prompt:
            futures_map['gen_dalle']  = pool.submit(_run, lambda p=prompt: _gen_dalle(p))
            futures_map['gen_imagen'] = pool.submit(_run, lambda p=prompt: _gen_imagen(p))

        if mode in ('ocr', 'both') and image_b64:
            futures_map['ocr_gpt']    = pool.submit(_run, lambda b=image_b64, m=image_mime: _ocr_gpt(b, m))
            futures_map['ocr_gemini'] = pool.submit(_run, lambda b=image_b64, m=image_mime: _ocr_gemini(b, m))
            futures_map['ocr_vision'] = pool.submit(_run, lambda b=image_b64: _ocr_vision(b))

        for key, future in futures_map.items():
            try:
                results[key] = future.result(timeout=120)
            except concurrent.futures.TimeoutError:
                results[key] = {'ok': False, 'time_ms': 120000, 'error': 'timeout (120s)'}

    return jsonify(results)
