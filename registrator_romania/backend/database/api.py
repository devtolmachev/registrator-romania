from datetime import date

from loguru import logger
from sqlalchemy import (
    CursorResult,
    Delete,
    Insert,
    Select,
    Text,
    Update,
    select,
    delete,
    insert,
    text,
)
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
    AsyncSession,
)

from registrator_romania.backend.database.sqlalchemy_models import (
    Base,
    ListUsers,
)
from registrator_romania.shared import get_config


def get_async_engine():
    cfg = get_config()
    return create_async_engine(cfg["remote_db"]["uri"])


def get_session() -> AsyncSession:
    maker = async_sessionmaker(get_async_engine(), expire_on_commit=False)
    return maker()


async def setup():
    async with get_async_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_list_users(session: AsyncSession):
    stmt = select(ListUsers)
    conn = await session.connection()
    r = await conn.execute(stmt)
    results = r.fetchall()
    return [data for id, data in results]


async def insert_users(session: AsyncSession, users: list[dict]):
    for user in users:
        stmt = insert(ListUsers).values(data=user)
        await session.execute(stmt)


async def remove_user(session: AsyncSession, user: dict):
    stmt = delete(ListUsers).where(ListUsers.data == user)
    await session.execute(stmt)


async def clear_list(session: AsyncSession):
    stmt = delete(ListUsers)
    await session.execute(stmt)


def to_dict_cursor_result(curresultl: CursorResult, data: tuple) -> dict:
    return dict(zip(curresultl.keys(), data))


class UsersService:
    _model = ListUsers

    def __init__(self) -> None:
        eng = get_async_engine()
        self._maker = async_sessionmaker(
            eng, expire_on_commit=False, class_=AsyncSession
        )
        self._session: AsyncSession = None

    async def __aenter__(self):
        self._session = self._maker()
        cmd = (
            f"LOCK TABLE {self._model.__tablename__} IN ACCESS EXCLUSIVE MODE;"
        )
        self._conn = await self._session.connection()
        await self._conn.execute(text(cmd))
        return self

    async def __aexit__(self, type, value, traceback):
        if value:
            await self._conn.rollback()
        else:
            await self._conn.commit()
        
        await self._conn.close()
        return True

    async def _execute_stmt(
        self, stmt: Select | Update | Delete | Insert | Text
    ) -> CursorResult:
        conn = await self._session.connection()

        return await conn.execute(stmt)

    async def clear_table(self):
        stmt = "truncate table list_users cascade;"
        await self._execute_stmt(text(stmt))

    async def get_users_by_reg_date(
        self, registration_date: date
    ) -> list[dict] | None:
        stmt = select(self._model.user_data).where(
            self._model.registration_date == registration_date
        )
        cur = await self._execute_stmt(stmt)
        result = cur.fetchall()

        if result:
            return [user_data[0] for user_data in result]
        return []

    async def add_user(
        self, user_data: dict, registration_date: date
    ) -> dict | None:
        users_in_db = await self.get_users_by_reg_date(registration_date)
        if users_in_db and user_data in users_in_db:
            return

        stmt = (
            insert(self._model)
            .values(user_data=user_data, registration_date=registration_date)
            .returning(self._model)
        )
        cur = await self._execute_stmt(stmt)
        result = cur.fetchall()

        if result:
            data = to_dict_cursor_result(cur, result[0].tuple())
            return data["user_data"]

    async def remove_user(self, user_data: dict) -> None:
        stmt = delete(self._model).where(self._model.user_data == user_data)
        await self._execute_stmt(stmt)
