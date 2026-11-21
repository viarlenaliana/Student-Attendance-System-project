from app import create_app
from app.extensions import db
from app.models.department import Department


app = create_app()


def test_crud():
    with app.app_context():
        test_department = Department(
            department_name="TEST_CRUD_DEPARTMENT",
            description="Testing SQLAlchemy CRUD"
        )

        try:
            # 1. CREATE
            db.session.add(test_department)
            db.session.commit()
            department_id = test_department.department_id
            print("CREATE: SUCCESS")

            # 2. READ
            department = db.session.get(Department, department_id)
            assert department is not None
            print("READ: SUCCESS")
            print("Department:", department.department_name)

            # 3. UPDATE
            department.description = "Updated successfully"
            db.session.commit()

            updated_department = db.session.get(
                Department, department_id
            )
            assert updated_department.description == "Updated successfully"
            print("UPDATE: SUCCESS")

            # 4. DELETE
            db.session.delete(updated_department)
            db.session.commit()

            deleted_department = db.session.get(
                Department, department_id
            )
            assert deleted_department is None
            print("DELETE: SUCCESS")

            print("\nALL CRUD TESTS PASSED!")

        except Exception as error:
            db.session.rollback()
            print("CRUD TEST FAILED!")
            print(error)

        finally:
            db.session.remove()


if __name__ == "__main__":
    test_crud()