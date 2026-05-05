"""
Genera listas de tareas y tareas aleatorias usando Faker.

Uso:
    python seed.py                  # 5 listas, hasta 5 tareas por lista
    python seed.py 10               # 10 listas
    python seed.py 10 8             # 10 listas, hasta 8 tareas por lista
    python seed.py --clear          # borra todos los datos y recarga los defaults
    python seed.py 10 --clear       # borra todo y carga 10 listas
"""

import sys
import random
from faker import Faker
from app.database import engine
from app.models import Base, TaskStatus
from app.service import TaskListService, TaskService

fake = Faker()
statuses = [s.value for s in TaskStatus]

tls_svc = TaskListService()
task_svc = TaskService()


def clear():
    for tl in tls_svc.get_all():
        tls_svc.delete(tl["id"])
    print("Datos borrados.\n")


def seed(num_tasklists: int = 5, max_tasks_per_list: int = 5):
    Base.metadata.create_all(bind=engine)

    for _ in range(num_tasklists):
        tl = tls_svc.create(fake.bs().title())
        print(f"[tasklist {tl['id']}] {tl['name']}")

        for _ in range(random.randint(1, max_tasks_per_list)):
            task = task_svc.create(
                description=fake.sentence(nb_words=random.randint(4, 8)).rstrip("."),
                tasklist_id=tl["id"],
                status=random.choice(statuses),
            )
            print(f"    [{task['status']:12s}] {task['description']}")

    print(f"\nListo — {num_tasklists} listas creadas.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--clear"]
    do_clear = "--clear" in sys.argv

    num = int(args[0]) if len(args) > 0 else 5
    max_tasks = int(args[1]) if len(args) > 1 else 5

    if do_clear:
        clear()

    seed(num_tasklists=num, max_tasks_per_list=max_tasks)
