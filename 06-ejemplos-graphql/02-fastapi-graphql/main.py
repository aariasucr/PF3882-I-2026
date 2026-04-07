from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter
import strawberry

# Pydantic model (e.g. for REST or validation)
from pydantic import BaseModel


class Employee(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str


# Strawberry GraphQL type for Employee
@strawberry.type(
    description="Representa un empleado en el sistema (identificador, nombre, apellido y correo)."
)
class EmployeeType:
    id: int = strawberry.field(description="Identificador único del empleado.")
    first_name: str = strawberry.field(description="Nombre del empleado.")
    last_name: str = strawberry.field(description="Apellido del empleado.")
    email: str = strawberry.field(
        description="Correo electrónico del empleado.")

    @classmethod
    def from_pydantic(cls, e: Employee) -> "EmployeeType":
        return cls(id=e.id, first_name=e.first_name, last_name=e.last_name, email=e.email)


# In-memory demo data
EMPLOYEES: list[Employee] = [
    Employee(id=1, first_name="Jane", last_name="Doe",
             email="jane.doe@example.com"),
    Employee(id=2, first_name="John", last_name="Smith",
             email="john.smith@example.com"),
    Employee(id=3, first_name="Alice", last_name="Jones",
             email="alice.jones@example.com"),
]


@strawberry.type(description="Consultas de lectura: listar y obtener empleados.")
class Query:
    @strawberry.field(description="Devuelve la lista de todos los empleados.")
    def employees(self) -> list[EmployeeType]:
        return [EmployeeType.from_pydantic(e) for e in EMPLOYEES]

    @strawberry.field(
        description="Devuelve un empleado por su ID. Retorna null si no existe."
    )
    def employee(self, id: int) -> EmployeeType | None:
        for e in EMPLOYEES:
            if e.id == id:
                return EmployeeType.from_pydantic(e)
        return None


@strawberry.type(description="Operaciones de escritura: crear, actualizar y eliminar empleados.")
class Mutation:
    @strawberry.mutation(
        description="Crea un nuevo empleado. El ID se asigna automáticamente. Devuelve el empleado creado."
    )
    def create_employee(
        self,
        first_name: str,
        last_name: str,
        email: str,
    ) -> EmployeeType:
        new_id = max((e.id for e in EMPLOYEES), default=0) + 1
        emp = Employee(id=new_id, first_name=first_name,
                       last_name=last_name, email=email)
        EMPLOYEES.append(emp)
        return EmployeeType.from_pydantic(emp)

    @strawberry.mutation(
        description="Actualiza un empleado por ID. Solo se modifican los campos que envíes (el resto se mantiene). Devuelve null si no existe."
    )
    def update_employee(
        self,
        id: int,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
    ) -> EmployeeType | None:
        for i, e in enumerate(EMPLOYEES):
            if e.id == id:
                updated = Employee(
                    id=e.id,
                    first_name=first_name if first_name is not None else e.first_name,
                    last_name=last_name if last_name is not None else e.last_name,
                    email=email if email is not None else e.email,
                )
                EMPLOYEES[i] = updated
                return EmployeeType.from_pydantic(updated)
        return None

    @strawberry.mutation(
        description="Elimina un empleado por ID. Devuelve true si se eliminó, false si no existía."
    )
    def delete_employee(self, id: int) -> bool:
        for i, e in enumerate(EMPLOYEES):
            if e.id == id:
                EMPLOYEES.pop(i)
                return True
        return False


schema = strawberry.Schema(Query, Mutation)
graphql_app = GraphQLRouter(schema)

app = FastAPI(title="Employee GraphQL API")
app.include_router(graphql_app, prefix="/graphql")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
