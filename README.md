# Student Attendance System

## 1. Project Overview
The Student Attendance System is a web-based application designed to manage student attendance efficiently. It supports attendance sessions, attendance recording, attendance result management, and attendance reports.

## 2. Technologies
- Backend: Python – Flask
- Frontend: HTML, CSS, Bootstrap, JavaScript
- Database: MySQL
- Development Tool: Visual Studio Code
- Version Control: Git & GitHub

## 3. Project Structure

```text
Student-Attendance-System-project/
│
├── app/
│   ├── __init__.py
│   ├── models/
│   ├── routes/
│   ├── templates/
│   └── static/
│       ├── css/
│       ├── js/
│       └── images/
│
├── requirement document/
├── venv/
├── .gitignore
├── config.py
├── main.py
└── requirements.txt
```

## 4. Folder and File Description

| Folder/File | Purpose |
|---|---|
| `app/` | Contains the main application components. |
| `app/__init__.py` | Initializes the Flask application. |
| `app/models/` | Contains database models and data-related logic. |
| `app/routes/` | Contains routes and request-handling logic. |
| `app/templates/` | Stores HTML pages displayed to users. |
| `app/static/css/` | Stores CSS files for styling. |
| `app/static/js/` | Stores JavaScript files. |
| `app/static/images/` | Stores images and other visual assets. |
| `requirement document/` | Contains project specifications and team documents. |
| `venv/` | Python virtual environment (not uploaded to GitHub). |
| `.gitignore` | Specifies files and folders Git should ignore. |
| `config.py` | Stores application configuration. |
| `main.py` | Entry point for running the Flask application. |
| `requirements.txt` | Lists Python dependencies. |

## 5. Architecture

The project follows the MVC (Model–View–Controller) architectural approach:

- **Model:** Handles data and database operations.
- **View:** Displays the user interface using HTML templates.
- **Controller:** Handles user requests and coordinates application logic.

## 6. Setup Instructions

1. Clone the repository.
2. Create and activate a Python virtual environment.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the application:

```bash
python main.py
```

5. Open the application at:

```text
http://127.0.0.1:5000
```

## 7. Team Development Rules

- Follow the approved project specification.
- Follow the agreed folder structure and naming conventions.
- Work on assigned features using separate Git branches.
- Do not modify shared files or function interfaces without team agreement.
- Test your changes before creating a Pull Request.
- Keep the `main` branch stable.
- 
