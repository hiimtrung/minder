from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass


class BaseModelMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    company_id: str = "default"
