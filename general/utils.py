import random


def get_delta(ds):
    factor = (-10, 10)
    sign = 1 if random.randrange(0, 2) else -1
    delta = random.randrange(factor[0], factor[1]) / 10.0

    return delta * sign
