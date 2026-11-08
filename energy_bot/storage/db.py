"""SQLite persistence: subscribers, schedule snapshots, sent notifications and active emergency outages."""

from datetime import date, datetime, time, timedelta
from typing import Self

import aiosqlite

from energy_bot.loe.schemas import DaySchedule
from energy_bot.storage.schemas import ActiveAccident, Subscriber

SNAPSHOT_RETENTION = timedelta(days=7)
SENT_RETENTION = timedelta(days=3)

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    chat_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    outage_group TEXT NOT NULL,
    city_id INTEGER,
    city_name TEXT,
    otg_name TEXT,
    street_id INTEGER,
    street_name TEXT,
    building TEXT,
    quiet_start TEXT NOT NULL,
    quiet_end TEXT NOT NULL,
    quiet_enabled INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS schedule_snapshots (
    date TEXT PRIMARY KEY,
    schedule_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sent_notifications (
    chat_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, key)
);
CREATE TABLE IF NOT EXISTS active_accidents (
    chat_id INTEGER NOT NULL,
    accident_id INTEGER NOT NULL,
    date_plan_in TEXT,
    PRIMARY KEY (chat_id, accident_id)
);
"""

SUBSCRIBER_COLUMNS = tuple(Subscriber.model_fields)
UPSERT_SUBSCRIBER = (
    f"INSERT INTO subscribers ({', '.join(SUBSCRIBER_COLUMNS)}) "
    f"VALUES ({', '.join(f':{column}' for column in SUBSCRIBER_COLUMNS)}) "
    f"ON CONFLICT (chat_id) DO UPDATE SET "
    f"{', '.join(f'{column} = excluded.{column}' for column in SUBSCRIBER_COLUMNS if column != 'chat_id')}"
)


class Database:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection

    @classmethod
    async def connect(cls, path: str) -> Self:
        connection = await aiosqlite.connect(path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA journal_mode=WAL")
        await connection.executescript(SCHEMA)
        await connection.commit()
        return cls(connection)

    async def close(self) -> None:
        await self._connection.close()

    async def upsert_subscriber(self, subscriber: Subscriber) -> None:
        await self._connection.execute(UPSERT_SUBSCRIBER, subscriber.model_dump(mode="json"))
        await self._connection.commit()

    async def get_subscriber(self, chat_id: int) -> Subscriber | None:
        async with self._connection.execute("SELECT * FROM subscribers WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
        return Subscriber.model_validate(dict(row)) if row else None

    async def active_subscribers(self) -> list[Subscriber]:
        async with self._connection.execute("SELECT * FROM subscribers WHERE active = 1") as cursor:
            return [Subscriber.model_validate(dict(row)) async for row in cursor]

    async def set_quiet_hours(self, chat_id: int, start: time, end: time, enabled: bool) -> None:
        await self._connection.execute(
            "UPDATE subscribers SET quiet_start = ?, quiet_end = ?, quiet_enabled = ? WHERE chat_id = ?",
            (start.isoformat(), end.isoformat(), enabled, chat_id),
        )
        await self._connection.commit()

    async def deactivate(self, chat_id: int) -> None:
        """For a chat that blocked the bot: keep its data, stop sending to it."""
        await self._connection.execute("UPDATE subscribers SET active = 0 WHERE chat_id = ?", (chat_id,))
        await self._connection.commit()

    async def delete_subscriber(self, chat_id: int) -> None:
        """/stop: remove the subscriber and everything stored for it."""
        for table in ("subscribers", "sent_notifications", "active_accidents"):
            await self._connection.execute(f"DELETE FROM {table} WHERE chat_id = ?", (chat_id,))
        await self._connection.commit()

    async def has_snapshots(self) -> bool:
        async with self._connection.execute("SELECT 1 FROM schedule_snapshots LIMIT 1") as cursor:
            return await cursor.fetchone() is not None

    async def get_snapshot(self, day: date) -> DaySchedule | None:
        async with self._connection.execute(
            "SELECT schedule_json FROM schedule_snapshots WHERE date = ?", (day.isoformat(),)
        ) as cursor:
            row = await cursor.fetchone()
        return DaySchedule.model_validate_json(row["schedule_json"]) if row else None

    async def recent_snapshots(self, since: date) -> list[DaySchedule]:
        async with self._connection.execute(
            "SELECT schedule_json FROM schedule_snapshots WHERE date >= ? ORDER BY date", (since.isoformat(),)
        ) as cursor:
            return [DaySchedule.model_validate_json(row["schedule_json"]) async for row in cursor]

    async def save_snapshot(self, schedule: DaySchedule) -> None:
        await self._connection.execute(
            "INSERT OR REPLACE INTO schedule_snapshots (date, schedule_json) VALUES (?, ?)",
            (schedule.date.isoformat(), schedule.model_dump_json()),
        )
        await self._connection.commit()

    async def is_sent(self, chat_id: int, key: str) -> bool:
        async with self._connection.execute(
            "SELECT 1 FROM sent_notifications WHERE chat_id = ? AND key = ?", (chat_id, key)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def mark_sent(self, chat_id: int, key: str, now: datetime) -> None:
        await self._connection.execute(
            "INSERT OR IGNORE INTO sent_notifications (chat_id, key, sent_at) VALUES (?, ?, ?)",
            (chat_id, key, now.isoformat()),
        )
        await self._connection.commit()

    async def active_accidents(self, chat_id: int) -> list[ActiveAccident]:
        async with self._connection.execute(
            "SELECT accident_id, date_plan_in FROM active_accidents WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            return [ActiveAccident.model_validate(dict(row)) async for row in cursor]

    async def save_accident(self, chat_id: int, accident: ActiveAccident) -> None:
        """Insert a newly reported accident or update its planned restore time."""
        await self._connection.execute(
            "INSERT OR REPLACE INTO active_accidents (chat_id, accident_id, date_plan_in) "
            "VALUES (:chat_id, :accident_id, :date_plan_in)",
            {"chat_id": chat_id, **accident.model_dump(mode="json")},
        )
        await self._connection.commit()

    async def remove_accident(self, chat_id: int, accident_id: int) -> None:
        await self._connection.execute(
            "DELETE FROM active_accidents WHERE chat_id = ? AND accident_id = ?", (chat_id, accident_id)
        )
        await self._connection.commit()

    async def prune(self, now: datetime) -> None:
        """Drop snapshots and sent-notification records too old to matter."""
        await self._connection.execute(
            "DELETE FROM schedule_snapshots WHERE date < ?", ((now - SNAPSHOT_RETENTION).date().isoformat(),)
        )
        await self._connection.execute(
            "DELETE FROM sent_notifications WHERE sent_at < ?", ((now - SENT_RETENTION).isoformat(),)
        )
        await self._connection.commit()
