import src.rapid_api.routes as routes


def test_run_jobs_route_http_scaffold(client, mock_requests_get):
    resp = client.post("/rapid-api/run-jobs", json={})
    assert resp.status_code == 200
