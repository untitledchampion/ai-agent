"""Main data collector — pulls everything from ChatApp API into SQLite.

READ-ONLY: Only fetches data via GET requests, never modifies anything in ChatApp.
"""

import json
from datetime import datetime, timezone

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from .api_client import ChatAppClient
from .database import (
    Chat,
    Company,
    Employee,
    License,
    Message,
    Tag,
    async_session,
    init_db,
)

console = Console()


async def collect_all() -> None:
    """Run full data collection pipeline."""
    await init_db()
    console.print("[bold green]Database initialized[/]")

    async with ChatAppClient() as api:
        # Auth check
        me = await api.safe_get("/v1/me")
        if me and me.get("data"):
            d = me["data"]
            console.print(f"[bold]Authenticated as:[/] {d.get('fullName') or d.get('email', '?')}")
        else:
            console.print("[bold]Authenticated[/]")

        # 1. Companies — API: {companyId, name, ownerId, ...}
        companies = await api.get_companies()
        await _save_companies(companies)
        console.print(f"  Companies: {len(companies)}")

        # 2. Licenses — API: {licenseId, licenseName, messenger: [{type, ...}], companies: [id], ...}
        licenses_data = await api.get_licenses()
        await _save_licenses(licenses_data)
        console.print(f"  Licenses:  {len(licenses_data)}")

        # 3. Employees per company — API: {id, fullName, email, role: {name}, ...}
        total_employees = 0
        for comp in companies:
            cid = comp.get("companyId") or comp.get("id")
            if not cid:
                continue
            try:
                employees = await api.get_employees(cid)
                await _save_employees(cid, employees)
                total_employees += len(employees)
            except Exception as e:
                console.print(f"  [yellow]Employees for company {cid}: {e}[/]")
        console.print(f"  Employees: {total_employees}")

        # 4. Tags
        try:
            tags = await api.get_tags()
            await _save_tags(tags)
            console.print(f"  Tags:      {len(tags)}")
        except Exception as e:
            console.print(f"  [yellow]Tags: {e}[/]")

        # 5. Chats + Messages per license/messenger
        license_messengers = _extract_license_messengers(licenses_data)
        console.print(f"  Messenger channels: {len(license_messengers)}")
        for lic_id, m_type in license_messengers:
            console.print(f"    - {m_type} (license {lic_id})")

        total_chats = 0
        total_messages = 0

        for lic_id, m_type in license_messengers:
            try:
                chats = await api.get_all_chats(lic_id, m_type)
                await _save_chats(lic_id, m_type, chats)
                total_chats += len(chats)
                print(f"    {m_type} (lic {lic_id}): {len(chats)} chats found", flush=True)
            except Exception as e:
                print(f"  [WARN] Chats {m_type} (lic {lic_id}): {e}", flush=True)
                continue

            if not chats:
                continue

            for i, chat_data in enumerate(chats, 1):
                chat_id = str(chat_data["id"])
                chat_name = chat_data.get("name", "?")[:40]
                try:
                    messages = await api.get_all_messages(lic_id, m_type, chat_id)
                    chat_pk = await _get_chat_pk(chat_id, lic_id, m_type)
                    if chat_pk is not None and messages:
                        await _save_messages(chat_pk, messages)
                    total_messages += len(messages)
                    if i % 100 == 0 or i == len(chats) or len(messages) > 50:
                        print(f"      [{m_type}] {i}/{len(chats)} | +{len(messages)} msgs | total: {total_messages} | {chat_name}", flush=True)
                except Exception as e:
                    print(f"      [WARN] Chat {i}/{len(chats)} {chat_name}: {e}", flush=True)

        console.print()
        console.print("[bold green]Collection complete![/]")
        console.print(f"  Total chats:    {total_chats}")
        console.print(f"  Total messages: {total_messages}")


# ── Helpers ───────────────────────────────────────────────────────────


def _extract_license_messengers(
    licenses_data: list[dict],
) -> list[tuple[int, str]]:
    """Extract (license_id, messenger_type) pairs.

    Real API: {"licenseId": 70021, "messenger": [{"type": "telegram"}], "active": true}
    Only include active licenses with at least one messenger.
    """
    pairs: list[tuple[int, str]] = []
    for lic in licenses_data:
        if not lic.get("active", True):
            continue
        lic_id = lic.get("licenseId") or lic.get("id")
        if not lic_id:
            continue
        messengers = lic.get("messenger") or lic.get("messengers") or []
        if isinstance(messengers, list):
            for m in messengers:
                if isinstance(m, dict):
                    m_type = m.get("type")
                    if m_type:
                        pairs.append((lic_id, m_type))
    return pairs


async def _save_companies(companies: list[dict]) -> None:
    """Save companies. API field: companyId"""
    async with async_session() as session:
        for c in companies:
            cid = c.get("companyId") or c.get("id")
            if not cid:
                continue
            stmt = sqlite_upsert(Company).values(
                id=cid,
                name=c.get("name", ""),
                raw_json=json.dumps(c, ensure_ascii=False, default=str),
                synced_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "name": c.get("name", ""),
                    "raw_json": json.dumps(c, ensure_ascii=False, default=str),
                    "synced_at": datetime.now(timezone.utc),
                },
            )
            await session.execute(stmt)
        await session.commit()


