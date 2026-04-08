"""CourseStore — module-level singleton for course caching.

Replaces the private `_course_cache` dict in courses.py to provide
a shared interface across routers without layer-breaking imports.
"""
from __future__ import annotations


class CourseStore:
    """In-memory course cache with a clean public interface."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def get(self, course_id: str) -> dict | None:
        return self._data.get(course_id)

    def put(self, course_id: str, course: dict) -> None:
        self._data[course_id] = course

    def put_many(self, courses: list[dict]) -> None:
        for c in courses:
            self._data[c["id"]] = c

    def clear(self) -> None:
        self._data.clear()


# Module-level singleton
course_store = CourseStore()
