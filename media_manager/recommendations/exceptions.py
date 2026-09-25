class RecommendationError(RuntimeError):
    """Base exception for the recommendations domain."""


class RecommendationConfigurationError(RecommendationError):
    """Raised when a required provider or user mapping is not configured."""


class RecommendationProviderError(RecommendationError):
    """Raised when a history provider cannot return a valid response."""


class OllamaResponseError(RecommendationProviderError):
    """Raised when Ollama returns invalid or unvalidated output."""


class WebhookAuthenticationError(RecommendationError):
    """Raised when an incoming Plex webhook cannot be authenticated."""


class RecommendationRefreshInProgressError(RecommendationError):
    """Raised when the same user already has an active refresh in this process."""
