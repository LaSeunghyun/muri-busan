import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.store import course_store
from backend.routers.share import init_share_db, _DB_PATH
from backend.routers.report import init_report_db, _DB_PATH as _REPORT_DB_PATH


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        course_store.clear()
        # 테스트용 share DB 초기화 (매 테스트마다 깨끗한 상태)
        if _DB_PATH.exists():
            _DB_PATH.unlink()
        init_share_db()
        # 테스트용 report DB 초기화
        if _REPORT_DB_PATH.exists():
            _REPORT_DB_PATH.unlink()
        init_report_db()

    def tearDown(self):
        if _DB_PATH.exists():
            _DB_PATH.unlink()
        if _REPORT_DB_PATH.exists():
            _REPORT_DB_PATH.unlink()

    def test_recommend_falls_back_to_citywide_results(self):
        fallback_courses = [
            {
                "id": "course-fallback-1",
                "name": "부산 전역 대체 코스",
                "spots": [
                    {
                        "id": "spot-1",
                        "name": "광안리해수욕장",
                        "area": "수영",
                        "wheelchair_accessible": True,
                        "stroller_accessible": True,
                        "restroom_accessible": True,
                        "elevator": False,
                    }
                ],
                "total_time_min": 120,
                "total_fatigue": 24.5,
                "distance_km": 2.4,
                "rest_spots": 1,
                "accessibility_avg": 4.5,
            }
        ]

        with patch(
            "backend.routers.recommend.fetch_spots",
            AsyncMock(return_value=[{"id": "stub-spot"}]),
        ), patch(
            "backend.routers.recommend.recommend_courses",
            side_effect=[[], fallback_courses],
        ) as recommend_mock, patch(
            "backend.routers.recommend.fetch_festivals",
            AsyncMock(return_value=[]),
        ), patch(
            "backend.routers.recommend.enrich_courses",
            side_effect=lambda courses, *a, **kw: courses,
        ):
            response = self.client.post(
                "/api/recommend",
                json={
                    "mobility_types": ["wheelchair"],
                    "days": 1,
                    "areas": ["해운대"],
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["courses"], fallback_courses)
        self.assertTrue(body["summary"]["fallback_used"])
        self.assertEqual(body["summary"]["requested_areas"], ["해운대"])
        self.assertEqual(body["summary"]["applied_areas"], ["수영"])
        self.assertEqual(recommend_mock.call_count, 2)
        self.assertEqual(recommend_mock.call_args_list[1].kwargs["areas"], [])

    def test_share_can_use_inline_course_payload_without_cache(self):
        payload_course = {
            "id": "course-inline-1",
            "name": "직접 전달 코스",
            "spots": [
                {
                    "id": "spot-inline-1",
                    "name": "태종대",
                    "area": "영도",
                    "wheelchair_accessible": True,
                    "stroller_accessible": True,
                    "restroom_accessible": True,
                    "elevator": False,
                }
            ],
            "total_time_min": 95,
            "total_fatigue": 18.0,
            "distance_km": 1.3,
            "rest_spots": 1,
            "accessibility_avg": 4.0,
        }

        create_response = self.client.post(
            "/api/share",
            json={"course": payload_course},
        )
        self.assertEqual(create_response.status_code, 200)

        token = create_response.json()["token"]
        share_response = self.client.get(f"/api/share/{token}")
        self.assertEqual(share_response.status_code, 200)
        self.assertEqual(share_response.json()["name"], "직접 전달 코스")

        course_response = self.client.get(f"/api/courses/{payload_course['id']}")
        self.assertEqual(course_response.status_code, 200)
        self.assertEqual(course_response.json()["id"], payload_course["id"])

    def test_share_persists_in_sqlite(self):
        """SQLite 영속화: DB에서 직접 조회 가능한지 확인."""
        payload_course = {
            "id": "course-persist-1",
            "name": "영속화 테스트 코스",
            "spots": [{"id": "s1", "name": "해운대", "area": "해운대"}],
            "total_time_min": 60,
            "total_fatigue": 10.0,
            "distance_km": 1.0,
            "rest_spots": 0,
            "accessibility_avg": 3.0,
        }

        resp = self.client.post("/api/share", json={"course": payload_course})
        self.assertEqual(resp.status_code, 200)
        token = resp.json()["token"]

        # DB에서 직접 확인
        import sqlite3, json
        conn = sqlite3.connect(str(_DB_PATH))
        row = conn.execute("SELECT course_json FROM shares WHERE token = ?", (token,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(json.loads(row[0])["name"], "영속화 테스트 코스")

    def test_share_not_found_returns_404(self):
        response = self.client.get("/api/share/nonexistent")
        self.assertEqual(response.status_code, 404)

    def test_runtime_config_exposes_kakao_map_key(self):
        with patch.dict(os.environ, {"KAKAO_MAP_KEY": "kakao-js-key-123"}, clear=False):
            response = self.client.get("/runtime-config.js")

        self.assertEqual(response.status_code, 200)
        self.assertIn("window.KAKAO_MAP_KEY", response.text)
        self.assertIn('"kakao-js-key-123"', response.text)


    def test_report_create_and_retrieve(self):
        """현장 신고 생성 및 조회."""
        resp = self.client.post("/api/report", json={
            "spot_id": "tour_12345",
            "spot_name": "해운대해수욕장",
            "issue_type": "elevator_broken",
            "description": "1번 출구 엘리베이터 점검 중",
            "lat": 35.1586,
            "lng": 129.1603,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("id", data)
        self.assertEqual(data["message"], "감사합니다! 데이터 개선에 도움이 됩니다.")

        # 조회
        reports = self.client.get("/api/reports/tour_12345")
        self.assertEqual(reports.status_code, 200)
        items = reports.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["issue_type"], "elevator_broken")
        self.assertEqual(items[0]["spot_name"], "해운대해수욕장")

    def test_report_invalid_issue_type(self):
        """잘못된 이슈 유형은 400."""
        resp = self.client.post("/api/report", json={
            "spot_id": "tour_99",
            "spot_name": "테스트",
            "issue_type": "invalid_type",
        })
        self.assertEqual(resp.status_code, 400)

    def test_share_expired_returns_410(self):
        """만료된 공유 링크는 410 반환."""
        from datetime import datetime, timedelta, timezone
        import sqlite3, json

        payload_course = {
            "id": "course-expire-1",
            "name": "만료 테스트 코스",
            "spots": [{"id": "s1", "name": "테스트", "area": "해운대"}],
            "total_time_min": 60,
            "total_fatigue": 10.0,
            "distance_km": 1.0,
            "rest_spots": 0,
            "accessibility_avg": 3.0,
        }

        resp = self.client.post("/api/share", json={"course": payload_course})
        self.assertEqual(resp.status_code, 200)
        token = resp.json()["token"]

        # DB에서 직접 만료 시각을 과거로 변경
        expired = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        conn = sqlite3.connect(str(_DB_PATH))
        conn.execute("UPDATE shares SET expires_at = ? WHERE token = ?", (expired, token))
        conn.commit()
        conn.close()

        resp = self.client.get(f"/api/share/{token}")
        self.assertEqual(resp.status_code, 410)


if __name__ == "__main__":
    unittest.main()
