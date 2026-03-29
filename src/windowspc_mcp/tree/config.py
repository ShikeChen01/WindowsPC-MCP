"""Control type classification for interactive element detection."""

INTERACTIVE_CONTROL_TYPE_NAMES = frozenset({
    "ButtonControl", "ListItemControl", "MenuItemControl", "EditControl",
    "CheckBoxControl", "RadioButtonControl", "ComboBoxControl",
    "HyperlinkControl", "SplitButtonControl", "TabItemControl",
    "TreeItemControl", "DataItemControl", "HeaderItemControl",
    "TextBoxControl", "SpinnerControl", "ScrollBarControl",
})

DOCUMENT_CONTROL_TYPE_NAMES = frozenset({"DocumentControl"})

INFORMATIVE_CONTROL_TYPE_NAMES = frozenset({"TextControl", "ImageControl", "StatusBarControl"})

# Accessibility roles that indicate interactivity
INTERACTIVE_ROLES = frozenset({
    "PushButton", "SplitButton", "Link", "Text", "ComboBox", "DropList",
    "CheckButton", "RadioButton", "MenuItem", "ListItem", "PageTab",
    "OutlineItem", "Slider", "SpinButton", "Dial", "ScrollBar", "Grip",
    "ColumnHeader", "RowHeader", "Cell",
})

DEFAULT_ACTIONS = frozenset({"Click", "Press", "Jump", "Check", "Uncheck", "Double Click"})
