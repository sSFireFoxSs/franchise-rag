"""LLM 호출 추상화 — provider(ollama/openai)를 바꿔치기 가능하게.

슬롯추출(nlu.py)과 답변생성(answer.py) 둘 다 call_llm()/call_llm_json() 하나만 보고
어떤 provider를 쓰는지 모른다. `.env`의 LLM_PROVIDER 값만 바꾸면 전체가 갈아탄다.
"""
import json
import re

import requests

from . import config

logger = None  # utils.get_logger는 handler를 파일에도 붙이는데, 이 모듈은 여러 스크립트/
                # 앱에서 재사용되므로 로거 이름 충돌을 피하려고 호출부에서 필요시 주입한다.


class LLMError(RuntimeError):
    """LLM 호출/파싱 실패. 호출부(nlu.py 등)가 이 예외를 보고 "커버불가"나 재시도 등을 결정한다."""


def call_llm(messages: list[dict], *, json_mode: bool = False, temperature: float = 0.0) -> str:
    """messages: [{"role": "system"|"user"|"assistant", "content": str}, ...]
    반환값: 모델의 응답 텍스트(문자열). provider에 따라 Ollama 또는 OpenAI를 호출한다."""
    if config.LLM_PROVIDER == "ollama":
        return _call_ollama(messages, json_mode=json_mode, temperature=temperature)
    elif config.LLM_PROVIDER == "openai":
        return _call_openai(messages, json_mode=json_mode, temperature=temperature)
    else:
        raise LLMError(f"알 수 없는 LLM_PROVIDER: {config.LLM_PROVIDER!r} (ollama 또는 openai만 지원)")


def call_llm_json(messages: list[dict], *, temperature: float = 0.0) -> dict:
    """JSON 객체 응답을 강제하고 파싱까지 해서 dict로 반환한다. 파싱 실패 시 LLMError."""
    raw = call_llm(messages, json_mode=True, temperature=temperature)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 모델이 코드블록(```json ... ```)이나 설명을 덧붙인 경우 가장 바깥 {...}만 추출해서 재시도.
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    raise LLMError(f"LLM 응답을 JSON으로 파싱하지 못함. 원문(앞 500자): {raw[:500]!r}")


def _call_ollama(messages, *, json_mode: bool, temperature: float) -> str:
    url = f"{config.OLLAMA_HOST}/api/chat"
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": config.OLLAMA_THINK,
        # 2026-09-15 (작업로그 (35)): num_ctx를 명시 안 하면 모델 기본 컨텍스트 윈도가 작아서
        # (실측 4096 추정) 표/금액 컨텍스트가 큰 서술형 질문에서 답변이 중간에 잘리는
        # 문제(done_reason="length")가 있었음 — config.OLLAMA_NUM_CTX 참고.
        "options": {"temperature": temperature, "num_ctx": config.OLLAMA_NUM_CTX},
    }
    if json_mode:
        payload["format"] = "json"
    try:
        resp = requests.post(url, json=payload, timeout=config.LLM_TIMEOUT_SEC)
    except requests.exceptions.RequestException as e:
        raise LLMError(
            f"Ollama 호출 실패({url}): {type(e).__name__}: {e} — "
            f"`ollama serve`가 실행 중인지, 모델 '{config.OLLAMA_MODEL}'이 "
            f"`ollama list`에 있는지 확인할 것."
        ) from e
    if resp.status_code != 200:
        raise LLMError(f"Ollama 응답 오류 (status={resp.status_code}): {resp.text[:500]}")
    data = resp.json()
    content = data.get("message", {}).get("content")
    if content is None:
        raise LLMError(f"Ollama 응답에 message.content가 없음: {data}")
    return content


def _call_openai(messages, *, json_mode: bool, temperature: float) -> str:
    if not config.OPENAI_API_KEY:
        raise LLMError("LLM_PROVIDER=openai인데 .env에 OPENAI_API_KEY가 없음.")
    try:
        from openai import OpenAI
    except ImportError as e:
        raise LLMError("openai 패키지가 설치되어 있지 않음 (pip install openai).") from e

    client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
            timeout=config.LLM_TIMEOUT_SEC,
            **kwargs,
        )
    except Exception as e:  # openai 라이브러리 예외 계층을 다 알 필요 없이 통일해서 올림
        raise LLMError(f"OpenAI 호출 실패: {type(e).__name__}: {e}") from e
    content = resp.choices[0].message.content
    if content is None:
        raise LLMError(f"OpenAI 응답에 content가 없음: {resp}")
    return content
