-- registrations：访客登记表。回访沿用同一张表，不改 schema。
CREATE TABLE IF NOT EXISTS registrations (
    id          BIGSERIAL PRIMARY KEY,
    plate       TEXT        NOT NULL,   -- 车牌号
    company     TEXT        NOT NULL,   -- 来访单位
    phone       TEXT        NOT NULL,   -- 手机号
    reason      TEXT        NOT NULL,   -- 来访事由
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 回访识别按车牌查历史
CREATE INDEX IF NOT EXISTS idx_registrations_plate ON registrations (plate);
CREATE INDEX IF NOT EXISTS idx_registrations_created_at ON registrations (created_at DESC);
