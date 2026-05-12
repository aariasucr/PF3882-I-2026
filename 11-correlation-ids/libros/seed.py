import os
import random

from dotenv import load_dotenv
from faker import Faker
from sqlalchemy import text

load_dotenv("config.env")

from app import engine, Base, Libro
from sqlalchemy.orm import Session

fake = Faker("es_ES")

with Session(engine) as session:
    session.execute(text("TRUNCATE TABLE libros RESTART IDENTITY CASCADE"))
    session.commit()

with Session(engine) as session:
    for _ in range(20):
        session.add(Libro(
            titulo=fake.sentence(nb_words=random.randint(2, 5)).rstrip("."),
            autor_id=random.randint(1, 20),
        ))
    session.commit()

print("Seeded 20 libros.")
