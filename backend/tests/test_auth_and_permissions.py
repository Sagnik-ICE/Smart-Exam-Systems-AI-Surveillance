def login(client, name: str, email: str, role: str):
    response = client.post(
        "/auth/login",
        json={"name": name, "email": email, "role": role},
    )
    assert response.status_code == 200
    return response.json()


def test_teacher_can_create_exam_and_student_cannot(client):
    teacher = login(client, "Teacher A", "teacherA@example.com", "teacher")
    student = login(client, "Student A", "studentA@example.com", "student")

    teacher_headers = {"Authorization": f"Bearer {teacher['access_token']}"}
    student_headers = {"Authorization": f"Bearer {student['access_token']}"}

    payload = {
        "title": "Permission Exam",
        "duration_minutes": 15,
        "questions": [{"id": "q1", "prompt": "Explain AI risk.", "type": "text"}],
    }

    ok = client.post("/exams", json=payload, headers=teacher_headers)
    assert ok.status_code == 200

    forbidden = client.post("/exams", json=payload, headers=student_headers)
    assert forbidden.status_code == 403


def test_protected_routes_require_auth(client):
    response = client.post(
        "/exams",
        json={
            "title": "No Token",
            "duration_minutes": 10,
            "questions": [{"id": "q1", "prompt": "x", "type": "text"}],
        },
    )
    assert response.status_code == 401
