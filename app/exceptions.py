"""Enterprise exception hierarchy for Gabster AI.

All custom domain exceptions inherit from GabsterException and provide
consistent error codes, machine-readable details, and HTTP status codes.
"""

from typing import Any, Dict, Optional
from fastapi import status


class GabsterException(Exception):
    """Root exception for all application-level errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


# ==============================================================================
# Authentication & Authorization Exceptions
# ==============================================================================

class AuthenticationError(GabsterException):
    def __init__(
        self,
        message: str = "Invalid or expired authentication credentials",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="AUTHENTICATION_FAILED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class PermissionDeniedError(GabsterException):
    def __init__(
        self,
        message: str = "You do not have permission to perform this action",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="PERMISSION_DENIED",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class TenantAccessForbiddenError(GabsterException):
    def __init__(
        self,
        message: str = "Cross-tenant access is strictly prohibited",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="TENANT_ISOLATION_VIOLATION",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


# ==============================================================================
# Resource & State Exceptions
# ==============================================================================

class ResourceNotFoundError(GabsterException):
    def __init__(
        self,
        resource_type: str,
        identifier: Any,
        details: Optional[Dict[str, Any]] = None,
    ):
        msg = f"{resource_type} with identifier '{identifier}' was not found"
        d = details or {}
        d.update({"resource_type": resource_type, "identifier": str(identifier)})
        super().__init__(
            message=msg,
            code="RESOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=d,
        )


class ResourceConflictError(GabsterException):
    def __init__(
        self,
        message: str = "Resource already exists or violates a unique constraint",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="RESOURCE_CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ValidationError(GabsterException):
    def __init__(
        self,
        message: str = "Request validation failed",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


# ==============================================================================
# Rate Limiting & Billing Exceptions
# ==============================================================================

class RateLimitExceededError(GabsterException):
    def __init__(
        self,
        message: str = "Rate limit threshold exceeded. Please throttle requests.",
        retry_after_seconds: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        d = details or {}
        if retry_after_seconds:
            d["retry_after_seconds"] = retry_after_seconds
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=d,
        )


class InsufficientCreditsError(GabsterException):
    def __init__(
        self,
        message: str = "Insufficient AI operation credits to complete this action",
        current_balance: Optional[float] = None,
        required_credits: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        d = details or {}
        if current_balance is not None:
            d["current_balance"] = current_balance
        if required_credits is not None:
            d["required_credits"] = required_credits
        super().__init__(
            message=message,
            code="INSUFFICIENT_CREDITS",
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            details=d,
        )


class SubscriptionInactiveError(GabsterException):
    def __init__(
        self,
        message: str = "Active subscription is required for this enterprise capability",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="SUBSCRIPTION_INACTIVE",
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            details=details,
        )


# ==============================================================================
# External Integration & Channel Exceptions
# ==============================================================================

class ChannelDeliveryError(GabsterException):
    def __init__(
        self,
        channel: str,
        message: str = "Failed to deliver message via external channel gateway",
        details: Optional[Dict[str, Any]] = None,
    ):
        d = details or {}
        d["channel"] = channel
        super().__init__(
            message=f"[{channel.upper()}] {message}",
            code="CHANNEL_DELIVERY_FAILED",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=d,
        )


class AIProviderError(GabsterException):
    def __init__(
        self,
        provider: str,
        message: str = "Upstream AI model provider returned an error",
        details: Optional[Dict[str, Any]] = None,
    ):
        d = details or {}
        d["provider"] = provider
        super().__init__(
            message=f"[{provider.upper()}] {message}",
            code="AI_PROVIDER_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=d,
        )


class GuardrailBreachError(GabsterException):
    def __init__(
        self,
        message: str = "Content blocked by active safety or compliance guardrail",
        violations: Optional[list] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        d = details or {}
        if violations:
            d["violations"] = violations
        super().__init__(
            message=message,
            code="GUARDRAIL_BLOCKED",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=d,
        )
