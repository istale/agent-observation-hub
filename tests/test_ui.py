def test_index_ui_renders(app_client):
    response = app_client.get("/")

    assert response.status_code == 200
    assert "Agent Observation Hub" in response.text
