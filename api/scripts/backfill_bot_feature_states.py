import argparse
import asyncio
from typing import Optional

from api.src.adapters.driven.persistence.mongodb import db
from api.src.application.services.bot_feature_state_service import BotFeatureStateService
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service


async def run_backfill(only_active: bool, limit: Optional[int], bot_id: Optional[str], dry_run: bool):
    query = {}
    if only_active:
        query["status"] = "active"
    if bot_id:
        query["_id"] = __import__("bson").ObjectId(bot_id)

    cursor = db.bot_instances.find(query).sort("created_at", -1)
    if limit and limit > 0:
        cursor = cursor.limit(limit)

    bots = await cursor.to_list(length=limit or 100000)
    print(f"[BACKFILL] Bots encontrados: {len(bots)}")

    service = BotFeatureStateService()
    ok = 0
    fail = 0

    for b in bots:
        bid = str(b.get("_id"))
        try:
            user_oid = b.get("user_id") or b.get("userId")
            user_open = None
            if user_oid is not None:
                user_doc = await db.users.find_one({"_id": user_oid})
                if user_doc:
                    user_open = user_doc.get("openId")

            if not user_open:
                print(f"[SKIP] {bid} -> user openId not found")
                fail += 1
                continue

            payload = {
                "bot_id": bid,
                "user_id": user_oid,
                "user_open_id": user_open,
                "symbol": b.get("symbol"),
                "timeframe": b.get("timeframe") or "15m",
                "market_type": (b.get("market_type") or b.get("marketType") or "spot"),
                "exchange_id": (b.get("exchange_id") or b.get("exchangeId") or "okx"),
                "strategy_name": b.get("strategy_name") or "auto",
                "candles_limit": 200,
            }

            if dry_run:
                print(f"[DRY] {bid} {payload['strategy_name']} {payload['symbol']} {payload['timeframe']} {payload['market_type']} {payload['exchange_id']}")
                ok += 1
                continue

            res = await service.initialize_for_bot(**payload)
            if res.get("ok"):
                print(f"[OK] {bid} -> doc={res.get('docId')} features={res.get('featureCount')} rows={res.get('rows')}")
                ok += 1
            else:
                print(f"[FAIL] {bid} -> {res}")
                fail += 1
        except Exception as e:
            print(f"[ERR] {bid} -> {e}")
            fail += 1

    print(f"[BACKFILL] done ok={ok} fail={fail}")

    # Ensure CCXT async sessions are closed cleanly
    try:
        await ccxt_service.close_all()
    except Exception:
        pass


def main():
    p = argparse.ArgumentParser(description="Backfill bot_feature_states for existing bot_instances")
    p.add_argument("--only-active", action="store_true", help="Process only active bots")
    p.add_argument("--all", action="store_true", help="Process ALL bots (overrides --only-active)")
    p.add_argument("--limit", type=int, default=0, help="Max bots to process")
    p.add_argument("--bot-id", type=str, default="", help="Process a single bot ObjectId")
    p.add_argument("--dry-run", action="store_true", help="Do not write, only validate/list")
    args = p.parse_args()

    asyncio.run(
        run_backfill(
            only_active=(False if args.all else args.only_active),
            limit=args.limit if args.limit > 0 else None,
            bot_id=args.bot_id or None,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
