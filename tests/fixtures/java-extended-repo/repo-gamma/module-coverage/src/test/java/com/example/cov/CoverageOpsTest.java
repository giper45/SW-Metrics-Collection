package com.example.cov;

import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;

public class CoverageOpsTest {
    @Test
    void testMax() {
        CoverageOps ops = new CoverageOps();
        Assertions.assertEquals(7, ops.max(7, 3));
        Assertions.assertEquals(5, ops.max(2, 5));
    }

    @Test
    void testMin() {
        CoverageOps ops = new CoverageOps();
        Assertions.assertEquals(2, ops.min(2, 5));
    }
}
