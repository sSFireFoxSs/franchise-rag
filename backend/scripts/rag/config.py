"""RAG 설정값 — 전부 .env 또는 기본값에서 읽는다. 여기 말고 다른 곳에서 os.environ을
직접 읽지 않는다(설정이 여기저기 흩어지면 나중에 FastAPI로 옮길 때 놓치기 쉬움).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # scripts/ (utils 임포트용)

from utils import DATA_DIR, LOG_DIR, PROJECT_ROOT  # noqa: E402

# --- LLM provider 추상화 ---
# 슬롯추출(1단계)/답변생성(4단계) 둘 다 이 설정을 공유한다. call_llm()이 이 값을 보고
# Ollama 또는 OpenAI 중 하나로 실제 호출을 보낸다 (scripts/rag/llm.py 참고).
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# 2026-09-14: 사용자 환경에 `ollama pull`로 이미 받아져 있는 모델이 qwen3.5:9b라서
# (사용자가 예시로 든 qwen2.5:7b-instruct가 아니라) 기본값을 실제 설치된 모델로 맞춤.
# .env에 OLLAMA_MODEL을 넣어두면 그걸 우선한다.
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")
# 2026-09-14 실측: qwen3.5:9b가 기본적으로 "thinking"(추론 과정을 먼저 길게 생성)을 켜고
# 있어서, 슬롯추출 같은 짧은 JSON 응답 하나에도 85초(3,159 추론 토큰)가 걸렸음. think를
# 꺼보니(Ollama가 이 파라미터를 지원) 같은 질문이 1.8초로 줄고 결과도 동일하게 정확했음 —
# 이 프로젝트의 프롬프트들은 애초에 추론이 필요 없는 구조화 출력/근거 요약이라 thinking이
# 지연만 키우고 이득이 없다고 판단, 기본값을 끔. 필요하면 .env에서 true로 되돌릴 수 있음.
OLLAMA_THINK = os.environ.get("OLLAMA_THINK", "false").strip().lower() in ("1", "true", "yes")
# 2026-09-15 (작업로그 (35)) 실측: num_ctx를 안 주면 Ollama가 이 모델의 기본 컨텍스트
# 윈도(4096으로 추정 — prompt_eval_count=3888일 때 eval_count가 정확히 208로 끊김을 확인)를
# 쓰는데, 서술형 답변(표/금액 컨텍스트 포함, 작업로그 (34)(35))이 프롬프트만으로 이미
# 4천 토큰 가까이 먹는 경우가 있어서 답변이 문장 중간에 잘리는 문제(done_reason="length")가
# 있었음. 답변용 여유를 넉넉히 남기도록 상향.
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or None  # 커스텀 엔드포인트용, 없으면 기본 OpenAI

LLM_TIMEOUT_SEC = float(os.environ.get("LLM_TIMEOUT_SEC", "90"))

# --- 임베딩/벡터DB ---
EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "nlpai-lab/KURE-v1")
EMBEDDING_DEVICE = os.environ.get("EMBEDDING_DEVICE", "cuda")  # GPU 없으면 .env에서 "cpu"로 덮어쓰기
# 2026-09-14: CPU 실측 12시간+ -> CUDA torch(cu128) 설치 후 GPU(RTX 4070)로 전환, 기본값을
# cuda로 바꿈. GPU 없는 환경에서 이 프로젝트를 열면 .env에 EMBEDDING_DEVICE=cpu를 추가할 것.
EMBEDDING_BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", "32"))
# KURE-v1 기본 max_seq_length는 8192(토큰)인데, 실측 결과 서술형 카테고리 조항 텍스트의
# 99%가 1,148자 이하(중앙값 153자)라 8192는 과함 — 드물게 섞인 9천자대 이상치 텍스트가
# attention 비용을 이차적으로 키워서 배치 전체를 느리게 만드는 걸 막기 위해 상한을 둔다.
# (토큰 수는 글자 수보다 조금 적음 — 1024토큰이면 실질적으로 p99인 1,148자보다 넉넉함)
EMBEDDING_MAX_SEQ_LENGTH = int(os.environ.get("EMBEDDING_MAX_SEQ_LENGTH", "1024"))

VECTORDB_DIR = DATA_DIR / "vectordb"
# 컬렉션 이름에 임베딩 모델을 박아둔다 — 나중에 임베딩 모델을 바꾸면(예: KURE-v2) 이름이
# 자동으로 갈려서 차원 수가 다른 벡터가 같은 컬렉션에 섞이는 사고를 방지한다.
VECTORDB_COLLECTION = os.environ.get("VECTORDB_COLLECTION", "clauses_kure_v1")

# --- 검색 파라미터 ---
VECTOR_TOP_K = int(os.environ.get("VECTOR_TOP_K", "5"))

# --- 데이터 경로 (utils.DATA_DIR 기준, 03_extract_clauses.py / app.py와 동일) ---
CLAUSES_GZ_PATH = DATA_DIR / "disclosure" / "clauses.jsonl.gz"
CLAUSES_PATH = DATA_DIR / "disclosure" / "clauses.jsonl"
BRAND_PATH = DATA_DIR / "brand" / "brand_unified.jsonl"

__all__ = [
    "PROJECT_ROOT", "DATA_DIR", "LOG_DIR",
    "LLM_PROVIDER", "OLLAMA_HOST", "OLLAMA_MODEL", "OLLAMA_THINK", "OLLAMA_NUM_CTX",
    "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL", "LLM_TIMEOUT_SEC",
    "EMBEDDING_MODEL_NAME", "EMBEDDING_DEVICE", "EMBEDDING_BATCH_SIZE",
    "VECTORDB_DIR", "VECTORDB_COLLECTION", "VECTOR_TOP_K",
    "CLAUSES_GZ_PATH", "CLAUSES_PATH", "BRAND_PATH",
]
