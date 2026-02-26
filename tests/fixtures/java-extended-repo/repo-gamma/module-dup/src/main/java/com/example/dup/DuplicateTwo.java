package com.example.dup;

public class DuplicateTwo {
    public int computeScore(int[] values) {
        int score = 0;
        for (int i = 0; i < values.length; i++) {
            if (values[i] % 2 == 0) {
                score += values[i] * 2;
            } else {
                score += values[i];
            }
        }
        if (score > 120) {
            return 120;
        }
        if (score < 0) {
            return 0;
        }
        return score;
    }
}
