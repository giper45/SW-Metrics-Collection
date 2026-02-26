def classify(value):
    if value < 0:
        return -1
    if value == 0:
        return 0
    if value > 10:
        return 2
    return 1
