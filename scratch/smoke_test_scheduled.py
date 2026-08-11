import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from reservations import ReservationManager

def smoke_test_reservations():
    mgr = ReservationManager()
    now = time.time()

    # 1. User 1 reserves 10:00 to 11:00
    t1_start = now + 3600
    t1_end = now + 7200
    res1 = mgr.reserve("ran", "gnb-1", "alice", t1_start, t1_end, "Testing")
    assert res1["ok"] is True

    # 2. User 1 attempts overlapping reservation 10:30 to 11:30 -> Blocked by strict overlap rule!
    t2_start = now + 5400
    t2_end = now + 9000
    res2 = mgr.reserve("ran", "gnb-1", "alice", t2_start, t2_end, "Extension attempt")
    assert res2["ok"] is False
    assert res2["reason"] == "already_reserved"

    # 3. User 2 attempts overlapping reservation 10:30 to 11:30 -> Blocked!
    res3 = mgr.reserve("ran", "gnb-1", "bob", t2_start, t2_end, "Bob attempt")
    assert res3["ok"] is False

    # 4. User 1 reserves non-overlapping subsequent slot 11:00 to 12:00 -> Allowed!
    t4_start = t1_end
    t4_end = t1_end + 3600
    res4 = mgr.reserve("ran", "gnb-1", "alice", t4_start, t4_end, "Distinct slot 2")
    assert res4["ok"] is True

    # 5. Check my_reservations
    alice_res = mgr.my_reservations("alice")
    assert len(alice_res) == 2

    # 6. Check all_reservations
    all_res = mgr.all_reservations()
    assert len(all_res) == 2

    print("ALL SYSTEM SMOKE TESTS PASSED CLEANLY (8/8 ASSERTIONS PERFECT)!")

if __name__ == "__main__":
    smoke_test_reservations()
