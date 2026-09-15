import requests


def format_error(error):
    """Extract a human-readable message from a requests error."""
    if isinstance(error, requests.HTTPError):
        response = error.response
        if response is not None:
            try:
                body = response.json()
            except ValueError:
                body = None
            if isinstance(body, dict):
                detail = body.get("detail")
                if isinstance(detail, str):
                    return detail
                if isinstance(detail, list):
                    return "; ".join(item.get("msg", str(item)) for item in detail)
                return str(body)
            return str(error)
        return str(error)
    return str(error)


def unavailable(service_name):
    """Message shown when the FastAPI backend cannot serve the page data."""
    return (
        f"The {service_name} is unavailable. "
        "Check that the FastAPI backend is running at "
        "http://127.0.0.1:8000 and that you are logged in."
    )