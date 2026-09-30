"""RAG 핵심 로직 패키지.

Streamlit(app.py)과 완전히 분리된 순수 함수/모듈 모음. 나중에 FastAPI로 감쌀 때
이 패키지의 함수들을 엔드포인트로 그대로 wrap할 수 있도록, 이 패키지 안 어디에도
streamlit import가 있으면 안 된다(app.py -> rag 방향으로만 의존).

가장 바깥에서 쓸 진입점은 scripts.rag.pipeline.answer_question() 하나면 충분하다.
"""
