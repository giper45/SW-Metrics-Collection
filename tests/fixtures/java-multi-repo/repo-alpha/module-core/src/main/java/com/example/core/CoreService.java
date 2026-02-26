package com.example.core;

public class CoreService {
    public int classify(int value) {
        if (value < 0) {
            return -1;
        }
        if (value == 0) {
            return 0;
        }
        if (value > 100) {
            return 2;
        }
        return 1;
    }

    public int sumUpTo(int max) {
        int total = 0;
        for (int i = 0; i <= max; i++) {
            total += i;
        }
        return total;
    }
}
