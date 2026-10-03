"""
End-to-end smoke test for Research Bot.

Inserts a sample research_request (as a test user), waits for the worker
to process it, then prints the resulting ticket.

Requires:
  SUPABASE_URL, SUPABASE_SERVICE_KEY
  (and optionally a real USER_ID of an existing auth.users row)

Usage:
  python scripts/test_e2e.py
"""
import os
import sys
import time
from supabase import create_client

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]
TEST_USER_ID = os.environ.get("TEST_USER_ID")

sb = create_client(URL, KEY)

def get_test_user_id() -> str:
    if TEST_USER_ID:
        return TEST_USER_ID
    try:
        users = sb.auth.admin.list_users()
        if users and users.users:
            return users.users[0].id
    except Exception as e:
        print("Could not list users:", e)
    print("Set TEST_USER_ID env var to a valid auth.users id")
    sys.exit(1)


def main():
    user_id = get_test_user_id()
    print(f"Using user_id={user_id}")

    question = "What is the current market outlook for NVDA? Keep it brief."
    print(f"Inserting request: {question}")

    row = (
        sb.table("research_requests")
        .insert({
            "user_id": user_id,
            "question": question,
            "status": "pending",
        })
        .execute()
        .data[0]
    )
    req_id = row["id"]
    print(f"Request id: {req_id}")

    for i in range(60):
        time.sleep(5)
        r = (
            sb.table("research_requests")
            .select("status,error_message")
            .eq("id", req_id)
            .single()
            .execute()
            .data
        )
        status = r["status"]
        print(f"  [{i*5}s] status={status}")
        if status == "done":
            tickets = (
                sb.table("tickets")
                .select("*")
                .eq("request_id", req_id)
                .execute()
                .data
            )
            if tickets:
                t = tickets[0]
                print("\n=== TICKET ===")
                print(f"Symbol:     {t['symbol']}")
                print(f"Stance:     {t['stance']}")
                print(f"Confidence: {t['confidence']}%")
                print(f"Summary:    {t['summary']}")
                print(f"Sources:    {t.get('sources')}")
                return
            print("Status done but no ticket found")
            return
        if status == "error":
            print("Error:", r.get("error_message"))
            return

    print("Timed out waiting for worker")


if __name__ == "__main__":
    main()
