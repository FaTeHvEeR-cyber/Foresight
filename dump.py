import asyncio
from backend.src.orchestrator.chart_picker import pick_chart
from backend.config.settings import Settings
import json

async def main():
    s = Settings(google_api_key="test-key", chart_picker_enabled=True)
    # Heuristic
    h_out = await pick_chart("forecast", {"status": "ok"}, settings=Settings(google_api_key=""))
    print("HEURISTIC:")
    print(json.dumps({"recommended_visualization": h_out}, indent=2))

    # We can fake the LLM output by mocking httpx
    import httpx
    def mock_handler(req: httpx.Request):
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": json.dumps({
                "charts": ["line_chart", "forecast_band_chart"],
                "reason": "Time series forecast with uncertainty band."
            })}]}}]
        })
    mock_transport = httpx.MockTransport(mock_handler)
    l_out = await pick_chart("forecast", {"status": "ok"}, settings=s, transport=mock_transport)
    print("LLM:")
    print(json.dumps({"recommended_visualization": l_out}, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
