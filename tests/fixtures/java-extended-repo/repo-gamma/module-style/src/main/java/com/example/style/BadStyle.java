package com.example.style;

public class BadStyle {
    public int evaluate(int number) {
        if (number > 10)
            return number; // NeedBraces violation
        return 0;
    }

    public String longMessage() {
        return "This line is intentionally very long to trigger the LineLength checkstyle rule for deterministic warning output in tests.";
    }
}
