"""
Molty Royale AI Agent entry point.
Runs the dashboard plus one or more agent heartbeats.
"""
import asyncio
import os
import sys

from bot.agent_profiles import bootstrap_profiles_if_needed
from bot.dashboard.server import start_dashboard
from bot.dashboard.state import dashboard_state
from bot.heartbeat import Heartbeat
from bot.utils.logger import get_logger

log = get_logger(__name__)

DASHBOARD_PORT = int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "8080")))


def main():
    log.info("Molty Royale AI Agent v2.0.0")
    log.info("Press Ctrl+C to stop")

    async def run_all():
        profile_store = await bootstrap_profiles_if_needed()
        heartbeats = [Heartbeat(profile, profile_store) for profile in profile_store.profiles]
        await start_dashboard(port=DASHBOARD_PORT)
        dashboard_state.bots_running = len(heartbeats)
        if not heartbeats:
            log.warning("No agent profiles configured. Dashboard will remain online.")
            await asyncio.Event().wait()
        await asyncio.gather(*(heartbeat.run() for heartbeat in heartbeats))

    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_all())
    except KeyboardInterrupt:
        log.info("Shutdown complete.")


if __name__ == "__main__":
    main()
