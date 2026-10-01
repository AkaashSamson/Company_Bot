from typing import Dict, Optional
from app.domain.ports.channel_adapter import ChannelAdapterPort

_REGISTRY: Dict[str, ChannelAdapterPort] = {}


def register_channel_adapter(adapter: ChannelAdapterPort) -> None:
    _REGISTRY[adapter.channel_name.lower()] = adapter


def get_channel_adapter(channel_name: str) -> Optional[ChannelAdapterPort]:
    return _REGISTRY.get(channel_name.lower())


def clear_channel_registry() -> None:
    _REGISTRY.clear()
