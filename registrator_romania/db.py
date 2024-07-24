import asyncio
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import select, update, delete, insert, Pool, Integer
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
    create_async_pool_from_url,
    AsyncSession,
)
from sqlalchemy.dialects.postgresql import JSONB

from registrator_romania.config import get_config
from registrator_romania.new_request_registrator import generate_fake_users_data


def get_async_engine():
    cfg = get_config()
    return create_async_engine(
        cfg["remote_db"]["uri"], isolation_level="AUTOCOMMIT"
    )


class Base(DeclarativeBase): ...


class ListUsers(Base):
    __tablename__ = "list_users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    data: Mapped[dict] = mapped_column(JSONB, primary_key=False, nullable=False)


async def setup():
    async with get_async_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def conn_pool():
    cfg = get_config()
    return create_async_pool_from_url(cfg["remote_db"]["uri"], pool_size=50)


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


def get_session() -> AsyncSession:
    maker = async_sessionmaker(get_async_engine())
    return maker()


async def main():
    await setup()
    session = get_session()

    users = generate_fake_users_data(40)

    async with session:
        await clear_list(session)
        await insert_users(session, users)
        print(await get_list_users(session))

        # for u in users:
        #     await remove_user(session, u)
        #     print(await get_list_users(session))
    ...


if __name__ == "__main__":
    asyncio.run(main())
