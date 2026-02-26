package com.acme.core;

import com.acme.util.UtilApi;

public class CoreApi {
    private final UtilApi util = new UtilApi();

    public String buildLabel(int value) {
        return util.decorate("v-" + value);
    }
}
