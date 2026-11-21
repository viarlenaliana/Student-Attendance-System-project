from app.extensions import db
from sqlalchemy import text
from main import app


with app.app_context():
    try:
        with db.engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))

            print("Connected successfully!")
            print("Database:", result.scalar())

    except Exception as e:
        print("Connection failed!")
        print(e)