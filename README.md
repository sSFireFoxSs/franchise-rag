<p align="center"><b>franchise-rag</b></p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="python">
  <img src="https://img.shields.io/badge/FastAPI-backend-009688" alt="fastapi">
  <img src="https://img.shields.io/badge/Next.js-frontend-black" alt="nextjs">
</p>

<p align="center">
  <a href="#4-실행">실행</a> ·
  <a href="#3-데이터-파이프라인">데이터 파이프라인</a> ·
  <a href="#6-평가">평가</a> ·
  <a href="#7-한계">한계</a> ·
  <a href="docs/DESIGN.md">설계 문서</a>
</p>

**예비 창업자를 위한 가맹사업 정보공개서 비교·질의응답 서비스**

브랜드마다 제각각인 정보공개서 조항(가맹비, 보증금, 필수구입물품, 위약금, 계약해지, 법 위반 이력 등)을 자연어로 묻고, 여러 브랜드를 나란히 비교해요. 모든 답에는 원문 조항 출처가 붙어요.

```
"비비큐랑 종로김밥 보증금 비교해줘"
   ▼
브랜드 정규화 → 질문 분류 → 구조화 값 조회 / 조항 벡터 검색 → 숫자 검증된 답변 + 출처 원문
```

---

## 1. 어떤 문제를 푸나요

| 문제 | 예 |
|---|---|
| **같은 항목도 브랜드마다 표현이 달라요** | 「위약금」을 「손해배상」, 「필수구입물품」을 「구입요구 품목」으로 적어요 |
| **금액 단위가 숨어 있어요** | 칸에는 「5,500」만 있고 단위(천원)는 표 캡션에만 있어요. 그대로 읽으면 1,000배 틀려요 |
| **LLM이 숫자를 지어낼 수 있어요** | 가맹비 같은 숫자는 한 자리만 틀려도 판단이 바뀌어요 |

그래서 조항은 공정위 서식의 **고정 코드(attr)**로 분류하고, 표는 병합 칸·여러 줄 머리글·단위를 복원해 금액을 원 단위로 맞춰요. 금액은 LLM이 만들지 않고 데이터에서 그대로 꺼내요.

## 2. 주요 기능

- **채팅:** 금액·통계 질문은 구조화 데이터에서 바로 꺼내고, 서술형 질문(계약해지 조건 등)은 브랜드별로 조항을 검색해 요약해요. 답변 속 금액은 원본과 전부 대조하고, 안 맞으면 LLM 없이 만든 문장으로 바꿔요.
- **근거 원문 패널:** 출처를 누르면 원문 조항, 표, 별첨 안내를 그대로 보여 줘요.
- **브랜드 해석:** 별칭·괄호 축약형(「비비큐」→「비비큐(BBQ)」)을 인식하고, 못 찾으면 추측하지 않고 후보를 버튼으로 보여 줘요. 동명이인은 법인명으로 구분해요.
- **총창업비용:** 가맹금·보증금·기타 비용의 합계 행을 모아 계산해요. 이중 계산(예치가맹금 ⊃ 최초 가맹금)을 막고, 매장 타입이 여럿이면 타입별로 보여 줘요.
- **브랜드 비교 · TOP20 · 점검하기:** 주요 비용·매출을 표와 차트로 비교하고, 평균매출액·비용 대비 매출 순위를 보여 줘요.
- **회원 · 대화 기록:** 로그인한 사용자의 대화를 저장해요(PostgreSQL).

**기술 스택:** FastAPI · Next.js · PostgreSQL · Chroma · KURE-v1(로컬 임베딩) · Ollama(qwen3.5:9b) 또는 OpenAI

## 3. 데이터 파이프라인

```
01_fetch_disclosure_lists.py    공정위 정보공개서 목록 API → 연도별 brno 색인
02_fetch_disclosure_content.py  브랜드 ↔ 정보공개서 매칭(브랜드명 정확 일치만) → 본문 XML
03_extract_clauses.py           attr 코드로 38개 조항 선별, 표 복원, 금액 정규화 → clauses.jsonl.gz
11_build_embeddings.py          서술형 조항 약 6.2만 건 임베딩 → Chroma
```

추출 결과 `backend/data/disclosure/clauses.jsonl.gz`(브랜드 2,441개, 조항 약 9만 건)는 저장소에 들어 있어요. 원본 XML과 벡터 DB는 용량 때문에 넣지 않았어요. 자세한 규칙은 [docs/DESIGN.md](docs/DESIGN.md)에 있어요.

### 코드 구조

