
4 entrypoints:
- write negotiable_constraints_update
- compute and read schedule_diff_to_add and schedule_diff_to_remove

CHAT: validate that everybody is ok with changes
- get_latest_schedule : update schedule from schedule_diff_to_add and schedule_diff_to_remove and read it
-> update if all diffs are confirmed

TODO Vivien:
- add field confirmed_by_staff (yes/no) to schedule_diff_to_add and schedule_diff_to_remove

