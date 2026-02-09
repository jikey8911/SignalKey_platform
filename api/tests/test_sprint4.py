import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch
from api.main import app
from api.src.domain.entities.bot_instance import BotInstance
from api.src.infrastructure.security.auth_deps import get_current_user
from bson import ObjectId

# --- AUTH OVERRIDE ---
async def mock_get_current_user():
    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "openId": "default_user",
        "email": "test@test.com"
    }

app.dependency_overrides[get_current_user] = mock_get_current_user

client = TestClient(app)

# --- MOCKS ---
@pytest.fixture
def mock_repo():
    with patch("api.src.adapters.driving.api.routers.bot_router.repo") as mock:
        # Ensure collection.find_one is async
        mock.collection.find_one = AsyncMock(return_value=None)
        yield mock

@pytest.fixture
def mock_db():
    # Patch 'db' imported in bot_router
    with patch("api.src.adapters.driving.api.routers.bot_router.db") as mock:
        # Mock dictionary access like db["positions"]
        mock_positions = MagicMock()
        mock.__getitem__.return_value = mock_positions
        # Mock find_one on the collection
        mock_positions.find_one = AsyncMock(return_value=None)
        yield mock

@pytest.fixture
def mock_engine():
    with patch("api.src.adapters.driving.api.routers.bot_router.engine") as mock:
        # Mock process_signal to be async
        mock.process_signal = AsyncMock(return_value={"success": True, "status": "executed", "pnl": 0})
        yield mock

@pytest.fixture
def mock_app_config():
    with patch("api.src.adapters.driving.api.routers.bot_router.get_app_config", new_callable=AsyncMock) as mock:
        mock.return_value = {
            "investmentLimits": {"cexMaxAmount": 1000.0, "dexMaxAmount": 500.0},
            "virtualBalances": {"cex": 10000.0}
        }
        yield mock

# --- TESTS ---

def test_create_bot_endpoint(mock_repo, mock_app_config):
    # Setup
    mock_repo.save = AsyncMock(return_value="507f1f77bcf86cd799439011")

    payload = {
        "name": "Test Bot S4",
        "symbol": "BTC/USDT",
        "strategy_name": "TrendMaster",
        "timeframe": "1h",
        "mode": "simulated",
        "market_type": "spot",
        "amount": 100.0
    }

    # Execute
    response = client.post("/api/bots/", json=payload)

    # Verify
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json["id"] == "507f1f77bcf86cd799439011"
    assert resp_json["status"] == "created"

    # Verify repo.save called with correct user_id (ObjectId)
    args = mock_repo.save.call_args[0]
    bot_entity = args[0]
    assert isinstance(bot_entity.user_id, ObjectId)
    assert str(bot_entity.user_id) == "507f1f77bcf86cd799439011"

def test_list_bots_endpoint(mock_repo, mock_db):
    # Setup
    mock_bot = BotInstance(
        id="507f1f77bcf86cd799439011",
        user_id=ObjectId("507f1f77bcf86cd799439011"),
        name="B1",
        symbol="ETH/USDT",
        strategy_name="S1",
        timeframe="1h",
        mode="simulated",
        status="active",
        amount=100.0
    )
    # Mock get_all_by_user returning the bot
    mock_repo.get_all_by_user = AsyncMock(return_value=[mock_bot])

    # Mock positions collection via __getitem__
    mock_positions_coll = MagicMock()
    mock_db.__getitem__.return_value = mock_positions_coll
    mock_positions_coll.find_one = AsyncMock(return_value=None)

    # Execute
    response = client.get("/api/bots/")

    # Verify
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "B1"

    # Verify get_all_by_user called with ObjectId
    mock_repo.get_all_by_user.assert_called_once()
    args = mock_repo.get_all_by_user.call_args[0]
    assert isinstance(args[0], ObjectId)
    assert str(args[0]) == "507f1f77bcf86cd799439011"

def test_update_bot_status(mock_repo):
    # Setup
    mock_repo.update_status = AsyncMock(return_value=True)
    # Mock find_one for emitting status update
    mock_repo.collection.find_one = AsyncMock(return_value={
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "status": "paused",
        "userId": ObjectId("507f1f77bcf86cd799439011")
    })

    bot_id = "507f1f77bcf86cd799439011"
    
    # Execute
    response = client.patch(f"/api/bots/{bot_id}/status?status=paused")

    # Verify
    assert response.status_code == 200
    assert response.json() == {"message": "Bot paused"}
    mock_repo.update_status.assert_called_with(bot_id, "paused")

def test_webhook_trigger_engine(mock_repo, mock_engine):
    # Setup mock bot found in DB
    mock_bot_doc = {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "id": "507f1f77bcf86cd799439011",
        "status": "active", 
        "mode": "simulated",
        "symbol": "BTC/USDT",
        "amount": 1000,
        "user_id": ObjectId("507f1f77bcf86cd799439011")
    }
    # repo.collection.find_one is called
    mock_repo.collection.find_one = AsyncMock(return_value=mock_bot_doc)

    payload = {
        "bot_id": "507f1f77bcf86cd799439011",
        "signal": 1,
        "price": 50000.0
    }
    
    # Execute
    response = client.post("/api/bots/webhook-signal", json=payload)
    
    # Verify
    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    
    # Verify engine was called
    mock_engine.process_signal.assert_called_once()

    # Check arguments
    args = mock_engine.process_signal.call_args[0]
    # Check that user_id in bot passed to engine is ObjectId
    # Note: The code modifies bot['id'] = str(bot['_id']), but usually leaves other fields
    assert args[0]["id"] == "507f1f77bcf86cd799439011"
    assert args[1]["price"] == 50000.0

def test_webhook_bot_not_found(mock_repo):
    # Setup
    mock_repo.collection.find_one = AsyncMock(return_value=None)
    
    payload = {
        "bot_id": "507f1f77bcf86cd799439011",
        "signal": 1,
        "price": 50000.0
    }

    # Execute
    response = client.post("/api/bots/webhook-signal", json=payload)

    # Verify
    assert response.status_code == 404
