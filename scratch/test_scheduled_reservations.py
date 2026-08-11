import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from reservations import ReservationManager

def run_tests():
    mgr = ReservationManager()
    now = time.time()

    # 1. Basic reservation
    res1 = mgr.reserve("ran", "gnb-1", "user1", now + 60, now + 3600, "Test 1")
    assert res1["ok"] is True, f"Failed basic reserve: {res1}"
    print("Test 1 Passed: Basic reservation created")

    # 2. Overlap check - same user, overlapping window
    res2 = mgr.reserve("ran", "gnb-1", "user1", now + 1800, now + 5400, "Overlap self")
    assert res2["ok"] is False and res2["reason"] == "already_reserved", f"Overlap check failed for self: {res2}"
    print("Test 2 Passed: Overlap blocked for same user")

    # 3. Overlap check - different user, overlapping window
    res3 = mgr.reserve("ran", "gnb-1", "user2", now + 100, now + 500, "Overlap user2")
    assert res3["ok"] is False and res3["reason"] == "already_reserved", f"Overlap check failed for user2: {res3}"
    print("Test 3 Passed: Overlap blocked for different user")

    # 4. Consecutive reservation (non-overlapping) - same user
    res4 = mgr.reserve("ran", "gnb-1", "user1", now + 3600, now + 7200, "Slot 2")
    assert res4["ok"] is True, f"Failed non-overlapping slot: {res4}"
    print("Test 4 Passed: Consecutive slot created for same user")

    # 5. Status check
    st = mgr.status("ran", "gnb-1")
    assert st["active"] is None, "Should not be active yet"
    assert len(st["upcoming"]) == 2, f"Expected 2 upcoming, got {len(st['upcoming'])}"
    print("Test 5 Passed: Status shows upcoming slots correctly")

    # 6. Active slot check
    active_mgr = ReservationManager()
    active_mgr.reserve("ran", "gnb-1", "user1", now - 10, now + 300, "Active slot")
    st_active = active_mgr.status("ran", "gnb-1")
    assert st_active["active"] is not None, "Should have active slot"
    assert st_active["active"]["user"] == "user1", "Active user mismatch"
    assert active_mgr.get_active_reservation("ran", "gnb-1", "user1") is not None
    assert active_mgr.get_active_reservation("ran", "gnb-1", "user2") is None
    print("Test 6 Passed: Active slot detected correctly")

    # 7. Cancel upcoming slot
    up_id = res4["reservation"]["id"]
    cancel_res = mgr.cancel("ran", "gnb-1", "user1", up_id)
    assert cancel_res["ok"] is True, f"Failed cancel: {cancel_res}"
    assert len(mgr.status("ran", "gnb-1")["upcoming"]) == 1
    print("Test 7 Passed: Cancel upcoming slot succeeded")

    # 8. Cancel active slot should fail
    active_id = st_active["active"]["id"]
    cancel_active = active_mgr.cancel("ran", "gnb-1", "user1", active_id)
    assert cancel_active["ok"] is False and cancel_active["reason"] == "already_started"
    print("Test 8 Passed: Cannot cancel already started reservation")

    print("\nALL 8 RESERVATION BACKEND TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
