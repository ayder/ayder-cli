"""Tests for the keybinding registry."""

from ayder_cli.tui.keybindings import KEYBINDING_REGISTRY, get_keybindings_by_category


class TestKeybindingRegistry:
    def test_registry_is_not_empty(self):
        assert len(KEYBINDING_REGISTRY) > 0

    def test_registry_entries_have_three_fields(self):
        for entry in KEYBINDING_REGISTRY:
            assert len(entry) == 3, f"Entry {entry} should be (key, description, category)"

    def test_all_entries_have_nonempty_strings(self):
        for key, desc, cat in KEYBINDING_REGISTRY:
            assert key and isinstance(key, str)
            assert desc and isinstance(desc, str)
            assert cat and isinstance(cat, str)

    def test_categories_are_known(self):
        valid = {"Navigation", "Chat", "Panels", "General"}
        for _, _, cat in KEYBINDING_REGISTRY:
            assert cat in valid, f"Unknown category: {cat}"

    def test_ctrl_h_is_in_registry(self):
        keys = [k for k, _, _ in KEYBINDING_REGISTRY]
        assert "Ctrl+H" in keys


class TestGetKeybindingsByCategory:
    def test_returns_ordered_dict(self):
        grouped = get_keybindings_by_category()
        assert isinstance(grouped, dict)
        categories = list(grouped.keys())
        assert categories == ["Navigation", "Chat", "Panels", "General"]

    def test_each_group_has_entries(self):
        grouped = get_keybindings_by_category()
        for cat, entries in grouped.items():
            assert len(entries) > 0, f"Category {cat} has no entries"

    def test_entries_are_key_desc_tuples(self):
        grouped = get_keybindings_by_category()
        for cat, entries in grouped.items():
            for key, desc in entries:
                assert isinstance(key, str)
                assert isinstance(desc, str)
