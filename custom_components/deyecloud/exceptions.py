"""Exceptions for the DeyeCloud integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class DeyeCloudError(HomeAssistantError):
    """Base class for DeyeCloud errors."""


class DeyeCloudAuthError(DeyeCloudError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed") -> None:
        """Initialize auth error."""
        super().__init__(message)
        self.translation_key = "auth_failed"
        self.translation_placeholders = {"error": message}


class DeyeCloudConnectionError(DeyeCloudError):
    """Raised when the API is unreachable."""

    def __init__(self, message: str = "Connection failed") -> None:
        """Initialize connection error."""
        super().__init__(message)
        self.translation_key = "connection_failed"
        self.translation_placeholders = {"error": message}


class DeyeCloudApiError(DeyeCloudError):
    """Raised when the API returns an error response."""

    def __init__(self, message: str) -> None:
        """Initialize API error."""
        super().__init__(message)
        self.translation_key = "api_error"
        self.translation_placeholders = {"error": message}


class DeyeCloudNoStationsError(DeyeCloudError):
    """Raised when credentials are valid but no stations are accessible."""

    def __init__(self) -> None:
        """Initialize no-stations error."""
        super().__init__("No stations found for this account")
        self.translation_key = "no_stations_found"
