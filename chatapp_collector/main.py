"""Entry point — CLI for the ChatApp data collector."""

import asyncio
import sys

from rich.console import Console

from .collector import collect_all
from .database import async_session, init_db, Chat, Message, Company, Employee, License
from sqlalchemy import func, select

console = Console()


async def run_collect() -> None:
    """Full collection pipeline."""
    console.print("[bold]Starting ChatApp data collection...[/]\n")
    await collect_all()


async def run_stats() -> None:
    """Print DB statistics."""
    await init_db()
    async with async_session() as session:
        companies = (await session.execute(select(func.count(Company.id)))).scalar() or 0
        licenses = (await session.execute(select(func.count(License.id)))).scalar() or 0
        employees = (await session.execute(select(func.count(Employee.id)))).scalar() or 0
        chats = (await session.execute(select(func.count(Chat.id)))).scalar() or 0
        messages = (await session.execute(select(func.count(Message.id)))).scalar() or 0

    console.print("[bold]Database Statistics[/]")
    console.print(f"  Companies:  {companies}")
    console.print(f"  Licenses:   {licenses}")
    console.print(f"  Employees:  {employees}")
    console.print(f"  Chats:      {chats}")
    console.print(f"  Messages:   {messages}")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "collect"

    if command == "collect":
        asyncio.run(run_collect())
    elif command == "stats":
        asyncio.run(run_stats())
    else:
        console.print(f"[red]Unknown command:[/] {command}")
        console.print("Usage: python -m chatapp_collector [collect|stats]")
        sys.exit(1)


if __name__ == "__main__":
    main()
