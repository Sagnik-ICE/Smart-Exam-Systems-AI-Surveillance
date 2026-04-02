from statistics import mean


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _risk_from_rate(rate: float, low: float, high: float) -> float:
    if rate <= low:
        return 0.0
    if rate >= high:
        return 1.0
    return _clamp((rate - low) / (high - low))


def _calculate_suspicion_assessment(
    events: list[dict],
    time_taken_seconds: int,
    exam_duration_minutes: int | None = None,
    question_count: int | None = None,
) -> tuple[float, str, dict]:
    tab_switches = 0
    hidden_intervals_ms = []
    hidden_start_ms = None
    paste_events = 0
    paste_char_count = 0
    large_paste_events = 0
    key_deltas = []
    burst_keystrokes = 0
    idle_gaps = 0
    prev_key_ts = None
    fullscreen_exits = 0
    fullscreen_not_entered = 0
    answer_changes = 0
    rapid_answer_jumps = 0
    webcam_no_face = 0
    webcam_multi_face = 0
    webcam_movement_alerts = 0
    eye_left_alerts = 0
    eye_right_alerts = 0

    for event in sorted(events, key=lambda item: item.get("timestamp_ms", 0)):
        event_type = event.get("event_type", "")
        metadata = event.get("metadata", {}) or {}
        ts = int(event.get("timestamp_ms", 0))

        if event_type in {"tab_hidden", "window_blur", "focus_lost"}:
            tab_switches += 1
            if hidden_start_ms is None:
                hidden_start_ms = ts
        if event_type in {"tab_visible", "window_focus", "focus_regained"} and hidden_start_ms is not None:
            hidden_intervals_ms.append(max(0, ts - hidden_start_ms))
            hidden_start_ms = None
        if event_type == "paste":
            paste_events += 1
            chars = int(metadata.get("char_count", 0))
            paste_char_count += chars
            if chars >= 120:
                large_paste_events += 1
        if event_type == "keystroke":
            if prev_key_ts is not None:
                delta = max(1, ts - prev_key_ts)
                key_deltas.append(delta)
                if delta < 28:
                    burst_keystrokes += 1
                if delta > 8000:
                    idle_gaps += 1
            prev_key_ts = ts
        if event_type == "fullscreen_exit":
            fullscreen_exits += 1
        if event_type == "fullscreen_not_entered":
            fullscreen_not_entered += 1
        if event_type == "answer_change":
            answer_changes += 1
            if abs(int(metadata.get("delta_chars", 0))) > 220:
                rapid_answer_jumps += 1
        if event_type == "webcam_no_face":
            webcam_no_face += 1
        if event_type == "webcam_multiple_faces":
            webcam_multi_face += 1
        if event_type == "webcam_unusual_movement":
            webcam_movement_alerts += 1
        if event_type == "eye_movement_alert":
            alert_type = str(metadata.get("alert_type") or metadata.get("eye_alert_type") or "").lower()
            if alert_type == "looking_left":
                eye_left_alerts += 1
            elif alert_type == "looking_right":
                eye_right_alerts += 1

    exam_minutes_taken = max(1.0, _safe_div(time_taken_seconds, 60.0))

    tab_rate = _safe_div(tab_switches, exam_minutes_taken)
    hidden_minutes = _safe_div(sum(hidden_intervals_ms), 60000)
    hidden_ratio = _safe_div(sum(hidden_intervals_ms), max(1, time_taken_seconds * 1000))
    paste_rate = _safe_div(paste_events, exam_minutes_taken)
    paste_chars_per_min = _safe_div(paste_char_count, exam_minutes_taken)
    fullscreen_rate = _safe_div(fullscreen_exits, exam_minutes_taken)
    eye_alert_rate = _safe_div(max(eye_left_alerts, eye_right_alerts), exam_minutes_taken)
    eye_balance_gap = abs(eye_left_alerts - eye_right_alerts)

    tab_score = _clamp((0.7 * _risk_from_rate(tab_rate, 0.05, 0.9)) + (0.3 * _risk_from_rate(hidden_ratio, 0.005, 0.08)))
    paste_score = _clamp(
        (0.3 * _risk_from_rate(paste_rate, 0.05, 0.8))
        + (0.4 * _risk_from_rate(paste_chars_per_min, 20, 220))
        + (0.3 * _risk_from_rate(large_paste_events, 0.2, 2.0))
    )

    if len(key_deltas) < 8:
        typing_score = 0.12
    else:
        avg_delta = mean(key_deltas)
        typing_score = _clamp(
            (0.35 * _risk_from_rate(_safe_div(1000, avg_delta), 2.5, 12.0))
            + (0.35 * _risk_from_rate(_safe_div(burst_keystrokes, len(key_deltas)), 0.08, 0.45))
            + (0.3 * _risk_from_rate(idle_gaps, 0.5, 4.0))
        )

    answer_change_score = _clamp(
        (0.5 * _risk_from_rate(_safe_div(answer_changes, exam_minutes_taken), 1.0, 9.0))
        + (0.5 * _risk_from_rate(rapid_answer_jumps, 0.2, 2.5))
    )

    webcam_score = _clamp(
        (0.4 * _risk_from_rate(webcam_no_face, 0.5, 6.0))
        + (0.3 * _risk_from_rate(webcam_multi_face, 0.2, 3.0))
        + (0.3 * _risk_from_rate(webcam_movement_alerts, 0.3, 4.0))
    )

    fullscreen_score = _clamp(
        (0.7 * _risk_from_rate(fullscreen_exits + fullscreen_not_entered, 0.1, 2.0))
        + (0.3 * _risk_from_rate(fullscreen_rate, 0.05, 0.8))
    )

    eye_score = _clamp(
        (0.55 * _risk_from_rate(eye_alert_rate, 0.2, 2.0))
        + (0.25 * _risk_from_rate(eye_balance_gap, 1.0, 5.0))
        + (0.20 if max(eye_left_alerts, eye_right_alerts) >= 5 else 0.0)
    )

    expected_seconds = max(60, (exam_duration_minutes or 30) * 60)
    rapid_completion_ratio = _safe_div(time_taken_seconds, expected_seconds)
    rapid_completion_score = _clamp(1.0 - _risk_from_rate(rapid_completion_ratio, 0.2, 0.8))

    component_weights = {
        "tab_focus": 0.28,
        "paste": 0.24,
        "typing_pattern": 0.07,
        "answer_velocity": 0.08,
        "fullscreen": 0.12,
        "rapid_completion": 0.08,
        "webcam": 0.1,
        "eye_movement": 0.03,
    }
    component_scores = {
        "tab_focus": tab_score,
        "paste": paste_score,
        "typing_pattern": typing_score,
        "answer_velocity": answer_change_score,
        "fullscreen": fullscreen_score,
        "rapid_completion": rapid_completion_score,
        "webcam": webcam_score,
        "eye_movement": eye_score,
    }

    confidence_scores = {
        "tab_focus": _clamp(0.45 + min(0.55, tab_switches * 0.07)),
        "paste": _clamp(0.3 + min(0.7, paste_events * 0.08)),
        "typing_pattern": _clamp(_safe_div(len(key_deltas), 40)),
        "answer_velocity": _clamp(_safe_div(answer_changes, max(4, (question_count or 4) * 2))),
        "fullscreen": _clamp(0.2 + min(0.8, fullscreen_exits * 0.2)),
        "eye_movement": _clamp(0.2 + min(0.8, max(eye_left_alerts, eye_right_alerts) * 0.18)),
        "rapid_completion": 0.9,
        "webcam": _clamp(0.15 + min(0.85, (webcam_no_face + webcam_multi_face + webcam_movement_alerts) * 0.1)),
    }

    weighted_risk = 0.0
    total_weight = 0.0
    for key, weight in component_weights.items():
        signal_weight = weight * (0.6 + 0.4 * confidence_scores[key])
        weighted_risk += signal_weight * component_scores[key]
        total_weight += signal_weight

    base_risk = _safe_div(weighted_risk, total_weight) if total_weight > 0 else 0.0

    fairness_factor = 1.0
    if question_count and question_count >= 8:
        fairness_factor -= 0.05
    if exam_duration_minutes and exam_duration_minutes >= 90:
        fairness_factor -= 0.06
    if hidden_minutes <= 0.2 and paste_events <= 1 and fullscreen_exits == 0:
        fairness_factor -= 0.05

    fairness_factor = _clamp(fairness_factor, 0.78, 1.05)
    suspicion_score = round(_clamp(base_risk * fairness_factor) * 100, 2)

    suspicious_threshold = 20.0
    high_threshold = 50.0

    if question_count and question_count >= 8:
        suspicious_threshold += 3
        high_threshold += 5
    if exam_duration_minutes and exam_duration_minutes >= 90:
        suspicious_threshold += 2
        high_threshold += 4
    if exam_duration_minutes and exam_duration_minutes <= 20:
        suspicious_threshold -= 1

    if suspicion_score <= suspicious_threshold:
        risk_band = "Safe"
    elif suspicion_score <= high_threshold:
        risk_band = "Suspicious"
    else:
        risk_band = "High Risk"

    assessment = {
        "component_scores": component_scores,
        "confidence": confidence_scores,
        "thresholds": {
            "suspicious": round(suspicious_threshold, 2),
            "high": round(high_threshold, 2),
        },
    }

    return suspicion_score, risk_band, assessment


