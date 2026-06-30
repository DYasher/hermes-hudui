def test_safety_route_is_registered(registered_routes) -> None:
    assert ("GET", "/api/safety") in registered_routes
