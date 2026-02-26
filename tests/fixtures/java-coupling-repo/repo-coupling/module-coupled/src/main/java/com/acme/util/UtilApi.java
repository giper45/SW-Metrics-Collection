package com.acme.util;

import com.acme.core.CoreApi;

public class UtilApi {
    public String decorate(String value) {
        if (value == null || value.isEmpty()) {
            return "n/a";
        }
        return "[" + value + "]";
    }

    public boolean isFromCore(CoreApi api) {
        return api != null;
    }
}
