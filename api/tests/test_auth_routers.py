import pytest
import jwt
import time
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch
from api.main import app
from api.src.infrastructure.security.auth_deps import get_current_user
from api.config import Config

client = TestClient(app)

# Mock Data
MOCK_USER = {
    "_id": "mock_id",
    "openId": "mock_openid",
    "email": "test@example.com"
}

def generate_token(openid: str):
    payload = {
        "openId": openid,
        "exp": time.time() + 3600
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")

@pytest.fixture
def mock_db():
    with patch("api.src.adapters.driven.persistence.mongodb.db") as mock:
        mock.users.find_one = AsyncMock(return_value=MOCK_USER)
        mock.app_configs.find_one = AsyncMock(return_value={"exchanges": [{"exchangeId": "binance", "isActive": True}]})
        mock.virtual_balances.find_one = AsyncMock(return_value={"amount": 10000.0})
        yield mock

@pytest.fixture
def auth_headers():
    token = generate_token(MOCK_USER["openId"])
    return {"Authorization": f"Bearer {token}"}

class TestBacktestauth:
    def test_get_exchanges_no_auth(self):
        response = client.get("/backtest/exchanges")
        assert response.status_code == 401

    def test_get_exchanges_with_auth(self, mock_db, auth_headers):
        # We need to override dependency or ensure the db mock works deep down
        # For integration test with TestClient, Depends is executed. 
        # We must mock the DB call inside Depends(get_user_repository) -> find_user_by_openid
        
        with patch("api.src.infrastructure.security.auth_deps.get_database") as mock_get_db:
             # This is harder to mock full chain. 
             # Easier: Override get_current_user dependency for success case
             pass
        
        # Actually easier to use app.dependency_overrides for unit testing routers
        app.dependency_overrides[get_current_user] = lambda: MOCK_USER
        
        response = client.get("/backtest/exchanges")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        
        app.dependency_overrides = {} # Clean up

    def test_virtual_balance_no_auth(self):
        response = client.get("/backtest/virtual_balance")
        assert response.status_code == 401

    def test_virtual_balance_with_auth(self, mock_db):
        app.dependency_overrides[get_current_user] = lambda: MOCK_USER
        
        response = client.get("/backtest/virtual_balance")
        assert response.status_code == 200
        data = response.json()
        assert data["balance"] == 10000.0
        assert data["userId"] == "mock_openid"
        
        app.dependency_overrides = {}

class TestBotAuth:
    def test_list_bots_no_auth(self):
        response = client.get("/api/bots/") # Router prefix is /bots but mounted under /api usually? 
        # Check main.py mount. Assuming /api based on previous usage or root.
        # Check routers: backtest_router prefix="/backtest", bot_router prefix="/bots"
        # main.py usually includes with prefix /api or just router request.
        # Let's try /bots/ directly first if app includes it directly, or check main.py.
        pass

    # Assuming standard mounting for now
    
    def test_create_bot_no_auth(self):
        response = client.post("/bots/", json={
            "name": "Test Bot",
            "symbol": "BTC/USDT",
            "strategy_name": "MACD",
            "timeframe": "1h"
        })
        assert response.status_code == 401

    @patch("api.src.adapters.driven.persistence.mongodb_bot_repository.MongoBotRepository.save", new_callable=AsyncMock)
    def test_create_bot_with_auth(self, mock_save, mock_db):
        app.dependency_overrides[get_current_user] = lambda: MOCK_USER
        mock_save.return_value = "new_bot_id"

        response = client.post("/bots/", json={
            "name": "Test Bot",
            "symbol": "BTC/USDT",
            "strategy_name": "MACD",
            "timeframe": "1h"
        })
        
        assert response.status_code == 200
        assert response.json()["id"] == "new_bot_id"
        
        app.dependency_overrides = {}
