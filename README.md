# 국내 여행 추천 CLI

입력한 날짜를 바탕으로 Gemini가 국내 추천 도시, 날씨, 행사, 추천 이유를 JSON으로 생성하고, Kakao Local API로 해당 도시의 맛집을 검색해 Markdown 여행 리포트를 만듭니다.

## 설치

Python 3.10 이상에서 실행합니다.

```bash
pip install google-genai requests python-dotenv
```

## API 키 설정

프로젝트 루트에 `.env` 파일을 만들고 실제 키를 입력합니다. 파일은 `.gitignore`에 등록되어 있습니다.

```env
GEMINI_API_KEY="YOUR_GEMINI_API_KEY_HERE"

KAKAO_REST_API_KEY="YOUR_KAKAO_API_KEY_HERE"

```

Gemini 키가 없으면 일반 실행은 중단됩니다. Kakao 키가 없거나 장소 API가 실패하면 맛집은 `데이터 없음`으로 처리하고 리포트 생성을 계속합니다. 키를 코드, README, 결과 파일에 직접 작성하거나 Git에 커밋하지 마세요.

## 실행

```bash
python travel_planner.py --date "2026-10-03"
# -date 형식도 지원합니다.
python travel_planner.py -date "2026-10-03"
```

API 키 없이 동작과 결과 파일을 확인할 때는 명시적인 오프라인 모드를 사용할 수 있습니다.

```bash
python travel_planner.py --date "2026-10-03" --offline
```

날짜가 `YYYY-MM-DD`가 아니면 argparse 사용법과 오류가 출력됩니다. Gemini JSON 파싱 오류는 최대 1회 재시도하며, 외부 API 오류는 `errors`에 기록합니다.

## 결과물

실행하면 `results/`가 생성됩니다.

- `YYYY-MM-DD_raw_data.json`: 추천 JSON, 맛집 목록, 오류 요약
- `YYYY-MM-DD_travel_plan.md`: 추천 지역, 이유, 날씨, 행사, 맛집, 1일 일정

결과 파일에도 API 키를 기록하지 않습니다. `results/`는 개인 실행 결과가 저장되는 폴더이므로 기본적으로 Git 추적 대상에서 제외됩니다.

