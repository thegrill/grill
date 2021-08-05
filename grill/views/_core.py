_EMOJI_ID = "🕵"

# Very slightly modified USDView stylesheet for the push buttons.
_USDVIEW_PUSH_BUTTON_STYLE = """
QPushButton{
    /* gradient background */
    background-color: QLinearGradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgb(100, 100, 100), stop: 1 rgb(90, 90, 90));

    /* thin dark round border */
    border-width: 1px;
    border-color: rgb(42, 42, 42);
    border-style: solid;
    border-radius: 3;

    /* give the text enough space */
    padding: 3px;
    padding-right: 10px;
    padding-left: 10px;
}

/* Darker gradient when the button is pressed down */
QPushButton:pressed {
    background-color: QLinearGradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgb(50, 50, 50), stop: 1 rgb(60, 60, 60));
}

QPushButton:checked {
    background-color: QLinearGradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgb(60, 65, 70), stop: 1 rgb(70, 75, 80));
}

/* Greyed-out colors when the button is disabled */
QPushButton:disabled {
    background-color: QLinearGradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 rgb(66, 66, 66), stop: 1 rgb(56, 56, 56));
}

"""
