"""
Lightweight mock LLM server — simulates ChatGPT-style API responses.
Start with: python tests/integration/mock_llm_server.py
Listens on http://localhost:9999

The server echoes back whatever content it receives in the request body,
so you can verify that tokens (<<P001>>) appear in the request and are
restored to original values in the response.
"""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer


class MockLLMHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[MockLLM] {fmt % args}")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {"raw": body}

        # Extract the user message
        messages = data.get("messages", [])
        user_content = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_content = msg.get("content", "")

        # Echo the content back — so tokens visible in request → visible in response
        # This lets the deanonymizer test that it restores tokens in the response.
        reply_text = f"[MockLLM Response] You sent: {user_content}"

        # Also echo any tokens we detected, to test that deanon runs on responses
        tokens_found = re.findall(r"<<[A-Z]+\d{3}>>", user_content)
        if tokens_found:
            reply_text += f"\n\nI noticed these tokens: {', '.join(tokens_found)}"

        response = {
            "id": "mock-completion-001",
            "object": "chat.completion",
            "model": "mock-gpt",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply_text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

        body_bytes = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)


if __name__ == "__main__":
    server = HTTPServer(("localhost", 9999), MockLLMHandler)
    print("[MockLLM] Listening on http://localhost:9999")
    print("[MockLLM] POST /v1/chat/completions  → echoes back request content")
    print("[MockLLM] Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[MockLLM] Stopped")
