import requests
import ssl

def test_sync():
    print(f"SSL: {ssl.OPENSSL_VERSION}")
    
    targets = [
        ("Google", "https://www.google.com"),
        ("Binance", "https://api.binance.com/api/v3/ping"),
        ("Kraken", "https://api.kraken.com/0/public/Time")
    ]

    for name, url in targets:
        print(f"Checking {name}...")
        try:
            r = requests.get(url, timeout=5)
            print(f"  ✅ {name}: {r.status_code}")
        except Exception as e:
            print(f"  ❌ {name} Failed: {e}")

if __name__ == "__main__":
    test_sync()
