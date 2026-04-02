def signup_and_login_authority(client):
    signup = client.post(
        "/auth/signup",
        json={
            "name": "Authority One",
            "department": "Admin",
            "user_code": "AUTH-T-001",
            "role": "authority",
            "email": "authority.one@example.com",
            "contact_number": "1111111111",
            "password": "Authority@123",
        },
    )
    assert signup.status_code == 200

    login = client.post(
        "/auth/login-id",
        json={"user_code": "AUTH-T-001", "password": "Authority@123"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def test_delete_user_removes_profile_and_user(client):
    authority_token = signup_and_login_authority(client)
    authority_headers = {"Authorization": f"Bearer {authority_token}"}

    create_teacher = client.post(
        "/management/create-user",
        json={
            "name": "Teacher One",
            "department": "CS",
            "user_code": "TCH-T-001",
            "role": "teacher",
            "email": "teacher.one@example.com",
            "contact_number": "2222222222",
            "password": "Teacher@123",
            "approve_now": True,
        },
        headers=authority_headers,
    )
    assert create_teacher.status_code == 200
    teacher_id = create_teacher.json()["id"]

    create_student = client.post(
        "/management/create-user",
        json={
            "name": "Student One",
            "department": "CS",
            "user_code": "STD-T-001",
            "role": "student",
            "email": "student.one@example.com",
            "contact_number": "3333333333",
            "password": "Student@123",
            "teacher_user_id": teacher_id,
            "approve_now": True,
        },
        headers=authority_headers,
    )
    assert create_student.status_code == 200
    student_id = create_student.json()["id"]

    delete_student = client.delete(f"/management/users/{student_id}", headers=authority_headers)
    assert delete_student.status_code == 200

    students_after = client.get("/management/users?role=student", headers=authority_headers)
    assert students_after.status_code == 200
    assert all(row["id"] != student_id for row in students_after.json())


def test_room_create_supports_total_questions_payload(client):
    authority_token = signup_and_login_authority(client)
    authority_headers = {"Authorization": f"Bearer {authority_token}"}

    create_teacher = client.post(
        "/management/create-user",
        json={
            "name": "Teacher Two",
            "department": "Math",
            "user_code": "TCH-T-002",
            "role": "teacher",
            "email": "teacher.two@example.com",
            "contact_number": "4444444444",
            "password": "Teacher@123",
            "approve_now": True,
        },
        headers=authority_headers,
    )
    assert create_teacher.status_code == 200

    teacher_login = client.post(
        "/auth/login-id",
        json={"user_code": "TCH-T-002", "password": "Teacher@123"},
    )
    assert teacher_login.status_code == 200
    teacher_headers = {"Authorization": f"Bearer {teacher_login.json()['access_token']}"}

    create_room = client.post(
        "/rooms",
        json={
            "course_name": "Compatibility Course",
            "course_code": "CMP-01",
            "exam_name": "Compatibility Exam",
            "duration_minutes": 30,
            "total_questions": 3,
        },
        headers=teacher_headers,
    )
    assert create_room.status_code == 200
    body = create_room.json()
    assert body["room_id"]
    assert body["exam_id"] > 0