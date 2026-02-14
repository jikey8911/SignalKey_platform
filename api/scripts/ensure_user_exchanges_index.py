import asyncio
from api.src.adapters.driven.persistence.mongodb import db


async def main():
    # one document per user
    await db["user_exchanges"].create_index([( "userId", 1)], unique=True)
    print("OK: user_exchanges.userId unique index ensured")


if __name__ == "__main__":
    asyncio.run(main())
