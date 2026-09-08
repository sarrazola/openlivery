"""The directory reports stored availability after the operator refreshes."""
from test_mobile_and_push import _client_with_portal, _sign_in


def test_member_directory_keeps_the_selected_availability(authenticated_client):
    client = authenticated_client
    customer = _client_with_portal(client)
    session = _sign_in(client, "owner@barberco.com", "legacy-portal-pw").json()
    headers = {"Authorization": f"Bearer {session['token']}"}
    path = f"/api/portal/{customer['portal_slug']}"
    for availability in ("away", "online"):
        changed = client.patch(f"{path}/me", headers=headers, json={"availability": availability})
        assert changed.status_code == 200
        rows = client.get(f"{path}/members", headers=headers)
        assert rows.status_code == 200
        member = next(row for row in rows.json() if row["id"] == session["user_id"])
        assert member["availability"] == availability
