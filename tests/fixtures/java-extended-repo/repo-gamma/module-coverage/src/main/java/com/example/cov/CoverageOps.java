package com.example.cov;

public class CoverageOps {
    public int max(int left, int right) {
        if (left > right) {
            return left;
        }
        return right;
    }

    public int min(int left, int right) {
        if (left < right) {
            return left;
        }
        return right;
    }

    public int untouched(int value) {
        if (value < 0) {
            return -1;
        }
        return value;
    }
}
