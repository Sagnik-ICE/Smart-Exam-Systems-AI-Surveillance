from app.services.scoring import calculate_suspicion_assessment


def _base_keystroke_events(count: int = 24):
    events = []
    for i in range(count):
        events.append(
            {
                "event_type": "keystroke",
                "timestamp_ms": i * 1000,
                "metadata": {},
            }
        )
    return events


def test_webcam_alerts_from_eye_pipeline_raise_webcam_component():
    base_events = _base_keystroke_events()
    with_alerts = base_events + [
        {
            "event_type": "eye_movement_alert",
            "timestamp_ms": 25000,
            "metadata": {"alert_type": "no_face_detected"},
        },
        {
            "event_type": "eye_movement_alert",
            "timestamp_ms": 32000,
            "metadata": {"alert_type": "multiple_people"},
        },
    ]

    base_score, _, base_assessment = calculate_suspicion_assessment(
        base_events, time_taken_seconds=600, exam_duration_minutes=30, question_count=5
    )
    alert_score, _, alert_assessment = calculate_suspicion_assessment(
        with_alerts, time_taken_seconds=600, exam_duration_minutes=30, question_count=5
    )

    assert base_assessment["component_scores"]["webcam"] == 0.0
    assert alert_assessment["component_scores"]["webcam"] > 0.0
    assert alert_score > base_score


def test_up_down_eye_alerts_contribute_to_eye_movement_component():
    events = _base_keystroke_events() + [
        {
            "event_type": "eye_movement_alert",
            "timestamp_ms": 12000,
            "metadata": {"alert_type": "looking_up"},
        },
        {
            "event_type": "eye_movement_alert",
            "timestamp_ms": 18000,
            "metadata": {"alert_type": "looking_down"},
        },
        {
            "event_type": "eye_movement_alert",
            "timestamp_ms": 24000,
            "metadata": {"alert_type": "looking_up"},
        },
        {
            "event_type": "eye_movement_alert",
            "timestamp_ms": 30000,
            "metadata": {"alert_type": "looking_down"},
        },
        {
            "event_type": "eye_movement_alert",
            "timestamp_ms": 36000,
            "metadata": {"alert_type": "looking_up"},
        },
        {
            "event_type": "eye_movement_alert",
            "timestamp_ms": 42000,
            "metadata": {"alert_type": "looking_down"},
        },
    ]

    _, _, assessment = calculate_suspicion_assessment(
        events, time_taken_seconds=600, exam_duration_minutes=30, question_count=5
    )

    assert assessment["component_scores"]["eye_movement"] > 0.0
