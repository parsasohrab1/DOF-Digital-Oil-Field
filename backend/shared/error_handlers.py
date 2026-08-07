"""
Centralized error handling
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)


class APIException(Exception):
    """Base API exception"""

    def __init__(self, status_code: int, detail: str, error_code: str = None):
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code or f"ERR_{status_code}"


def create_error_response(
    status_code: int, detail: str, error_code: str = None, correlation_id: str = None
):
    """Create standardized error response"""
    response = {
        "error": {
            "code": error_code or f"ERR_{status_code}",
            "message": detail,
            "status": status_code,
        }
    }

    if correlation_id:
        response["correlation_id"] = correlation_id

    return JSONResponse(status_code=status_code, content=response)


async def api_exception_handler(request: Request, exc: APIException):
    """Handle custom API exceptions"""
    correlation_id = request.headers.get("X-Correlation-ID")

    logger.error(
        f"API Exception: {exc.detail}",
        extra={
            "correlation_id": correlation_id,
            "status_code": exc.status_code,
            "error_code": exc.error_code,
        },
    )

    return create_error_response(
        status_code=exc.status_code,
        detail=exc.detail,
        error_code=exc.error_code,
        correlation_id=correlation_id,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    correlation_id = request.headers.get("X-Correlation-ID")

    errors = exc.errors()
    logger.warning(
        f"Validation Error: {errors}", extra={"correlation_id": correlation_id}
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "status": 422,
                "details": errors,
            },
            "correlation_id": correlation_id,
        },
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """Handle database errors"""
    correlation_id = request.headers.get("X-Correlation-ID")

    logger.error(
        f"Database Error: {str(exc)}",
        extra={"correlation_id": correlation_id},
        exc_info=True,
    )

    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database error occurred",
        error_code="DATABASE_ERROR",
        correlation_id=correlation_id,
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors"""
    correlation_id = request.headers.get("X-Correlation-ID")

    logger.error(
        f"Unexpected Error: {str(exc)}",
        extra={"correlation_id": correlation_id},
        exc_info=True,
    )

    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
        error_code="INTERNAL_ERROR",
        correlation_id=correlation_id,
    )


def register_error_handlers(app):
    """Register all error handlers to FastAPI app"""
    app.add_exception_handler(APIException, api_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
