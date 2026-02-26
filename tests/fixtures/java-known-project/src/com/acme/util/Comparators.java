package com.acme.util;

public class Comparators {
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
}
