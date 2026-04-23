"""Testes do ciclo de vida de campanhas."""
import pytest
from httpx import AsyncClient

CAMPAIGN_PAYLOAD = {
    "name": "Campanha Teste",
    "message_template": "{Olá|Oi}, {{nome}}! Aproveite nossa oferta.",
}


@pytest.mark.asyncio
async def test_create_campaign(client: AsyncClient, auth_headers):
    resp = await client.post("/campaigns", headers=auth_headers, json=CAMPAIGN_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Campanha Teste"
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_list_campaigns(client: AsyncClient, auth_headers):
    await client.post("/campaigns", headers=auth_headers, json=CAMPAIGN_PAYLOAD)
    resp = await client.get("/campaigns", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_update_campaign_draft(client: AsyncClient, auth_headers):
    create = await client.post("/campaigns", headers=auth_headers, json=CAMPAIGN_PAYLOAD)
    cid = create.json()["id"]

    resp = await client.put(f"/campaigns/{cid}", headers=auth_headers, json={"name": "Novo Nome"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Novo Nome"


@pytest.mark.asyncio
async def test_delete_campaign_draft(client: AsyncClient, auth_headers):
    create = await client.post("/campaigns", headers=auth_headers, json=CAMPAIGN_PAYLOAD)
    cid = create.json()["id"]

    resp = await client.delete(f"/campaigns/{cid}", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_campaign_status_filter(client: AsyncClient, auth_headers):
    await client.post("/campaigns", headers=auth_headers, json=CAMPAIGN_PAYLOAD)

    resp = await client.get("/campaigns?status=draft", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert all(item["status"] == "draft" for item in data["items"])


@pytest.mark.asyncio
async def test_cannot_delete_non_draft(client: AsyncClient, auth_headers):
    """Não deve ser possível excluir campanha não-draft sem leads disponíveis."""
    # Cria e tenta lançar (sem instâncias/leads, ficará em estado de erro)
    create = await client.post("/campaigns", headers=auth_headers, json=CAMPAIGN_PAYLOAD)
    cid = create.json()["id"]

    # Launch com 0 leads — status vai para running com total_leads=0
    await client.post(f"/campaigns/{cid}/launch", headers=auth_headers)

    # Não deve conseguir excluir campanha running
    resp = await client.delete(f"/campaigns/{cid}", headers=auth_headers)
    assert resp.status_code == 409
