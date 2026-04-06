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

import json
import operator
import random
import time
import bittensor as bt

from template.protocol import ALLOWED_OPS, MathSynapse
from template.validator.reward import get_rewards
from template.utils.uids import get_random_uids

_OPS = {"+": operator.add, "-": operator.sub, "*": operator.mul}


async def forward(self):
    """
    The forward function is called by the validator every time step.

    It is responsible for querying the network and scoring the responses.

    Args:
        self (:obj:`bittensor.neuron.Neuron`): The neuron object which contains all the necessary state for the validator.

    """
    # TODO(developer): Define how the validator selects a miner to query, how often, etc.
    # get_random_uids is an example method, but you can replace it with your own.
    miner_uids = get_random_uids(self, k=self.config.neuron.sample_size)

    op = random.choice(ALLOWED_OPS)
    a = random.randint(0, 99)
    b = random.randint(0, 99)
    expected = float(_OPS[op](a, b))
    synapse = MathSynapse(operand_a=a, operand_b=b, op=op)

    responses = await self.dendrite(
        axons=[self.metagraph.axons[uid] for uid in miner_uids],
        synapse=synapse,
        deserialize=True,
    )

    bt.logging.info(
        f"Math quiz {a} {op} {b} (expect {expected}), responses: {responses}"
    )

    rewards = get_rewards(self, expected=expected, responses=responses)

    scoreboard = {
        "expected": expected,
        "op": op,
        "a": a,
        "b": b,
        "uids": [int(u) for u in miner_uids],
        "responses": [
            float(r) if r is not None else None for r in responses
        ],
        "rewards": [float(x) for x in rewards.tolist()],
    }
    bt.logging.info("MATH_SCOREBOARD " + json.dumps(scoreboard))

    bt.logging.info(f"Scored responses: {rewards}")
    # Update the scores based on the rewards. You may want to define your own update_scores function for custom behavior.
    self.update_scores(rewards, miner_uids)
    time.sleep(5)
