# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# TODO(developer): Set your name
# Copyright © 2023 <your name>

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
import typing

import numpy as np
import bittensor as bt


def get_rewards(
    self,
    expected: float,
    responses: typing.List[typing.Optional[float]],
) -> np.ndarray:
    """
    Winner-take-all (split ties): highest reward to miner(s) with smallest |response - expected|.
    """
    n = len(responses)
    errs = np.full(n, np.inf, dtype=np.float64)
    for i, r in enumerate(responses):
        if r is None:
            continue
        try:
            errs[i] = abs(float(r) - float(expected))
        except (TypeError, ValueError):
            errs[i] = np.inf

    finite = errs[np.isfinite(errs)]
    if finite.size == 0:
        bt.logging.warning("No valid miner responses for reward.")
        return np.zeros(n, dtype=np.float32)

    best = float(np.min(finite))
    winners = np.isfinite(errs) & (errs <= best + 1e-6)
    k = int(np.sum(winners))
    out = np.zeros(n, dtype=np.float32)
    if k > 0:
        out[winners] = 1.0 / k
    return out
