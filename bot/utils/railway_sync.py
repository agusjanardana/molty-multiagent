"""
Railway Variables auto-sync.
Supports both legacy single-agent credentials and multi-agent ACCOUNTS_JSON persistence.
"""
import json
import os

import httpx
from bot.utils.logger import get_logger

log = get_logger(__name__)

RAILWAY_API_URL = "https://backboard.railway.com/graphql/v2"


def is_railway() -> bool:
    return bool(os.getenv("RAILWAY_PROJECT_ID"))


def is_setup_complete() -> bool:
    return os.getenv("SETUP_COMPLETE", "").lower() == "true"


def _get_railway_config() -> dict | None:
    token = os.getenv("RAILWAY_API_TOKEN", "")
    project_id = os.getenv("RAILWAY_PROJECT_ID", "")
    env_id = os.getenv("RAILWAY_ENVIRONMENT_ID", "")
    service_id = os.getenv("RAILWAY_SERVICE_ID", "")
    if not all([token, project_id, env_id, service_id]):
        if is_railway() and not token:
            log.warning("RAILWAY_API_TOKEN not set. Cannot auto-save credentials.")
        return None
    return {
        "token": token,
        "project_id": project_id,
        "environment_id": env_id,
        "service_id": service_id,
    }


async def _collection_upsert(variables_dict: dict) -> bool:
    config = _get_railway_config()
    if not config:
        return False

    mutation = """
    mutation variableCollectionUpsert($input: VariableCollectionUpsertInput!) {
        variableCollectionUpsert(input: $input)
    }
    """
    clean_vars = {k: v for k, v in variables_dict.items() if v}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                RAILWAY_API_URL,
                json={
                    "query": mutation,
                    "variables": {
                        "input": {
                            "projectId": config["project_id"],
                            "environmentId": config["environment_id"],
                            "serviceId": config["service_id"],
                            "variables": clean_vars,
                        }
                    },
                },
                headers={
                    "Authorization": f"Bearer {config['token']}",
                    "Content-Type": "application/json",
                },
                timeout=15.0,
            )
            data = resp.json()
            if "errors" in data:
                log.warning("Railway collection upsert error: %s", data["errors"])
                return False
            log.info("Railway sync: %d variables saved in 1 API call", len(clean_vars))
            return True
    except Exception as exc:
        log.warning("Railway collection upsert error: %s", exc)
        return False


async def sync_all_to_railway(creds: dict, agent_pk: str, owner_pk: str = ""):
    if not is_railway() or is_setup_complete():
        return

    from bot.config import (
        AUTO_IDENTITY,
        AUTO_SC_WALLET,
        AUTO_WHITELIST,
        ADVANCED_MODE,
        ENABLE_AGENT_TOKEN,
        ENABLE_MEMORY,
        LOG_LEVEL,
        ROOM_MODE,
    )

    all_vars = {
        "ROOM_MODE": ROOM_MODE,
        "ADVANCED_MODE": str(ADVANCED_MODE).lower(),
        "AUTO_WHITELIST": str(AUTO_WHITELIST).lower(),
        "AUTO_SC_WALLET": str(AUTO_SC_WALLET).lower(),
        "ENABLE_MEMORY": str(ENABLE_MEMORY).lower(),
        "ENABLE_AGENT_TOKEN": str(ENABLE_AGENT_TOKEN).lower(),
        "AUTO_IDENTITY": str(AUTO_IDENTITY).lower(),
        "LOG_LEVEL": LOG_LEVEL,
        "API_KEY": creds.get("api_key", ""),
        "AGENT_NAME": creds.get("agent_name", ""),
        "AGENT_WALLET_ADDRESS": creds.get("agent_wallet_address", ""),
        "OWNER_EOA": creds.get("owner_eoa", ""),
        "AGENT_PRIVATE_KEY": agent_pk,
        "OWNER_PRIVATE_KEY": owner_pk,
        "SETUP_COMPLETE": "true",
    }
    ok = await _collection_upsert(all_vars)
    if ok:
        log.info("Legacy single-agent credentials synced to Railway")
    else:
        log.warning("Railway sync failed for single-agent credentials")


async def sync_profiles_to_railway(profiles: list[dict]):
    if not is_railway():
        return

    from bot.agent_profiles import serialize_profiles_compact

    _, compressed = serialize_profiles_compact(profiles)
    all_vars = {
        "ACCOUNTS_B64_GZIP": compressed,
        "ACCOUNTS_JSON": "",
        "AGENT_BOOTSTRAP_COUNT": str(len(profiles)),
        "SETUP_COMPLETE": "true",
    }
    ok = await _collection_upsert(all_vars)
    if ok:
        log.info("Saved %d agent profile(s) into Railway ACCOUNTS_JSON", len(profiles))
    else:
        log.warning("Failed to persist ACCOUNTS_JSON to Railway")
