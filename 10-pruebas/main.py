import threading
import uvicorn
from app.database import engine
from app.models import Base
from app.flask_api import create_flask_app
from app.fastapi_api import create_fastapi_app
from app.graphql_api import create_graphql_app


def run_flask(port: int):
    app = create_flask_app()
    app.run(host="0.0.0.0", port=port, use_reloader=False)


def run_fastapi(port: int):
    app = create_fastapi_app()
    uvicorn.run(app, host="0.0.0.0", port=port)


def run_graphql(port: int):
    app = create_graphql_app()
    app.run(host="0.0.0.0", port=port, use_reloader=False)


if __name__ == "__main__":
    print("Creando tablas en la base de datos...")
    Base.metadata.create_all(bind=engine)
    print("Tablas listas.\n")

    threads = [
        threading.Thread(target=run_flask, args=(5000,),
                         daemon=True, name="flask-rest"),
        threading.Thread(target=run_fastapi, args=(
            8000,), daemon=True, name="fastapi"),
        threading.Thread(target=run_graphql, args=(
            5001,), daemon=True, name="graphql"),
    ]

    for t in threads:
        t.start()

    print("Todas las APIs activas:")
    print("  Flask REST:  http://localhost:5000/flask/tasklists")
    print("  FastAPI:     http://localhost:8000/fastapi/tasklists")
    print("  FastAPI docs: http://localhost:8000/fastapi/docs")
    print("  GraphQL:     http://localhost:5001/graphql")
    print("\nPresiona Ctrl+C para detener.\n")

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\nDeteniendo servidores...")
