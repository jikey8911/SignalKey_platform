class DomainException(Exception):
    """Base class for domain exceptions"""
    pass

class InfrastructureServiceError(DomainException):
    def __init__(self, service_name: str, original_error: Exception):
        self.service_name = service_name
        self.original_error = original_error
        super().__init__(f"Error in infrastructure service '{service_name}': {original_error}")

class UserNotFoundError(DomainException):
    def __init__(self, user_id: str):
        super().__init__(f"User {user_id} not found")
