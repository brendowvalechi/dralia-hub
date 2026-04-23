"""Testes do CRUD de leads."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_lead(client: AsyncClient, auth_headers):
    resp = await client.post("/leads", headers=auth_headers, json={"phone": "+5511999999999", "name": "João"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["phone"] == "+5511999999999"
    assert data["name"] == "João"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_create_lead_invalid_phone(client: AsyncClient, auth_headers):
    resp = await client.post("/leads", headers=auth_headers, json={"phone": "11999999999"})
    assert resp.status_code == 422  # Pydantic validation


@pytest.mark.asyncio
async def test_create_lead_duplicate(client: AsyncClient, auth_headers):
    await client.post("/leads", headers=auth_headers, json={"phone": "+5511888888888"})
    resp = await client.post("/leads", headers=auth_headers, json={"phone": "+5511888888888"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_leads(client: AsyncClient, auth_headers):
    await client.post("/leads", headers=auth_headers, json={"phone": "+5521999999991"})
    await client.post("/leads", headers=auth_headers, json={"phone": "+5521999999992"})

    resp = await client.get("/leads", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    assert "items" in data


@pytest.mark.asyncio
async def test_list_leads_search(client: AsyncClient, auth_headers):
    await client.post("/leads", headers=auth_headers, json={"phone": "+5531999990001", "name": "Maria Silva"})
    await client.post("/leads", headers=auth_headers, json={"phone": "+5531999990002", "name": "João Santos"})

    resp = await client.get("/leads?search=maria", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert any("Maria" in (item.get("name") or "") for item in data["items"])


@pytest.mark.asyncio
async def test_update_lead(client: AsyncClient, auth_headers):
    create = await client.post("/leads", headers=auth_headers, json={"phone": "+5541999999999"})
    lead_id = create.json()["id"]

    resp = await client.put(f"/leads/{lead_id}", headers=auth_headers, json={"name": "Atualizado"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Atualizado"


@pytest.mark.asyncio
async def test_delete_lead(client: AsyncClient, auth_headers):
    create = await client.post("/leads", headers=auth_headers, json={"phone": "+5551999999999"})
    lead_id = create.json()["id"]

    resp = await client.delete(f"/leads/{lead_id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get(f"/leads/{lead_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_optout_lead(client: AsyncClient, auth_headers):
    create = await client.post("/leads", headers=auth_headers, json={"phone": "+5561999999999"})
    lead_id = create.json()["id"]

    resp = await client.post(f"/leads/{lead_id}/optout", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "opted_out"
