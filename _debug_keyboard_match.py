#!/usr/bin/env python3
"""Verify that keyboard callback_data strings match router regexp exactly."""
import re

ROUTER_REGEXP = r"^(approve|decline):(\d+):([01]):(\d+)$"
DECLINE_REGEXP = r"^decline_reason:(\w+):(\d+):([01]):(\d+)$"
MOD_CANCEL_REGEXP = r"^moderation:cancel_decline:(\d+):([01]):(\d+)$"
USERINFO_REGEXP = r"^userinfo:(\d+)$"

# Generate EXACTLY as keyboards.py does (lines 144-168)
def gen_approve_callback(user_id, anon_flag, poster_id):
    return f"approve:{user_id}:{anon_flag}:{poster_id}"

def gen_decline_callback(user_id, anon_flag, poster_id):
    return f"decline:{user_id}:{anon_flag}:{poster_id}"

def gen_userinfo_callback(user_id):
    return f"userinfo:{user_id}"

# Real-world test cases extracted from bot logs / database
test_cases = [
    ("approve",  gen_approve_callback(1, "0", 99)),
    ("approve",  gen_approve_callback(540929323, "0", 211)),
    ("decline",  gen_decline_callback(1, "0", 1)),
    ("decline",  gen_decline_callback(540929323, "1", 100)),
    ("userinfo", gen_userinfo_callback(540929323)),
]

all_ok = True
print("=" * 70)
print(f"{'Type':<10} {'Expected':<40} {'Result':<10}")
print("-" * 70)

for ctype, cb_data in test_cases:
    matched = False
    for tag, rx in [("approve/decline", ROUTER_REGEXP),
                    ("userinfo", USERINFO_REGEXP),
                    ("decline_reason", DECLINE_REGEXP),
                    ("mod_cancel", MOD_CANCEL_REGEXP)]:
        m = re.match(rx, cb_data)
        if m:
            print(f"{ctype:<10} {cb_data:<40} MATCH ({tag})")
            matched = True
            break
    if not matched:
        print(f"⚠️ {ctype:<9} {cb_data:<40} ❌ NO MATCH AT ALL ⚠️")
        all_ok = False

print("=" * 70)
if all_ok:
    print("✅ ALL MATCH — router regexp is NOT the problem.")
else:
    print("❌ MISMATCH FOUND — keyboard and router use different formats!")
