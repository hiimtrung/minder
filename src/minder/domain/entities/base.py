from pydantic import BaseModel, ConfigDict

class BaseModelMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    company_id: str = "default"
