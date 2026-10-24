"""Original, fixed demonstration quotes. No live broker adapter is registered."""
from decimal import Decimal
from typing import Protocol

QUOTES = {
    "RELIANCE": {"name": "Reliance Industries", "price": "2952.40", "change": 0.84, "sector": "Energy"},
    "TCS": {"name": "Tata Consultancy Services", "price": "4125.65", "change": -0.32, "sector": "Technology"},
    "HDFCBANK": {"name": "HDFC Bank", "price": "1728.30", "change": 1.12, "sector": "Banking"},
    "INFY": {"name": "Infosys", "price": "1892.15", "change": 0.67, "sector": "Technology"},
    "ICICIBANK": {"name": "ICICI Bank", "price": "1254.80", "change": 0.92, "sector": "Banking"},
    "ITC": {"name": "ITC Limited", "price": "486.25", "change": -0.41, "sector": "Consumer goods"},
}
STRATEGIES = [
    {"id": "momentum", "name": "Momentum Compass", "category": "Trend following", "risk": "Moderate", "description": "Explore momentum in a simulated equity basket. Orders are entered manually; automated signals are not enabled.", "instruments": "NSE equities", "color": "green"},
    {"id": "mean-reversion", "name": "Mean Reversion", "category": "Range trading", "risk": "High", "description": "A template for studying deviations from an average. No historical returns or live execution are claimed.", "instruments": "NSE equities", "color": "blue"},
    {"id": "balanced", "name": "Balanced Basket", "category": "Portfolio", "risk": "Moderate", "description": "Practice allocation in a paper portfolio. Activation saves configuration; automatic execution is not enabled.", "instruments": "NSE equities", "color": "amber"},
]

class BrokerAdapter(Protocol):
    mode: str
    def quote(self, symbol: str) -> Decimal: ...

class MockBroker:
    mode = "paper"
    def quote(self, symbol: str) -> Decimal:
        return Decimal(QUOTES[symbol]["price"])

broker: BrokerAdapter = MockBroker()
