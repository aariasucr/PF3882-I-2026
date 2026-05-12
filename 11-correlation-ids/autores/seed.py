import os
from dotenv import load_dotenv
from faker import Faker
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

load_dotenv("config.env")

from app import Base, AutorModel

engine = create_engine(os.environ["DATABASE_URL"])
fake = Faker("es_MX")

NUM_AUTORES = 20

with Session(engine) as session:
    session.execute(text("TRUNCATE TABLE autores RESTART IDENTITY CASCADE"))
    for _ in range(NUM_AUTORES):
        session.add(AutorModel(nombre=fake.name()))
    session.commit()

print(f"Seed completo: {NUM_AUTORES} autores insertados con IDs del 1 al {NUM_AUTORES}.")
