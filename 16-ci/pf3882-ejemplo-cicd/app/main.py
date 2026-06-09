import uvicorn

from app.fastapi_api import create_fastapi_app

if __name__ == "__main__":
    app = create_fastapi_app()

    print("API activa:")
    print("  REST:        http://localhost:8000/api/v1/tasklists")
    print("  GraphQL:     http://localhost:8000/graphql")
    print("  Swagger:     http://localhost:8000/docs")
    print("\nPresiona Ctrl+C para detener.\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
