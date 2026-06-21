"""
Square Web API integration.

Triggers a payment on the paired Square hardware terminal — supports both
FIAT card payments and Bitcoin (via Square's crypto payment option).

Interface (to be implemented):
    class SquareClient:
        def request_payment(self, amount_cents: int, payment_type: str) -> None:
            # POST /v2/terminal/checkouts  (FIAT)
            # POST /v2/payments with source_type=CRYPTO  (Bitcoin)
            # Emits bus.payment_result(success, message) when terminal responds.

Configuration (via .env or environment variables):
    SQUARE_API_KEY        — sandbox or production API key
    SQUARE_TERMINAL_ID    — device_id of the paired Square terminal
    SQUARE_LOCATION_ID    — Square location ID
    SQUARE_ENVIRONMENT    — "sandbox" | "production"
"""
