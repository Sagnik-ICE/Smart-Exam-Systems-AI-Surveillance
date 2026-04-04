import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import TeacherPanel from "./TeacherPanel";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: (...args) => mockGet(...args),
    post: (...args) => mockPost(...args)
  }
}));

describe("TeacherPanel", () => {
  it("renders summary after loading dashboard", async () => {
    mockGet.mockImplementation((url) => {
      if (url === "/rooms/mine") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/management/pending") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/management/users?role=student") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/analytics/teacher/exams") {
        return Promise.resolve({
          data: [
            {
              exam_id: 1,
              room_id: "TR5-ABC123",
              title: "Midterm",
              course_code: "CSE101",
              total_submissions: 1,
              submitted_count: 1,
              status: "completed"
            }
          ]
        });
      }
      if (url === "/analytics/exam/1") {
        return Promise.resolve({
          data: {
            exam_id: 1,
            summary: {
              total_submissions: 1,
              safe_count: 0,
              suspicious_count: 1,
              high_risk_count: 0,
              avg_suspicion_score: 42.5,
              total_paste_events: 2,
              total_tab_hidden_events: 1
            },
            submissions: [
              {
                submission_id: 11,
                student_name: "Student X",
                status: "submitted",
                suspicion_score: 42.5,
                risk_band: "Suspicious",
                event_counts: { paste: 2, tab_hidden: 1, window_blur: 0, keystroke: 10 },
                timeline: [{ type: "paste", timestamp_ms: 2000, metadata: { char_count: 50 } }]
              }
            ]
          }
        });
      }
      return Promise.reject(new Error("Unexpected URL"));
    });

    render(<TeacherPanel user={{ id: 5, role: "teacher", name: "Teacher" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Exams" }));
    const loadDashboardButton = await screen.findByRole("button", { name: "Load Dashboard" });
    fireEvent.click(loadDashboardButton);

    await waitFor(() => {
      expect(screen.getByText("Total Submissions")).toBeInTheDocument();
      expect(screen.getAllByText("Student X").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: "Open Student Monitor" }));

    await waitFor(() => {
      expect(screen.getByText("Behavior Replay")).toBeInTheDocument();
    });
  });
});
