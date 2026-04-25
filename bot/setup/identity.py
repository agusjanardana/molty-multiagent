"""
ERC-8004 identity registration via on-chain register() + POST /identity.
Never crashes; returns False when setup is incomplete so the caller can retry.
"""
from bot.api_client import MoltyAPI, APIError
from bot.web3.identity_contract import register_identity_onchain
from bot.config import ADVANCED_MODE
from bot.utils.logger import get_logger

log = get_logger(__name__)


async def ensure_identity(
    api: MoltyAPI,
    owner_private_key: str = "",
    profile: dict | None = None,
    save_profile=None,
    advanced_mode: bool = ADVANCED_MODE,
) -> bool:
    """Ensure ERC-8004 identity is registered for this agent profile."""
    try:
        identity = await api.get_identity()
        erc8004_id = identity.get("erc8004Id")
        if erc8004_id is not None:
            log.info("ERC-8004 identity already registered: tokenId=%s", erc8004_id)
            return True
    except APIError:
        pass

    if not advanced_mode:
        log.info(
            "ERC-8004 identity not registered. In default mode, "
            "register manually then set the tokenId."
        )
        return False

    if not owner_private_key:
        log.error("Advanced mode but no Owner private key available")
        return False

    log.info("Registering ERC-8004 identity on-chain...")
    token_id = await register_identity_onchain(owner_private_key)
    if token_id is None:
        log.info("Identity registration not completed. Will retry later.")
        return False

    try:
        result = await api.post_identity(token_id)
        log.info("Identity registered: %s", result)
        if profile is not None:
            profile["erc8004_token_id"] = token_id
        if save_profile:
            save_profile(erc8004_token_id=token_id)
        return True
    except APIError as exc:
        if exc.code == "CONFLICT":
            log.info("Identity already registered")
            return True
        log.error("Identity API registration failed: %s", exc)
        return False
