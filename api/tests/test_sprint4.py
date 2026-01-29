import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch
from api.main import app
from api.src.domain.entities.bot_instance import BotInstance

client = TestClient(app)

# --- MOCKS ---
@pytest.fixture
def mock_repo():
    with patch("api.src.adapters.driving.api.routers.bot_router.repo") as mock:
        yield mock

@pytest.fixture
def mock_engine():
    with patch("api.src.adapters.driving.api.routers.bot_router.engine") as mock:
        # Mock process_signal to be async
        mock.process_signal = AsyncMock(return_value={"status": "executed", "pnl": 0})
        yield mock

# --- TESTS ---

def test_create_bot_endpoint(mock_repo):
    mock_repo.save.return_value = "new_bot_id" # Mock async save if needed, but repo.save is usually awaited in router
    
    # Needs to handle the async call in router. 
    # Since TestClient calls FastAPI app which runs async code, usually we mock the return of the dependency.
    # However, 'repo' in bot_router is a global instance. We patched it.
    # Is repo.save async? Yes, in previous snippets it was 'await repo.save(bot)'.
    mock_repo.save = AsyncMock(return_value="new_bot_id")

    payload = {
        "name": "Test Bot S4",
        "symbol": "BTC/USDT",
        "strategy_name": "TrendMaster",
        "timeframe": "1h",
        "mode": "simulated"
    }
    response = client.post("/api/bots/", json=payload)
    assert response.status_code == 200
    assert response.json() == {"id": "new_bot_id", "status": "created"}

def test_list_bots_endpoint(mock_repo):
    mock_bot = BotInstance(
        id="bot_1", user_id="default_user", name="B1", symbol="ETH/USDT", 
        strategy_name="S1", timeframe="1h", mode="simulated", status="active"
    )
    mock_repo.get_all_by_user = AsyncMock(return_value=[mock_bot])

    response = client.get("/api/bots/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "B1"

def test_update_bot_status(mock_repo):
    mock_repo.update_status = AsyncMock()
    
    response = client.patch("/api/bots/bot_1/status?status=paused")
    assert response.status_code == 200
    assert response.json() == {"message": "Bot paused"}
    mock_repo.update_status.assert_called_with("bot_1", "paused")

def test_webhook_trigger_engine(mock_repo, mock_engine):
    # Setup mock bot found in DB
    mock_bot_doc = {
        "_id": "507f1f77bcf86cd799439011", 
        "id": "507f1f77bcf86cd799439011",
        "status": "active", 
        "mode": "simulated",
        "symbol": "BTC/USDT",
        "amount": 1000
    }
    # repo.collection.find_one is called
    mock_repo.collection.find_one = AsyncMock(return_value=mock_bot_doc)

    payload = {
        "bot_id": "507f1f77bcf86cd799439011",
        "signal": 1,
        "price": 50000.0
    }
    
    response = client.post("/api/bots/webhook-signal", json=payload)
    
    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    
    # Verify engine was called
    mock_engine.process_signal.assert_called_once()
    # Check arguments: (bot version with string id, signal_data)
    args = mock_engine.process_signal.call_args[0]
    assert args[0]["id"] == "507f1f77bcf86cd799439011"
    assert args[1]["price"] == 50000.0

def test_webhook_bot_not_found(mock_repo):
    mock_repo.collection.find_one = AsyncMock(return_value=None)
    
    payload = {
        "bot_id": "507f1f77bcf86cd799439011",
        "signal": 1,
        "price": 50000.0
    }
    response = client.post("/api/bots/webhook-signal", json=payload)
    assert response.status_code == 404
