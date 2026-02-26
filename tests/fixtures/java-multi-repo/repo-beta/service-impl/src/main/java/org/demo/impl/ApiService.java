package org.demo.impl;

import org.demo.api.ApiContract;

public class ApiService implements ApiContract {
    @Override
    public String format(String value) {
        if (value == null || value.isEmpty()) {
            return "empty";
        }
        if (value.length() > 8) {
            return value.substring(0, 8);
        }
        return value;
    }

    public int score(int value) {
        int score = 0;
        for (int i = 0; i < value; i++) {
            if (i % 2 == 0) {
                score++;
            }
        }
        return score;
    }
}
