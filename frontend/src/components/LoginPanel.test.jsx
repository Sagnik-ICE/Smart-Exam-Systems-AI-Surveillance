import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import LoginPanel from "./LoginPanel";

const mockPost = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    post: (...args) => mockPost(...args)
  }
}));

describe("LoginPanel", () => {
  it("submits ID login and passes user/token to callback", async () => {
    const onLogin = vi.fn();
    mockPost.mockResolvedValueOnce({
      data: {
        access_token: "token-123",
        user: {
          id: 1,
          name: "Alice",
          email: "alice@example.com",
          role: "teacher",
          profile: {
            user_id: 1,
            department: "CSE",
            user_code: "TCH-1",
            contact_number: "12345",
            approval_status: "approved",
            is_active: true,
            assigned_teacher_id: null
          }
        }
      }
    });

    render(<LoginPanel onLogin={onLogin} />);

    fireEvent.change(screen.getByLabelText("User ID"), { target: { value: "TCH-1" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Teacher@123" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => {
      expect(onLogin).toHaveBeenCalledWith(
        {
          id: 1,
          name: "Alice",
          email: "alice@example.com",
          role: "teacher",
          profile: {
            user_id: 1,
            department: "CSE",
            user_code: "TCH-1",
            contact_number: "12345",
            approval_status: "approved",
            is_active: true,
            assigned_teacher_id: null
          }
        },
        "token-123"
      );
    });
  });

  it("shows API error details", async () => {
    mockPost.mockRejectedValueOnce({ response: { data: { detail: "Invalid credentials" } } });

    render(<LoginPanel onLogin={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("User ID"), { target: { value: "TCH-404" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrongpass" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => {
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
    });
  });
});
