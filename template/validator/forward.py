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
import time

import bittensor as bt

from template.validator.reward import get_rewards
from template.validator.synthetic_context import build_synthetic_drone_nav_synapse
from template.validator.ue_synthetic import maybe_teleport_and_frame
from template.utils.uids import get_random_uids


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
    synapse, synthetic_context = build_synthetic_drone_nav_synapse(
        validator_step=int(getattr(self, "step", 0)),
    )
    maybe_teleport_and_frame(synapse)
    try:
        merged = json.loads(synapse.synthetic_context_json or "{}")
        if isinstance(merged, dict):
            synthetic_context = merged
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    instruction = str(synapse.instruction)

    responses = await self.dendrite(
        axons=[self.metagraph.axons[uid] for uid in miner_uids],
        synapse=synapse,
        deserialize=False,
        timeout=float(self.config.neuron.timeout),
    )
    rewards, details = get_rewards(self, instruction=instruction, responses=responses)

    scoreboard = {
        "task_id": str(synapse.task_id),
        "instruction": instruction,
        "synthetic_context": synthetic_context,
        "uids": [int(u) for u in miner_uids],
        "responses": [
            {
                "action_id": getattr(r, "action_id", None),
                "confidence": getattr(r, "confidence", None),
                "error": getattr(r, "miner_error", None),
            }
            for r in responses
        ],
        "verification": details,
        "rewards": [float(x) for x in rewards.tolist()],
    }
    bt.logging.info("DRONE_SCOREBOARD " + json.dumps(scoreboard, ensure_ascii=False))

    bt.logging.info(f"Scored responses: {rewards}")
    # Update the scores based on the rewards. You may want to define your own update_scores function for custom behavior.
    self.update_scores(rewards, miner_uids)
    time.sleep(float(self.config.neuron.forward_sleep))
