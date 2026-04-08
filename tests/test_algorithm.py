import json
import unittest
from pathlib import Path

from backend.services.algorithm import (
    MAX_DAILY_FATIGUE,
    MAX_DAILY_MINUTES,
    recommend_courses,
)


class RecommendationAlgorithmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data_path = Path("backend/data/busan_spots.json")
        cls.spots = json.loads(data_path.read_text(encoding="utf-8"))

    def test_recommend_courses_respect_daily_constraints(self):
        courses = recommend_courses(
            spots=self.spots,
            mobility_types=["carrier"],
            days=2,
            areas=[],
        )

        self.assertGreaterEqual(len(courses), 1)

        for course in courses:
            self.assertLessEqual(course["total_time_min"], MAX_DAILY_MINUTES)
            self.assertLessEqual(course["total_fatigue"], MAX_DAILY_FATIGUE)
            self.assertGreaterEqual(len(course["spots"]), 1)
            self.assertEqual(len(course["legs"]), max(len(course["spots"]) - 1, 0))

            # 코스 내부에서 스팟 중복 없음
            spot_ids = [s["id"] for s in course["spots"]]
            self.assertEqual(len(spot_ids), len(set(spot_ids)),
                             f"코스 내 스팟 중복: {course['name']}")

            for leg in course["legs"]:
                self.assertIn(leg["recommended_mode"], {"walk", "transit", "car"})
                self.assertGreater(leg["recommended_distance_m"], 0)
                self.assertGreater(leg["recommended_time_min"], 0)

        # 서로 다른 day의 primary 코스(alt_idx==0) 간에는 스팟 중복 없음
        primary_courses = [c for c in courses if not c["name"].endswith(("(B코스)", "(C코스)"))]
        seen_spot_ids = set()
        for course in primary_courses:
            for spot in course["spots"]:
                self.assertNotIn(spot["id"], seen_spot_ids,
                                 f"primary 코스 간 스팟 중복: {spot['id']}")
                seen_spot_ids.add(spot["id"])


if __name__ == "__main__":
    unittest.main()
