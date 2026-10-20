"""Downloads stay bounded by the requested file, even with slow readers."""

import asyncio
import os
import uuid

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.database import get_db
from app.main import app
from app.models import Message, MessageAttachment
from app.services import audio
from conftest import TestingSession, login_legacy_owner
from test_native_audio_playback import _setup


def _download(client, portal):
    path, headers, attachment_id = _setup(client)
    if not portal:
        path = "/api/conversations/" + path.split("/conversations/")[1]
        headers = {}
    return path, headers, attachment_id


@pytest.mark.parametrize("portal", [False, True])
def test_download_does_not_materialize_message_history(authenticated_client, portal):
    path, headers, attachment_id = _download(authenticated_client, portal)
    with TestingSession() as db:
        for index in range(300):
            message = Message(conversation_id=uuid.UUID(path.split("/")[-3]), role="user", content=f"History {index}")
            message.attachments.append(MessageAttachment(kind="audio", mime="audio/ogg", size_bytes=5, data=b"other"))
            db.add(message)
        db.commit()

    loaded = []
    def record_load(session, instance):
        if isinstance(instance, (Message, MessageAttachment)):
            loaded.append(instance)

    event.listen(Session, "loaded_as_persistent", record_load)
    try:
        response = authenticated_client.get(path, headers=headers)
    finally:
        event.remove(Session, "loaded_as_persistent", record_load)
    assert response.status_code == 200 and response.content == b"original-media"
    assert len(loaded) == 1
    assert isinstance(loaded[0], MessageAttachment) and str(loaded[0].id) == attachment_id


@pytest.mark.parametrize("portal", [False, True])
@pytest.mark.parametrize("downloads,pool_size", [(8, 2), (64, 10)])
def test_slow_downloads_release_pool_before_sending(authenticated_client, portal, downloads, pool_size):
    path, headers, _ = _download(authenticated_client, portal)
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=pool_size, max_overflow=0, pool_timeout=1)
    sessions = sessionmaker(bind=engine)

    def download_db():
        with sessions() as db:
            yield db

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = download_db

    async def exercise():
        ready = asyncio.Event()
        release = asyncio.Event()
        sending = 0

        async def slow_reader(scope, receive, send):
            async def delayed_send(message):
                nonlocal sending
                if message["type"] == "http.response.body":
                    sending += 1
                    if sending == downloads:
                        ready.set()
                    await release.wait()
                await send(message)
            await app(scope, receive, delayed_send)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=slow_reader), base_url="http://testserver",
            cookies=authenticated_client.cookies,
        ) as client:
            requests = [asyncio.create_task(client.get(path, headers=headers)) for _ in range(downloads)]
            try:
                await asyncio.wait_for(ready.wait(), timeout=10)
                assert engine.pool.checkedout() == 0
                with engine.connect() as connection:
                    assert connection.exec_driver_sql("SELECT 1").scalar() == 1
            finally:
                release.set()
                results = await asyncio.gather(*requests, return_exceptions=True)
            assert all(isinstance(result, httpx.Response) and result.status_code == 200 for result in results), results
            assert all(result.content == b"original-media" for result in results)

    try:
        asyncio.run(exercise())
    finally:
        app.dependency_overrides[get_db] = previous
        engine.dispose()


def test_conversion_runs_without_a_database_connection(authenticated_client, monkeypatch):
    path, headers, _ = _setup(authenticated_client)
    from conftest import test_engine

    async def convert(data):
        assert test_engine.pool.checkedout() == 0
        await asyncio.sleep(0)
        return b"converted"

    monkeypatch.setattr(audio, "to_native_audio", convert)
    response = authenticated_client.get(f"{path}?format=m4a", headers=headers)
    assert response.status_code == 200 and response.content == b"converted"


def test_portal_download_does_not_run_sync_sql_on_the_event_loop(authenticated_client):
    from conftest import test_engine

    path, headers, _ = _setup(authenticated_client)
    attachment_queries = []

    def check_thread(connection, cursor, statement, parameters, context, executemany):
        if "message_attachments" not in statement:
            return
        attachment_queries.append(statement)
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()

    event.listen(test_engine, "before_cursor_execute", check_thread)
    try:
        response = authenticated_client.get(path, headers=headers)
    finally:
        event.remove(test_engine, "before_cursor_execute", check_thread)
    assert response.status_code == 200 and response.content == b"original-media"
    assert attachment_queries


def test_admin_attachment_keeps_ownership_checks(authenticated_client):
    path, headers, _ = _download(authenticated_client, False)
    other_path, _, _ = _download(authenticated_client, False)
    swapped = path.rsplit("/", 1)[0] + "/" + other_path.rsplit("/", 1)[1]
    assert authenticated_client.get(swapped).status_code == 404
    login_legacy_owner(authenticated_client)
    assert authenticated_client.get(path, headers=headers).status_code == 404