| 위치 | 책임 |
|---|---|
| `backend/scripts/rag/brand_match.py` | 브랜드명 정규화, 별칭·축약형 색인, 유사 후보 |
| `backend/scripts/rag/nlu.py` | LLM 1회로 intent · 브랜드 · 카테고리 추출 |
| `backend/scripts/rag/retrieval.py` | 구조화 조회 / 브랜드별 벡터 검색 |
| `backend/scripts/rag/answer.py` | 답변 조립, 금액 그룹핑, 숫자 검증, 템플릿 대체 |
| `backend/scripts/rag/total_cost.py` | 총창업비용 계산 |
| `backend/scripts/rag/pipeline.py` | 위 단계를 잇는 `answer_question()` |
| `backend/scripts/section_schema.py` | attr 코드 → 카테고리·표준 조항명 |
| `backend/app/` | FastAPI: 채팅, 인증, 대화 기록, 비교·TOP20 API |
| `frontend/app/` | Next.js 화면 |

## 4. 실행

### 준비물
- Python 3.10+, Node.js 20+, Docker(PostgreSQL)
- 로컬 Ollama(`qwen3.5:9b`) 또는 OpenAI API 키
- NVIDIA GPU 권장(임베딩). 없으면 `.env`에서 `EMBEDDING_DEVICE=cpu`

### 1) 데이터
`clauses.jsonl.gz`는 들어 있어요. 서술형 검색에 쓰는 벡터 DB는 직접 만들어요.

```bash
cd backend
python scripts/11_build_embeddings.py          # backend/data/vectordb/ 생성 (GPU 기준 약 7분)
```

브랜드 목록(`backend/data/brand/brand_unified.jsonl`)은 data.go.kr 「공정거래위원회 가맹정보 브랜드 목록」 API로 받아요. 정보공개서를 처음부터 다시 모으려면 `franchise.ftc.go.kr` API 키를 `.env`의 `DISCLOSURE_LIST_SERVICE_KEY`에 넣고 01 → 02 → 03을 차례로 실행해요.

### 2) 백엔드
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                             # macOS/Linux: cp
docker compose --env-file .env -f ../compose.yaml up -d   # PostgreSQL
# backend/sql/*.sql 을 순서대로 적용
uvicorn app.main:app --reload --port 8000
```
확인: http://localhost:8000/health → `{"status":"ok"}`

### 3) 프론트엔드
```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```
http://localhost:3000

브랜드 로고 이미지는 각 브랜드의 상표라 저장소에 넣지 않았어요. 없으면 이니셜로 표시되고, `python tools/logos/logos.py`로 정보공개서 원문에서 다시 추출할 수 있어요.

## 5. API

| 메서드 | 경로 | 내용 |
|---|---|---|
| GET | `/health` | 상태 확인 |
| POST | `/api/chat` | 질문 → 답변 + 출처 |
| POST | `/api/auth/signup` · `/login` · `/logout`, GET `/me` | 인증 |
| GET | `/api/conversations` · `/api/conversations/{id}` | 대화 기록 |
| GET | `/api/brands/search` · `/api/brands/compare` | 브랜드 검색·비교 |
| GET | `/api/brands/top20` · `/api/brands/top20/categories` | TOP20 |
| GET | `/api/home/stats` | 홈 통계 |

## 6. 평가

```bash
cd backend
python scripts/13_eval_gold.py     # 골드셋 40문항 → logs/13_eval_gold_report.md
python scripts/15_test_total_cost.py   # 총창업비용 회귀 테스트 (LLM 불필요)
```

| LLM | PASS | FAIL | N/A(사람 확인) |
|---|---|---|---|
| qwen3.5:9b (로컬) | 29 | 4 | 7 |
| gpt-4o-mini | 31 | 0 | 7 |

qwen의 FAIL 4건 중 3건은 표기 차이(「10만원」 vs 「10 만원」)를 채점 스크립트가 놓친 것이고, 실제 오답은 1건이에요(「형사처벌」 질문을 행정처분으로 분류).

## 7. 한계

- 공정위 목록 API로 찾을 수 있는 브랜드(약 2,400개)만 다뤄요. 일부 대형 브랜드는 API에 없어서 「데이터 없음」으로 나와요.
- 문서에 단위가 아예 없는 금액(약 8~10%)은 「단위 미확인」으로 표시해요.
- 별첨으로 빠진 내용(필수구입물품 상세 목록 등)은 데이터에 없고, 답변에 그 사실을 알려요.
- 로컬 LLM은 응답이 느려요(질문당 수 초~수십 초). 토큰 스트리밍은 아직 없어요.
- 이 서비스의 답은 정보공개서 원문 요약이에요. 계약 판단은 원문과 전문가 확인을 거쳐야 해요.

## 8. 만든 사람

- 데이터 수집 · 조항 표준화 · RAG 파이프라인 · 채팅 · 점검하기: KimSeungJu
- 브랜드 비교 · TOP20: JoonkiYoon
- 로그인 · 회원 · 대화 기록: Moreumi
- 브랜드 로고 추출 · TOP20 로고: choocs5228

## 데이터 출처

- 공정거래위원회 가맹사업거래 정보공개서 (franchise.ftc.go.kr Open API)
- 공정거래위원회 가맹정보 브랜드 목록 (data.go.kr)
