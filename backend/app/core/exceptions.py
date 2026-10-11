class ApiError(Exception):
    def __init__(self, code, message, status_code=503, details=None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)
