"""
Dashboard shared state — bridge between bot engine and web dashboard.
Bot writes → Dashboard reads. Thread-safe via asyncio lock.
"""
import time
from collections import deque
from bot.utils.logger import get_logger

log = get_logger(__name__)

# Maximum log entries kept in memory
MAX_LOGS = 500


class DashboardState:
    """Singleton shared state between bot and dashboard."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # ── Agent state ────────────────────────────────────────
        self.agents: dict[str, dict] = {}  # {agent_id: {name, status, hp, ep, ...}}

        # ── Global stats ───────────────────────────────────────
        self.total_wins = 0
        self.total_moltz = 0
        self.total_smoltz = 0
        self.total_cross = 0.0
        self.bots_running = 0

        # ── Logs ───────────────────────────────────────────────
        self.global_logs: deque = deque(maxlen=MAX_LOGS)
        self.agent_logs: dict[str, deque] = {}  # {agent_id: deque}

        # ── Accounts ───────────────────────────────────────────
        self.accounts: list[dict] = []
        self.setup: dict = {
            "active": False,
            "message": "",
            "current": 0,
            "total": 0,
            "error": "",
        }
        self.owner_setup: dict[str, dict] = {}

        # ── Timestamps ─────────────────────────────────────────
        self.started_at = time.time()
        self.last_update = time.time()

    # ── Bot writes ─────────────────────────────────────────────

    def update_agent(self, agent_id: str, data: dict):
        """Update agent state from bot engine."""
        if agent_id not in self.agents:
            self.agents[agent_id] = {}
            self.agent_logs[agent_id] = deque(maxlen=MAX_LOGS)
        self.agents[agent_id].update(data)
        self.agents[agent_id]["last_update"] = time.time()
        self.last_update = time.time()

    def add_log(self, message: str, level: str = "info", agent_id: str = None):
        """Add log entry."""
        entry = {
            "ts": time.time(),
            "msg": message,
            "level": level,
            "agent": agent_id,
        }
        self.global_logs.append(entry)
        if agent_id and agent_id in self.agent_logs:
            self.agent_logs[agent_id].append(entry)

    def set_account(self, account_data: dict):
        """Add or update account."""
        api_key = account_data.get("api_key", "")
        for i, acc in enumerate(self.accounts):
            if acc.get("api_key") == api_key:
                self.accounts[i] = account_data
                return
        self.accounts.append(account_data)

    def set_setup_status(self, *, active: bool, message: str = "", current: int = 0,
                         total: int = 0, error: str = ""):
        self.setup.update({
            "active": active,
            "message": message,
            "current": current,
            "total": total,
            "error": error,
        })
        self.last_update = time.time()

    def set_owner_setup(self, owner_eoa: str, data: dict):
        key = (owner_eoa or "").lower()
        if not key:
            return
        current = self.owner_setup.get(key, {})
        current.update(data)
        current["updated_at"] = time.time()
        self.owner_setup[key] = current
        self.last_update = time.time()

    def clear_owner_setup(self, owner_eoa: str):
        key = (owner_eoa or "").lower()
        if key in self.owner_setup:
            del self.owner_setup[key]
            self.last_update = time.time()

    # ── Dashboard reads ────────────────────────────────────────

    def get_snapshot(self) -> dict:
        """Full state snapshot for dashboard API."""
        total_wins = sum(int(a.get("wins", 0) or 0) for a in self.agents.values())
        total_moltz = sum(int(a.get("moltz", 0) or 0) for a in self.agents.values())
        total_smoltz = sum(int(a.get("smoltz", 0) or 0) for a in self.agents.values())
        total_cross = sum(float(a.get("cross", 0) or 0) for a in self.agents.values())
        return {
            "agents": dict(self.agents),
            "stats": {
                "total_wins": total_wins,
                "total_moltz": total_moltz,
                "total_smoltz": total_smoltz,
                "total_cross": total_cross,
                "bots_running": self.bots_running,
                "agents_active": sum(1 for a in self.agents.values()
                                     if a.get("status") == "playing"),
                "agents_idle": sum(1 for a in self.agents.values()
                                   if a.get("status") in ("idle", "queuing")),
                "agents_dead": sum(1 for a in self.agents.values()
                                   if a.get("status") == "dead"),
                "agents_error": sum(1 for a in self.agents.values()
                                    if a.get("status") == "error"),
                "uptime": time.time() - self.started_at,
            },
            "accounts": self.accounts,
            "setup": dict(self.setup),
            "owner_setup": dict(self.owner_setup),
            "logs": list(self.global_logs)[-200:],
            "agent_logs": {k: list(v)[-100:] for k, v in self.agent_logs.items()},
        }


# Global singleton
dashboard_state = DashboardState()
