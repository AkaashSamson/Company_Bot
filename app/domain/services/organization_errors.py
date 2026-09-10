class OrganizationError(Exception):
    """Base exception for organization domain failures."""


class NotFoundError(OrganizationError):
    pass


class ConflictError(OrganizationError):
    pass


class ForbiddenError(OrganizationError):
    pass


class AuthenticationError(OrganizationError):
    pass


class PersistenceError(OrganizationError):
    pass
