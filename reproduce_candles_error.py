import httpx
import asyncio
import json

async def test_candles_endpoint():
    url = "http://127.0.0.1:8000/api/market/candles"
    params = {
        "symbol": "AAVE/USDT",
        "timeframe": "5m",
        "limit": 10
    }
    
    print(f"Testing endpoint: {url}")
    print(f"Params: {params}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=30.0)
            
            print(f"Status Code: {response.status_code}")
            try:
                print(f"Response: {json.dumps(response.json(), indent=2)}")
            except:
                print(f"Response Text: {response.text}")
                
            if response.status_code == 200:
                print("SUCCESS")
            else:
                print("FAILED")
                
    except Exception as e:
        print(f"Error during request: {e}")

if __name__ == "__main__":
    asyncio.run(test_candles_endpoint())
