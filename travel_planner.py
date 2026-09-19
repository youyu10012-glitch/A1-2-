"""CLI domestic travel planner using Gemini and Kakao Local APIs."""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from google import genai

REQUIRED_RECOMMENDATION_KEYS = {"recommended_city", "weather", "events", "reason"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="날짜 기반 국내 여행지 추천 프로그램")
    parser.add_argument("-date", "--date", required=True, help="여행 날짜 (YYYY-MM-DD)")
    parser.add_argument("--offline", action="store_true", help="API 호출 없이 예시 데이터로 결과 파일을 생성합니다.")
    args = parser.parse_args()
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        parser.error("date는 YYYY-MM-DD 형식이어야 합니다.")
    return args


def add_error(errors: list[dict[str, str]], step: str, error_type: str, message: str) -> None:
    errors.append({"step": step, "type": error_type, "message": message[:300]})


def extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    result = json.loads(cleaned)
    if not isinstance(result, dict) or not REQUIRED_RECOMMENDATION_KEYS.issubset(result):
        raise ValueError("필수 추천 필드가 없습니다.")
    if not isinstance(result["recommended_city"], str) or not isinstance(result["events"], list):
        raise ValueError("추천 필드 타입이 올바르지 않습니다.")
    return result


def recommendation_prompt(travel_date: str, retry: bool = False) -> str:
    retry_instruction = "이전 출력이 파싱되지 않았으므로 JSON만 출력하세요." if retry else ""
    return f"""{travel_date}에 여행하기 좋은 국내 도시 한 곳을 추천해 주세요.
{retry_instruction}
마크다운이나 설명 없이 유효한 JSON 객체만 출력하세요. 스키마:
{{"recommended_city":"도시명","weather":"해당 시기 일반적 날씨 요약","events":["행사 후보"],"reason":"2~4문장 추천 근거"}}
events는 1~3개의 문자열 배열이어야 합니다. 행사 일정은 변동될 수 있음을 고려하세요."""


def get_recommendation(travel_date: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 또는 GOOGLE_API_KEY가 설정되지 않았습니다.")
    client = genai.Client(api_key=api_key)
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                contents=recommendation_prompt(travel_date, retry=attempt == 1),
                config={"response_mime_type": "application/json"},
            )
            return extract_json(response.text)
        except (ValueError, json.JSONDecodeError, AttributeError) as exc:
            if attempt == 1:
                add_error(errors, "llm_recommendation", "PARSE_ERROR", str(exc))
        except Exception as exc:
            add_error(errors, "llm_recommendation", "API_ERROR", str(exc))
            break
    raise RuntimeError("Gemini 추천 결과를 생성하지 못했습니다.")


def search_restaurants(city: str, errors: list[dict[str, str]]) -> list[dict[str, Any]]:
    api_key = os.getenv("KAKAO_REST_API_KEY")
    if not api_key:
        add_error(errors, "place_search", "MISSING_API_KEY", "KAKAO_REST_API_KEY가 없어 데이터 없음")
        return []
    try:
        response = requests.get(
            "https://dapi.kakao.com/v2/local/search/keyword.json",
            headers={"Authorization": f"KakaoAK {api_key}"},
            params={"query": f"{city} 맛집", "size": 5},
            timeout=10,
        )
        if response.status_code in (401, 403):
            add_error(errors, "place_search", "AUTH_ERROR", f"HTTP {response.status_code}")
            return []
        response.raise_for_status()
        documents = response.json().get("documents", [])
        restaurants = [
            {
                "name": item.get("place_name", ""),
                "address": item.get("road_address_name") or item.get("address_name", ""),
                "category": item.get("category_name", ""),
                "url": item.get("place_url", ""),
                "x": float(item["x"]) if item.get("x") else None,
                "y": float(item["y"]) if item.get("y") else None,
            }
            for item in documents[:5]
        ]
        if not restaurants:
            add_error(errors, "place_search", "EMPTY_RESULT", f"0 results for query={city} 맛집")
        return restaurants
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        add_error(errors, "place_search", "API_ERROR", str(exc))
        return []


