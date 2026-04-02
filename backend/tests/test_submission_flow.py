def login(client, name: str, email: str, role: str):
    response = client.post(
        "/auth/login",
        json={"name": name, "email": email, "role": role},
    )
    assert response.status_code == 200
    return response.json()


def test_submission_scoring_and_csv_export(client):
    teacher = login(client, "Teacher B", "teacherB@example.com", "teacher")
    student = login(client, "Student B", "studentB@example.com", "student")

    teacher_headers = {"Authorization": f"Bearer {teacher['access_token']}"}
    student_headers = {"Authorization": f"Bearer {student['access_token']}"}

    exam_response = client.post(
        "/exams",
        json={
            "title": "Flow Exam",
            "duration_minutes": 20,
            "questions": [
                {"id": "q1", "prompt": "What is AI?", "type": "text"},
                {"id": "q2", "prompt": "Why monitor behavior?", "type": "text"},
            ],
        },
        headers=teacher_headers,
    )
    assert exam_response.status_code == 200
    exam_id = exam_response.json()["id"]

    start_response = client.post(
        "/submissions/start",
        json={"exam_id": exam_id},
        headers=student_headers,
    )
    assert start_response.status_code == 200
    submission_id = start_response.json()["submission_id"]

    events_response = client.post(
        "/events/batch",
        json={
            "submission_id": submission_id,
            "events": [
                {"event_type": "tab_hidden", "timestamp_ms": 1000, "metadata": {}},
                {"event_type": "paste", "timestamp_ms": 1700, "metadata": {"char_count": 80}},
                {"event_type": "keystroke", "timestamp_ms": 2200, "metadata": {"delta_ms": 30}},
            ],
        },
        headers=student_headers,
    )
    assert events_response.status_code == 200

    submit_response = client.post(
        f"/submissions/{submission_id}/submit",
        json={
            "answers": {
                "q1": "AI is intelligence demonstrated by machines.",
                "q2": "Behavior monitoring gives evidence-based integrity scoring.",
            },
            "time_taken_seconds": 95,
        },
        headers=student_headers,
    )
    assert submit_response.status_code == 200
    submit_payload = submit_response.json()
    assert submit_payload["risk_band"] in {"Safe", "Suspicious", "High Risk"}
    assert 0 <= submit_payload["suspicion_score"] <= 100

    dashboard_response = client.get(f"/analytics/exam/{exam_id}", headers=teacher_headers)
    assert dashboard_response.status_code == 200
    dashboard_payload = dashboard_response.json()
    assert dashboard_payload["summary"]["total_submissions"] == 1

    export_response = client.get(f"/analytics/exam/{exam_id}/export.csv", headers=teacher_headers)
    assert export_response.status_code == 200
    assert "text/csv" in export_response.headers["content-type"]
    assert "submission_id" in export_response.text

    export_pdf_response = client.get(f"/analytics/exam/{exam_id}/export.pdf", headers=teacher_headers)
    assert export_pdf_response.status_code == 200
    assert "application/pdf" in export_pdf_response.headers["content-type"]


def test_event_payload_guard_rejects_too_many_events(client):
    teacher = login(client, "Teacher C", "teacherC@example.com", "teacher")
    student = login(client, "Student C", "studentC@example.com", "student")

    teacher_headers = {"Authorization": f"Bearer {teacher['access_token']}"}
    student_headers = {"Authorization": f"Bearer {student['access_token']}"}

    exam_response = client.post(
        "/exams",
        json={
            "title": "Guard Exam",
            "duration_minutes": 10,
            "questions": [{"id": "q1", "prompt": "Describe one AI integrity signal.", "type": "text"}],
        },
        headers=teacher_headers,
    )
    assert exam_response.status_code == 200
    exam_id = exam_response.json()["id"]

    start_response = client.post(
        "/submissions/start",
        json={"exam_id": exam_id},
        headers=student_headers,
    )
    submission_id = start_response.json()["submission_id"]

    too_many_events = [
        {"event_type": "keystroke", "timestamp_ms": idx, "metadata": {"delta_ms": 10}}
        for idx in range(201)
    ]

    response = client.post(
        "/events/batch",
        json={"submission_id": submission_id, "events": too_many_events},
        headers=student_headers,
    )
    assert response.status_code == 422
