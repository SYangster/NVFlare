# Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from .fedavg import FedAvg

import os

import torch

from net import Net

from nvflare.app_common.abstract.fl_model import FLModel, ParamsType


class PTFedAvg(FedAvg):
    """Controller for FedAvg Workflow. *Note*: This class is based on the experimental `ModelController`.
    Implements [FederatedAveraging](https://arxiv.org/abs/1602.05629).

    Provides the implementations for the `run` routine, controlling the main workflow:
        - def run(self)

    The parent classes provide the default implementations for other routines.

    Args:
        min_clients (int, optional): The minimum number of clients responses before
            Workflow starts to wait for `wait_time_after_min_received`. Note that the workflow will move forward
            when all available clients have responded regardless of this value. Defaults to 1000.
        num_rounds (int, optional): The total number of training rounds. Defaults to 5.
        persistor_id (str, optional): ID of the persistor component. Defaults to "persistor".
        ignore_result_error (bool, optional): whether this controller can proceed if client result has errors.
            Defaults to False.
        allow_empty_global_weights (bool, optional): whether to allow empty global weights. Some pipelines can have
            empty global weights at first round, such that clients start training from scratch without any global info.
            Defaults to False.
        task_check_period (float, optional): interval for checking status of tasks. Defaults to 0.5.
        persist_every_n_rounds (int, optional): persist the global model every n rounds. Defaults to 1.
            If n is 0 then no persist.
    """
    
    def save_model(self, model: FLModel, file_path: str):
        if not file_path:
            raise ValueError("invalid file path")

        dir_name = os.path.dirname(file_path)
        os.makedirs(dir_name, exist_ok=True)

        self.logger.info(f"save best model to {file_path} \n")
        torch.save(model.params, file_path)

    def init_model(self):
        net = Net()
        model = FLModel(params=net.state_dict(), params_type=ParamsType.FULL)
        return model