def offline_recommendation(travel_date: str) -> dict[str, Any]:
    month = int(travel_date[5:7])
    return {
        "recommended_city": "강릉",
        "weather": f"{month}월의 강릉은 계절 특유의 선선한 날씨로 해안 산책에 적합합니다.",
        "events": ["강릉 지역 계절 문화 행사(일정 변동 가능)"],
        "reason": "바다와 커피 문화를 함께 즐길 수 있는 도시입니다. 하루 일정으로 해안과 지역 문화를 균형 있게 둘러보기 좋습니다.",
    }


def build_report(travel_date: str, recommendation: dict[str, Any], restaurants: list[dict[str, Any]], errors: list[dict[str, str]]) -> str:
    events = recommendation.get("events") or ["데이터 없음"]
    event_lines = "\n".join(f"- {event}" for event in events)
    if restaurants:
        restaurant_lines = "\n".join(f"- **{item['name']}** | {item['category'] or '분류 없음'} | {item['address']}" for item in restaurants)
    else:
        restaurant_lines = "- 데이터 없음 (장소 검색 결과 0건 또는 API 미설정)"
    error_lines = "\n".join(f"- `{error['step']}`: {error['type']} - {error['message']}" for error in errors) or "- 없음"
    return f"""# {travel_date} 국내 여행 추천 리포트

## 추천 지역
{recommendation['recommended_city']}

## 추천 이유
{recommendation['reason']}

## 날씨 요약
{recommendation['weather']}

## 행사/축제
{event_lines}

## 맛집 추천
{restaurant_lines}

## 1일 일정 제안
- 오전: 지역 대표 명소와 주변 산책
- 오후: 추천 맛집에서 식사 후 문화 공간 방문
- 저녁: 해안 또는 도심 야경 감상

## 오류 요약(errors)
{error_lines}
"""


def generate_report_with_llm(
    travel_date: str,
    recommendation: dict[str, Any],
    restaurants: list[dict[str, Any]],
) -> str:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Gemini API 키가 없습니다.")
    client = genai.Client(api_key=api_key)
    prompt = f"""다음 여행 추천 데이터로 Markdown 리포트를 작성하세요.
날짜: {travel_date}
추천: {json.dumps(recommendation, ensure_ascii=False)}
맛집: {json.dumps(restaurants, ensure_ascii=False)}
반드시 추천 지역, 추천 이유, 날씨 요약, 행사/축제, 맛집 리스트, 오전/오후/저녁 1일 일정 제안을 포함하세요.
맛집이 비어 있으면 '데이터 없음'이라고 표시하세요. Markdown 텍스트만 출력하세요."""
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        contents=prompt,
    )
    if not response.text or not response.text.strip():
        raise ValueError("빈 리포트가 반환되었습니다.")
    return response.text.strip()


def main() -> int:
    load_dotenv()
    args = parse_args()
    errors: list[dict[str, str]] = []
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    print("[1/3] 1차 추천 생성 중(LLM)...")
    if args.offline:
        recommendation = offline_recommendation(args.date)
    else:
        try:
            recommendation = get_recommendation(args.date, errors)
        except RuntimeError as exc:
            print(f"오류: {exc}", file=sys.stderr)
            print(".env에 GEMINI_API_KEY를 설정하거나 테스트 시 --offline을 사용하세요.", file=sys.stderr)
            return 1
    print(f"    - recommended_city: {recommendation['recommended_city']}")
    print("[2/3] 맛집 검색 중(카카오 로컬 API)...")
    restaurants = search_restaurants(recommendation["recommended_city"], errors) if not args.offline else []
    print(f"    - 맛집 {len(restaurants)}곳" if restaurants else "    - 데이터 없음, 계속 진행합니다.")
    print("[3/3] 최종 리포트 생성 중...")
    if args.offline:
        report = build_report(args.date, recommendation, restaurants, errors)
    else:
        try:
            report = generate_report_with_llm(args.date, recommendation, restaurants)
        except Exception as exc:
            add_error(errors, "llm_report", "API_ERROR", str(exc))
            report = build_report(args.date, recommendation, restaurants, errors)
    raw_data = {"date": args.date, "recommendation": recommendation, "restaurants": restaurants, "errors": errors}
    raw_path = results_dir / f"{args.date}_raw_data.json"
    report_path = results_dir / f"{args.date}_travel_plan.md"
    raw_path.write_text(json.dumps(raw_data, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(report, encoding="utf-8")
    print(f"완료! {raw_path}와 {report_path}를 확인하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())