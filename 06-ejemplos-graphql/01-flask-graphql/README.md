# Employee GraphQL API

Flask + Strawberry GraphQL API for the `Employee` model.

- **API:** http://127.0.0.1:5000
- **GraphQL (GraphiQL):** http://127.0.0.1:5000/graphql

Run the server:

```bash
pip install -r requirements.txt
python app.py
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
    input: {
      firstName: "Bob"
      lastName: "Wilson"
      email: "bob.wilson@example.com"
    }
  ) {
    id
    firstName
    lastName
    email
  }
}
```

**Update an employee** (omit fields in `input` you don't want to change)

```graphql
mutation {
  updateEmployee(
    id: 1
    input: { firstName: "Jane", email: "jane.updated@example.com" }
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
