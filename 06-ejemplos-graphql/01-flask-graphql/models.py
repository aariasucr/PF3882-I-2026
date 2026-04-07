from pydantic import BaseModel


class Employee(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
