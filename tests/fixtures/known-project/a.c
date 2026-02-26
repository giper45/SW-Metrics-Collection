#include "a.h"

/* multi-line comment
   second line */
int g1 = 1;
static int s1;
extern int e1;

int add(int x, int y) {
    // choose max
    if (x > y) {
        return x + y;
    } else {
        return y + x;
    }
}
