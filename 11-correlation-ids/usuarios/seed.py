from dotenv import load_dotenv
import os
import random
from faker import Faker
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from main import Base, UserBook, UserRecord

load_dotenv("config.env")

engine = create_engine(os.getenv("DATABASE_URL"))
Base.metadata.create_all(engine)

fake = Faker("es_ES")

with Session(engine) as session:
    session.execute(text("TRUNCATE TABLE user_books RESTART IDENTITY CASCADE"))
    session.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))

    for _ in range(10):
        user = UserRecord(
            first_name=fake.first_name(),
            last_name=fake.last_name(),
            email=fake.unique.email(),
        )
        session.add(user)
        session.flush()

        book_ids = random.sample(range(1, 21), random.randint(0, 5))
        for book_id in book_ids:
            session.add(UserBook(user_id=user.id, book_id=book_id))

    session.commit()
    user_count = session.query(UserRecord).count()
    book_assoc_count = session.query(UserBook).count()

print(f"Seeded {user_count} users with {book_assoc_count} book associations.")
