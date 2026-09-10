import logging


logger = logging.getLogger("knowlayer.authentication")


def record_authentication_event(event: str, uid: str | None = None, success: bool | None = None):
    logger.info("authentication_event", extra={"event": event, "uid": uid, "success": success})