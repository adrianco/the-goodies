"""ADR-005 §2 rung 3 -- the three-way field merge, and the house's rung-2 rules.

The property that matters is deletion-safety: the base tells "deleted" from
"never existed", which is exactly what the dead two-way merge could not, and
why it resurrected deletions (design review F4 / ADR-008).
"""

from inbetweenies.sync.conflict import three_way_merge
from domains.house.manifest import HOUSE, merge_device, merge_automation


class TestThreeWayMerge:
    def test_one_side_changes_take_that_side(self):
        r = three_way_merge({"a": 1, "b": 2}, {"a": 1, "b": 3}, {"a": 9, "b": 2})
        assert r.merged == {"a": 9, "b": 3}
        assert r.conflicted == set()
        assert r.took_local == {"b"} and r.took_remote == {"a"}

    def test_a_deletion_on_one_side_wins_over_no_change_on_the_other(self):
        r = three_way_merge({"a": 1, "b": 2}, {"a": 1}, {"a": 1, "b": 2})
        assert r.merged == {"a": 1}, "the base says b existed; local removed it"

    def test_a_key_neither_side_ever_had_is_not_invented(self):
        r = three_way_merge({}, {"a": 1}, {"b": 2})
        assert r.merged == {"a": 1, "b": 2}

    def test_both_changed_to_the_same_value_agree(self):
        r = three_way_merge({"a": 1}, {"a": 5}, {"a": 5})
        assert r.merged == {"a": 5} and r.conflicted == set()

    def test_both_changed_differently_is_reported_not_guessed(self):
        r = three_way_merge({"a": 1, "b": 2}, {"a": 5, "b": 2}, {"a": 7, "b": 2})
        assert r.conflicted == {"a"}
        assert r.merged["a"] == 1, "left at the base for the caller to settle by rung 4"

    def test_delete_versus_edit_is_a_conflict(self):
        r = three_way_merge({"a": 1}, {}, {"a": 2})
        assert r.conflicted == {"a"}


class TestHouseMergeRules:
    def test_device_capabilities_union(self):
        owned = merge_device({"capabilities": ["a"]}, {"capabilities": ["a", "b"]}, {"capabilities": ["a", "c"]})
        assert owned == {"capabilities": ["a", "b", "c"]}

    def test_device_rule_declines_when_no_side_has_capabilities(self):
        assert merge_device({"x": 1}, {"x": 2}, {"x": 3}) == {}

    def test_automation_enabled_prefers_enabled(self):
        assert merge_automation({"enabled": True}, {"enabled": False}, {"enabled": True}) == {"enabled": True}
        assert merge_automation({"enabled": True}, {"enabled": False}, {"enabled": False}) == {"enabled": False}

    def test_the_house_manifest_registers_both(self):
        assert set(HOUSE.merge_rules) == {"device", "automation"}