async def _save_licenses(licenses: list[dict]) -> None:
    """Save licenses. API fields: licenseId, licenseName, messenger[], companies[], status{}"""
    async with async_session() as session:
        for lic in licenses:
            lic_id = lic.get("licenseId") or lic.get("id")
            if not lic_id:
                continue
            companies = lic.get("companies", [])
            company_id = companies[0] if companies else None
            messengers = lic.get("messenger") or []
            m_type = messengers[0]["type"] if messengers and isinstance(messengers[0], dict) else None
            status_obj = lic.get("status")
            status_str = status_obj.get("code") if isinstance(status_obj, dict) else str(status_obj) if status_obj else None
            stmt = sqlite_upsert(License).values(
                id=lic_id,
                company_id=company_id,
                name=lic.get("licenseName"),
                messenger_type=m_type,
                status=status_str,
                raw_json=json.dumps(lic, ensure_ascii=False, default=str),
                synced_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "name": lic.get("licenseName"),
                    "messenger_type": m_type,
                    "status": status_str,
                    "raw_json": json.dumps(lic, ensure_ascii=False, default=str),
                    "synced_at": datetime.now(timezone.utc),
                },
            )
            await session.execute(stmt)
        await session.commit()


async def _save_employees(company_id: int, employees: list[dict]) -> None:
    """Save employees. API: {id, fullName, email, role: {name}}"""
    async with async_session() as session:
        for e in employees:
            eid = e.get("id")
            if not eid:
                continue
            role_obj = e.get("role")
            role_name = role_obj.get("name") if isinstance(role_obj, dict) else None
            stmt = sqlite_upsert(Employee).values(
                id=eid,
                company_id=company_id,
                name=e.get("fullName") or e.get("name", ""),
                email=e.get("email"),
                role=role_name,
                raw_json=json.dumps(e, ensure_ascii=False, default=str),
                synced_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "name": e.get("fullName") or e.get("name", ""),
                    "email": e.get("email"),
                    "role": role_name,
                    "raw_json": json.dumps(e, ensure_ascii=False, default=str),
                    "synced_at": datetime.now(timezone.utc),
                },
            )
            await session.execute(stmt)
        await session.commit()


async def _save_tags(tags: list[dict]) -> None:
    async with async_session() as session:
        for t in tags:
            tid = t.get("id")
            if not tid:
                continue
            stmt = sqlite_upsert(Tag).values(
                id=tid,
                name=t.get("name", ""),
                color=t.get("color"),
                raw_json=json.dumps(t, ensure_ascii=False, default=str),
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={"name": t.get("name", ""), "color": t.get("color")},
            )
            await session.execute(stmt)
        await session.commit()


async def _save_chats(
    license_id: int, messenger_type: str, chats: list[dict],
) -> None:
    """Save chats. Fields: id, type, phone, username, name, status, responsible, tags, lastTime"""
    async with async_session() as session:
        for c in chats:
            responsible = c.get("responsible") or {}
            tags = c.get("tags") or []
            stmt = sqlite_upsert(Chat).values(
                chat_id=str(c["id"]),
                license_id=license_id,
                messenger_type=messenger_type,
                chat_type=c.get("type"),
                phone=c.get("phone"),
                username=c.get("username"),
                name=c.get("name"),
                status=c.get("status"),
                responsible_id=responsible.get("id") if isinstance(responsible, dict) else None,
                responsible_name=responsible.get("name") if isinstance(responsible, dict) else None,
                last_time=c.get("lastTime"),
                unread_messages=c.get("unreadMessages", 0),
                tags_json=json.dumps(tags, ensure_ascii=False, default=str),
                raw_json=json.dumps(c, ensure_ascii=False, default=str),
                synced_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["chat_id", "license_id", "messenger_type"],
                set_={
                    "name": c.get("name"),
                    "status": c.get("status"),
                    "responsible_id": responsible.get("id") if isinstance(responsible, dict) else None,
                    "responsible_name": responsible.get("name") if isinstance(responsible, dict) else None,
                    "last_time": c.get("lastTime"),
                    "unread_messages": c.get("unreadMessages", 0),
                    "tags_json": json.dumps(tags, ensure_ascii=False, default=str),
                    "raw_json": json.dumps(c, ensure_ascii=False, default=str),
                    "synced_at": datetime.now(timezone.utc),
                },
            )
            await session.execute(stmt)
        await session.commit()


async def _get_chat_pk(
    chat_id: str, license_id: int, messenger_type: str,
) -> int | None:
    async with async_session() as session:
        result = await session.execute(
            select(Chat.id).where(
                Chat.chat_id == str(chat_id),
                Chat.license_id == license_id,
                Chat.messenger_type == messenger_type,
            )
        )
        return result.scalar_one_or_none()


async def _save_messages(chat_pk: int, messages: list[dict]) -> None:
    """Save messages. API fields:
    {id, time, type, subtype, side (in/out), fromMe,
     message: {text, caption, file}, fromUser: {id, name, username, phone},
     created: {id (employeeId)}}
    """
    async with async_session() as session:
        for m in messages:
            msg_id = str(m.get("id", ""))
            if not msg_id:
                continue
            # Extract text from nested message object
            msg_obj = m.get("message") or {}
            text = msg_obj.get("text") if isinstance(msg_obj, dict) else None
            # Sender info
            from_user = m.get("fromUser") or {}
            sender_name = from_user.get("name") if isinstance(from_user, dict) else None
            # side = "in" (from client) or "out" (from operator)
            sender_type = m.get("side")  # "in" or "out"

            stmt = sqlite_upsert(Message).values(
                message_id=msg_id,
                chat_pk=chat_pk,
                timestamp=m.get("time"),
                sender_type=sender_type,
                sender_name=sender_name,
                message_type=m.get("type"),
                text=text,
                raw_json=json.dumps(m, ensure_ascii=False, default=str),
                synced_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["message_id", "chat_pk"],
                set_={
                    "text": text,
                    "raw_json": json.dumps(m, ensure_ascii=False, default=str),
                    "synced_at": datetime.now(timezone.utc),
                },
            )
            await session.execute(stmt)
        await session.commit()
