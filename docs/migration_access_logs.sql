-- access_logs: 모든 페이지 접속·API 호출 자동 기록
-- Supabase SQL Editor에서 실행

CREATE TABLE IF NOT EXISTS access_logs (
    id          uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at  timestamptz DEFAULT now(),
    ip          text,
    method      text,
    path        text,
    status_code integer,
    duration_ms integer,
    user_agent  text
);

-- 최신순 조회 인덱스
CREATE INDEX IF NOT EXISTS access_logs_created_at_idx ON access_logs (created_at DESC);
-- 경로별 필터 인덱스
CREATE INDEX IF NOT EXISTS access_logs_path_idx ON access_logs (path);

-- 30일 이상 된 로그 자동 삭제 (선택 사항 — 필요 시 주석 해제)
-- SELECT cron.schedule('delete-old-access-logs', '0 3 * * *',
--   $$DELETE FROM access_logs WHERE created_at < now() - interval '30 days'$$);
