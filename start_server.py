import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        # Excludes directories from reload monitoring.
        # This fixes issues with shell expansion and path handling on Windows.
        reload_excludes=[
            "api/src/domain/strategiesopt/**",
            "api/data/**"
        ]
    )
