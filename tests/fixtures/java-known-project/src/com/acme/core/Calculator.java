package com.acme.core;

public class Calculator {
    public int sign(int value) {
        if (value > 0) {
            return 1;
        } else if (value < 0) {
            return -1;
        }
        return 0;
    }

    public int identity(int value) {
        return value;
    }
}
