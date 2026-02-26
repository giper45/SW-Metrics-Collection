#include "a.h"
int g2;
static int s2 = 0;

int max(int a, int b) {
    if (a > b) {
        return a;
    }
    return b;
}

int calls(int v) {
    return max(v, g2);
}
