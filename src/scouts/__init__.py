"""Scout modules for on-chain and market data collection."""

from src.scouts.coingecko import CoinGeckoScout
from src.scouts.defillama import DefiLlamaScout
from src.scouts.deribit import DeribitScout
from src.scouts.github import GitHubScout

__all__ = [
    "CoinGeckoScout",
    "DefiLlamaScout",
    "DeribitScout",
    "GitHubScout",
]
