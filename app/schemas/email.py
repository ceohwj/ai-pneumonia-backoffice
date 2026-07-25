from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.email_jobs import EmailJobStatus


class EmailJobResponse(BaseModel):
    id: int
    task_id: str
    record_id: int
    requested_by: int | None
    recipient_email: EmailStr
    subject: str
    status: EmailJobStatus
    retry_count: int = Field(ge=0)
    result_message: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
