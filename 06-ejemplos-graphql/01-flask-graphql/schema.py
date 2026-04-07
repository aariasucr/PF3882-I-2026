import strawberry
from strawberry.experimental.pydantic import type as pydantic_type

from models import Employee


@pydantic_type(model=Employee, all_fields=True)
class EmployeeType:
    pass


@strawberry.input
class CreateEmployeeInput:
    first_name: str
    last_name: str
    email: str


@strawberry.input
class UpdateEmployeeInput:
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None


# In-memory store for demo; replace with DB in production
EMPLOYEES: list[Employee] = [
    Employee(id=1, first_name="Jane", last_name="Doe",
             email="jane.doe@example.com"),
    Employee(id=2, first_name="John", last_name="Smith",
             email="john.smith@example.com"),
]
_next_id = 3


@strawberry.type
class QueryEmployee:
    @strawberry.field
    def employees(self) -> list[EmployeeType]:
        return [EmployeeType.from_pydantic(e) for e in EMPLOYEES]

    @strawberry.field
    def employee(self, id: int) -> EmployeeType | None:
        for e in EMPLOYEES:
            if e.id == id:
                return EmployeeType.from_pydantic(e)
        return None


@strawberry.type
class MutateEmployee:
    @strawberry.mutation
    def create_employee(self, input: CreateEmployeeInput) -> EmployeeType:
        global _next_id
        employee = Employee(
            id=_next_id,
            first_name=input.first_name,
            last_name=input.last_name,
            email=input.email,
        )
        _next_id += 1
        EMPLOYEES.append(employee)
        return EmployeeType.from_pydantic(employee)

    @strawberry.mutation
    def update_employee(self, id: int, input: UpdateEmployeeInput) -> EmployeeType | None:
        for i, e in enumerate(EMPLOYEES):
            if e.id == id:
                updated = Employee(
                    id=e.id,
                    first_name=input.first_name if input.first_name is not None else e.first_name,
                    last_name=input.last_name if input.last_name is not None else e.last_name,
                    email=input.email if input.email is not None else e.email,
                )
                EMPLOYEES[i] = updated
                return EmployeeType.from_pydantic(updated)
        return None

    @strawberry.mutation
    def delete_employee(self, id: int) -> bool:
        for i, e in enumerate(EMPLOYEES):
            if e.id == id:
                EMPLOYEES.pop(i)
                return True
        return False


schema = strawberry.Schema(query=QueryEmployee, mutation=MutateEmployee)
