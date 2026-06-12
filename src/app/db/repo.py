"""数据访问层：写入登记、按车牌查历史（查历史延后到回访阶段）。

纯副作用层，用 asyncpg 连接池。和管线解耦，可单独测、并发安全。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg
from loguru import logger

from app.config import get_settings

_pool: asyncpg.Pool | None = None


@dataclass
class Registration:
    """一条登记记录。"""

    id: int
    plate: str
    company: str
    phone: str
    reason: str
    created_at: datetime


async def get_pool() -> asyncpg.Pool:
    """惰性创建并复用连接池。"""
    global _pool
    if _pool is None:
        dsn = get_settings().asyncpg_dsn
        _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        logger.debug("asyncpg 连接池已建立")
    return _pool


async def close_pool() -> None:
    """关闭连接池（退出时调用）。"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def insert_registration(plate: str, company: str, phone: str, reason: str) -> Registration:
    """写入一条登记，返回带 id 和 created_at 的记录。"""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO registrations (plate, company, phone, reason)
        VALUES ($1, $2, $3, $4)
        RETURNING id, plate, company, phone, reason, created_at
        """,
        plate,
        company,
        phone,
        reason,
    )
    reg = Registration(**dict(row))
    logger.info(f"[DB] 写入登记 id={reg.id} 车牌={reg.plate} 单位={reg.company}")
    return reg


async def find_by_plate(plate: str, limit: int = 5) -> list[Registration]:
    """按车牌查历史（回访用，阶段 6 才接入对话；这里先实现纯函数）。"""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, plate, company, phone, reason, created_at
        FROM registrations
        WHERE plate = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        plate,
        limit,
    )
    return [Registration(**dict(r)) for r in rows]
