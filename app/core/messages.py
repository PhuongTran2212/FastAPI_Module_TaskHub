RESOURCE_NOT_FOUND = "{resource} not found"
TASK_CONFLICT = "Task data conflicts with database constraints"
DATA_CONFLICT = "Data conflicts with database constraints"
FIELD_CANNOT_BE_NULL = "Field cannot be null"
DUE_DATE_IN_PAST = "due_date cannot be in the past"

EMAIL_ALREADY_REGISTERED = "Email already registered"
INVALID_CREDENTIALS = "Incorrect email or password"
ACCOUNT_DISABLED = "User account is disabled"
AUTHENTICATION_REQUIRED = "Could not validate credentials"
PERMISSION_DENIED = "Not enough permissions"
INCORRECT_CURRENT_PASSWORD = "Current password is incorrect"
PASSWORD_TOO_LONG = "Password must be at most {limit} bytes in UTF-8"
PASSWORD_MUST_DIFFER = "New password must differ from current password"
FULL_NAME_CANNOT_BE_NULL = "full_name cannot be null"

INVALID_REFRESH_TOKEN = "Invalid refresh token"
REFRESH_TOKEN_REVOKED = "Refresh token has been revoked"
INVALID_TOKEN = "Invalid or expired token"
INVALID_TOKEN_TYPE = "Invalid token type"
INVALID_TOKEN_SUBJECT = "Invalid token subject"
INVALID_TOKEN_ID = "Invalid token identifier"

MEMBER_ALREADY_EXISTS = "User is already a member of this workspace"
PROJECT_ARCHIVED = "Project is archived; its content is read-only"
LABEL_NAME_EXISTS = "A label with this name already exists in the project"
COMMENT_DELETE_NOT_ALLOWED = (
    "Only the comment author or the workspace owner can delete this comment"
)
ASSIGNEE_NOT_ALLOWED = (
    "Assignee must be an OWNER or EDITOR member of the task's workspace"
)
TASK_DELETE_NOT_ALLOWED = (
    "Only the task creator or the workspace owner can delete this task"
)
OWNER_MEMBERSHIP_LOCKED = (
    "The workspace owner cannot be removed or have their role changed"
)
