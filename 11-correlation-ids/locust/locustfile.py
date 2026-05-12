import random
from faker import Faker
from locust import HttpUser, task, between

# Faker genera datos ficticios como nombres y títulos para las pruebas
fake = Faker()


# Clase que define el comportamiento de un usuario virtual durante la prueba de carga
class UsersAPIUser(HttpUser):
    # Tiempo de espera aleatorio entre 1 y 3 segundos entre cada tarea
    wait_time = between(1, 3)

    def _user_id(self):
        # Selecciona un ID de usuario aleatorio entre 1 y 10
        return random.randint(1, 10)

    def _libro_id(self):
        # Selecciona un ID de libro aleatorio entre 1 y 20
        return random.randint(1, 20)

    # @task(N) define la frecuencia relativa de cada tarea respecto a las demás.
    # Locust elige la próxima tarea de forma aleatoria ponderada: una tarea con peso 4
    # tiene el doble de probabilidad de ejecutarse que una con peso 2. Los pesos no son
    # porcentajes ni intervalos de tiempo — solo importan en relación entre sí.
    # Si se omite N y se usa solo @task, Locust asigna peso 1 por defecto,
    # lo que hace que todas las tareas tengan la misma probabilidad de ejecutarse.

    # Peso 3: esta tarea se ejecuta 3 veces por cada 2 ejecuciones de add_book_to_user
    # Simula un usuario listando todos los usuarios del sistema
    @task(3)
    def list_users(self):
        self.client.get("/users", name="GET /users")

    # Peso 4: la tarea más frecuente — simula consultar los libros de un usuario específico
    @task(4)
    def get_user_books(self):
        user_id = self._user_id()
        self.client.get(
            f"/users/{user_id}/books",
            name="GET /users/{user_id}/books",
        )

    # Peso 2: la tarea menos frecuente — simula agregar un libro nuevo a un usuario
    # El payload usa datos ficticios generados por Faker
    @task(2)
    def add_book_to_user(self):
        user_id = self._user_id()
        payload = {
            "autor_nombre": fake.name(),
            "titulo": fake.sentence(nb_words=4).rstrip("."),
        }
        self.client.put(
            f"/users/{user_id}/books",
            json=payload,
            name="PUT /users/{user_id}/books",
        )

    # Peso 3: simula consultar el detalle de un libro específico por su ID
    @task(3)
    def get_libro(self):
        libro_id = self._libro_id()
        self.client.get(
            f"/libros/{libro_id}",
            name="GET /libros/{libro_id}",
        )
