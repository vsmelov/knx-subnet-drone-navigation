# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 Opentensor Foundation

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

import sys
import unittest

import bittensor as bt
import numpy as np

from neurons.validator import Validator
from template.base.validator import BaseValidatorNeuron
from template.protocol import MathSynapse
from template.utils.uids import get_random_uids
from template.validator.reward import get_rewards


class TemplateValidatorNeuronTestCase(unittest.TestCase):
    """
    This class contains unit tests for the RewardEvent classes.

    The tests cover different scenarios where completions may or may not be successful and the reward events are checked that they don't contain missing values.
    The `reward` attribute of all RewardEvents is expected to be a float, and the `is_filter_model` attribute is expected to be a boolean.
    """

    def setUp(self):
        sys.argv = sys.argv[0] + ["--config", "tests/configs/validator.json"]

        config = BaseValidatorNeuron.config()
        config.wallet._mock = True
        config.metagraph._mock = True
        config.subtensor._mock = True
        self.neuron = Validator(config)
        self.miner_uids = get_random_uids(self, k=10)

    def test_run_single_step(self):
        # TODO: Test a single step
        pass

    def test_sync_error_if_not_registered(self):
        # TODO: Test that the validator throws an error if it is not registered on metagraph
        pass

    def test_forward(self):
        # TODO: Test that the forward function returns the correct value
        pass

    def test_dummy_responses(self):
        step = self.neuron.step
        synapse = MathSynapse(operand_a=step, operand_b=2, op="*")
        expected = step * 2

        responses = self.neuron.dendrite.query(
            axons=[
                self.neuron.metagraph.axons[uid] for uid in self.miner_uids
            ],
            synapse=synapse,
            deserialize=True,
        )

        for response in responses:
            self.assertLess(abs(float(response) - float(expected)), 0.11)

    def test_reward(self):
        step = self.neuron.step
        synapse = MathSynapse(operand_a=step, operand_b=2, op="*")
        expected = float(step * 2)

        responses = self.neuron.dendrite.query(
            axons=[
                self.neuron.metagraph.axons[uid] for uid in self.miner_uids
            ],
            synapse=synapse,
            deserialize=True,
        )

        rewards = get_rewards(self.neuron, expected=expected, responses=responses)
        self.assertAlmostEqual(float(np.sum(rewards)), 1.0, places=5)
        self.assertTrue(np.all(rewards >= 0))

    def test_reward_with_nan(self):
        step = self.neuron.step
        synapse = MathSynapse(operand_a=step, operand_b=2, op="*")
        expected = float(step * 2)

        responses = self.neuron.dendrite.query(
            axons=[
                self.neuron.metagraph.axons[uid] for uid in self.miner_uids
            ],
            synapse=synapse,
            deserialize=True,
        )

        rewards = np.array(
            get_rewards(self.neuron, expected=expected, responses=responses),
            copy=True,
        )
        expected_rewards = rewards.copy()
        # Add NaN values to rewards
        rewards[0] = float("nan")

        with self.assertLogs(bt.logging, level="WARNING") as cm:
            self.neuron.update_scores(rewards, self.miner_uids)