def calculate_suspicion_score(
    events: list[dict],
    time_taken_seconds: int,
    exam_duration_minutes: int | None = None,
    question_count: int | None = None,
) -> tuple[float, str]:
    suspicion_score, risk_band, _ = _calculate_suspicion_assessment(
        events=events,
        time_taken_seconds=time_taken_seconds,
        exam_duration_minutes=exam_duration_minutes,
        question_count=question_count,
    )
    return suspicion_score, risk_band


def calculate_suspicion_assessment(
    events: list[dict],
    time_taken_seconds: int,
    exam_duration_minutes: int | None = None,
    question_count: int | None = None,
) -> tuple[float, str, dict]:
    return _calculate_suspicion_assessment(
        events=events,
        time_taken_seconds=time_taken_seconds,
        exam_duration_minutes=exam_duration_minutes,
        question_count=question_count,
    )


def merge_behavior_and_answer_risk(
    behavior_score: float,
    answer_similarity_risk: float,
    ai_style_risk: float,
) -> tuple[float, str]:
    behavior_risk = max(0.0, min(1.0, behavior_score / 100.0))
    similarity_risk = max(0.0, min(1.0, answer_similarity_risk))
    style_risk = max(0.0, min(1.0, ai_style_risk))

    final_risk = (0.65 * behavior_risk) + (0.2 * similarity_risk) + (0.15 * style_risk)
    final_score = round(final_risk * 100, 2)

    if behavior_risk >= 0.7:
        final_score = max(final_score, round(behavior_risk * 100 * 0.9, 2))

    final_score = max(final_score, round(behavior_risk * 100, 2))

    if final_score <= 30:
        risk_band = "Safe"
    elif final_score <= 60:
        risk_band = "Suspicious"
    else:
        risk_band = "High Risk"

    return final_score, risk_band

