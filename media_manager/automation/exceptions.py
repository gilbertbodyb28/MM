class AutomationError(RuntimeError):
    """Base exception for automatic download failures."""


class NoApprovedReleaseFoundError(AutomationError):
    """Raised when indexers have no approved release for a target."""


class AutomationTargetAlreadyManagedError(AutomationError):
    """Raised when another operation managed a target before this job did."""
