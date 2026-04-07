# Employee GraphQL API

FastAPI + Strawberry GraphQL API for the `Employee` model.

- **API:** http://127.0.0.1:8000  
- **Swagger UI:** http://127.0.0.1:8000/docs  
- **ReDoc:** http://127.0.0.1:8000/redoc  
- **GraphQL (GraphiQL):** http://127.0.0.1:8000/graphql  

Run the server:

```bash
uvicorn main:app --reload
```

---

## GraphQL examples

Field names in the schema use **camelCase** (e.g. `firstName`, `lastName`).

### Queries

**List all employees**

```graphql
query {
  employees {
    id
    firstName
    lastName
    email
  }
}
```

**Get one employee by id**

```graphql
query {
  employee(id: 2) {
    id
    firstName
    lastName
    email
  }
}
```

---

### Mutations

**Create an employee**

```graphql
mutation {
  createEmployee(
    firstName: "Bob"
    lastName: "Wilson"
    email: "bob.wilson@example.com"
  ) {
    id
    firstName
    lastName
    email
  }
}
```

**Update an employee** (omit arguments you don't want to change)

```graphql
mutation {
  updateEmployee(
    id: 1
    firstName: "Jane"
    email: "jane.updated@example.com"
  ) {
    id
    firstName
    lastName
    email
  }
}
```

**Delete an employee**

```graphql
mutation {
  deleteEmployee(id: 3)
}
```

Returns `true` if the employee was deleted, `false` if no employee with that id existed.
