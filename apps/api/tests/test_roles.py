"""Role checks use authoritative Better Auth DB state, not untrusted claims."""
from sqlalchemy import text


def bearer(token_factory, subject="test-user-a", **claims):
    return {"Authorization": "Bearer " + token_factory(sub=subject, **claims)}


def test_default_user_and_forged_claims_cannot_access_admin(client, token_factory, set_auth_role):
    set_auth_role("test-user-a", "user")
    path = "/api/v1/admin/overview"
    assert client.get(path, headers=bearer(token_factory, role="super_admin")).status_code == 403
    assert client.get("/api/v1/admin/team", headers=bearer(token_factory)).status_code == 403


def test_admin_can_operate_store_but_cannot_manage_roles(client, token_factory, set_auth_role):
    set_auth_role("test-user-a", "admin")
    assert client.get("/api/v1/admin/overview", headers=bearer(token_factory)).status_code == 200
    assert client.get("/api/v1/admin/team", headers=bearer(token_factory)).status_code == 403
    assert client.patch("/api/v1/admin/team/test-user-b/role", json={"role":"super_admin"},
                        headers=bearer(token_factory)).status_code == 403


def test_super_admin_can_assign_and_revoke_role_without_deployment(client, token_factory, set_auth_role):
    set_auth_role("root", "super_admin")
    set_auth_role("test-user-a", "user")
    root = bearer(token_factory, subject="root")
    normal = bearer(token_factory)
    assert client.get("/api/v1/admin/overview", headers=normal).status_code == 403
    users = client.get("/api/v1/admin/team", headers=root)
    assert users.status_code == 200, users.text
    assert any(row["id"] == "test-user-a" for row in users.json()["items"])
    elevated = client.patch("/api/v1/admin/team/test-user-a/role",
                            json={"role":"admin"}, headers=root)
    assert elevated.status_code == 200, elevated.text
    assert client.get("/api/v1/admin/overview", headers=normal).status_code == 200
    demoted = client.patch("/api/v1/admin/team/test-user-a/role",
                           json={"role":"user"}, headers=root)
    assert demoted.status_code == 200
    assert client.get("/api/v1/admin/overview", headers=normal).status_code == 403


def test_ban_and_unknown_roles_fail_closed(client, token_factory, set_auth_role):
    set_auth_role("test-user-a", "admin", banned=True)
    assert client.get("/api/v1/admin/overview", headers=bearer(token_factory)).status_code == 403
    set_auth_role("test-user-a", "custom-not-approved")
    assert client.get("/api/v1/admin/overview", headers=bearer(token_factory)).status_code == 403


def test_super_admin_cannot_self_demote_or_remove_last(client, token_factory, set_auth_role):
    set_auth_role("root", "super_admin")
    set_auth_role("other", "super_admin")
    root = bearer(token_factory,subject="root")
    assert client.patch("/api/v1/admin/team/root/role",json={"role":"user"},headers=root).status_code == 409
    assert client.patch("/api/v1/admin/team/other/role",json={"role":"user"},headers=root).status_code == 200
    assert client.patch("/api/v1/admin/team/other/role",json={"role":"super_admin"},headers=root).status_code == 200
    assert client.patch("/api/v1/admin/team/nobody/role",json={"role":"admin"},headers=root).status_code == 404
    assert client.patch("/api/v1/admin/team/other/role",json={"role":"invalid"},headers=root).status_code == 422
