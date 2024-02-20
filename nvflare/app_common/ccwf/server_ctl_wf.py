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

import time
from datetime import datetime
import logging

from nvflare.apis.wf_controller import WFController

from nvflare.apis.client import Client
from nvflare.apis.fl_constant import FLContextKey
from nvflare.apis.fl_context import FLContext
from nvflare.apis.impl.controller import ClientTask, Controller, Task
from nvflare.apis.shareable import ReturnCode, Shareable
from nvflare.apis.signal import Signal
from nvflare.app_common.app_constant import AppConstants
from nvflare.app_common.ccwf.common import (
    Constant,
    StatusReport,
    make_task_name,
    status_report_from_dict,
    topic_for_end_workflow,
)
from nvflare.fuel.utils.validation_utils import (
    DefaultValuePolicy,
    check_number_range,
    check_object_type,
    check_positive_int,
    check_positive_number,
    check_str,
    normalize_config_arg,
    validate_candidate,
    validate_candidates,
)
from nvflare.security.logging import secure_format_traceback

import logging
from typing import Callable, Dict, Optional

from net import Net

from nvflare.apis.wf_controller import WFController
from nvflare.app_common.abstract.fl_model import FLModel, ParamsType
from nvflare.app_common.aggregators.weighted_aggregation_helper import WeightedAggregationHelper
from nvflare.app_common.utils.fl_model_utils import FLModelUtils
from nvflare.app_common.utils.math_utils import parse_compare_criteria
from nvflare.security.logging import secure_format_traceback


class ClientStatus:
    def __init__(self):
        self.ready_time = None
        self.last_report_time = time.time()
        self.last_progress_time = time.time()
        self.num_reports = 0
        self.status = StatusReport()


class ServerSideControllerWF(WFController):
    def __init__(
        self,
        num_rounds: int,
        start_round: int = 0,
        task_name_prefix: str = "wf",
        configure_task_timeout=Constant.CONFIG_TASK_TIMEOUT,
        end_workflow_timeout=Constant.END_WORKFLOW_TIMEOUT,
        start_task_timeout=Constant.START_TASK_TIMEOUT,
        task_check_period: float = Constant.TASK_CHECK_INTERVAL,
        job_status_check_interval: float = Constant.JOB_STATUS_CHECK_INTERVAL,
        starting_client=None,
        starting_client_policy: str = DefaultValuePolicy.ANY,
        participating_clients=None,
        result_clients=None,
        result_clients_policy: str = DefaultValuePolicy.ALL,
        max_status_report_interval: float = Constant.PER_CLIENT_STATUS_REPORT_TIMEOUT,
        progress_timeout: float = Constant.WORKFLOW_PROGRESS_TIMEOUT,
        private_p2p: bool = True,
    ):
        super(ServerSideControllerWF, self).__init__()
        #Controller.__init__(self, task_check_period)
        participating_clients = normalize_config_arg(participating_clients)
        if participating_clients is None:
            raise ValueError("participating_clients must not be empty")

        self.task_name_prefix = task_name_prefix
        self.configure_task_name = make_task_name(task_name_prefix, Constant.BASENAME_CONFIG)
        self.configure_task_timeout = configure_task_timeout
        self.start_task_name = make_task_name(task_name_prefix, Constant.BASENAME_START)
        self.start_task_timeout = start_task_timeout
        self.end_workflow_timeout = end_workflow_timeout
        self.num_rounds = num_rounds
        self.start_round = start_round
        self.max_status_report_interval = max_status_report_interval
        self.progress_timeout = progress_timeout
        self.job_status_check_interval = job_status_check_interval
        self.starting_client = starting_client
        self.starting_client_policy = starting_client_policy
        self.participating_clients = participating_clients
        self.result_clients = result_clients
        self.result_clients_policy = result_clients_policy

        # make private_p2p bool
        check_object_type("private_p2p", private_p2p, bool)
        self.private_p2p = private_p2p

        self.client_statuses = {}  # client name => ClientStatus
        self.cw_started = False
        self.asked_to_stop = False
        self.workflow_id = None

        self.min_clients = 2

        check_positive_int("num_rounds", num_rounds)
        check_number_range("configure_task_timeout", configure_task_timeout, min_value=1)
        check_number_range("end_workflow_timeout", end_workflow_timeout, min_value=1)
        check_positive_number("job_status_check_interval", job_status_check_interval)
        check_number_range("max_status_report_interval", max_status_report_interval, min_value=10.0)
        check_number_range("progress_timeout", progress_timeout, min_value=5.0)
        check_str("starting_client_policy", starting_client_policy)

        if participating_clients and len(participating_clients) < 2:
            raise ValueError(f"Not enough participating_clients: must > 1, but got {participating_clients}")
        
        self.logger = logging.getLogger(self.__class__.__name__)

    # def __init__(
    #     self,
    #     min_clients: int,
    #     num_rounds: int,
    #     output_path: str,
    #     start_round: int = 1,
    #     stop_cond: str = None,
    #     resp_max_wait_time: float = 5,
    # ):
    #     super(ServerSideController, self).__init__()

    #     self.logger = logging.getLogger(self.__class__.__name__)


    #     self.task_name = "train"
    #     self.output_path = output_path
    #     self.min_clients = min_clients
    #     self.resp_max_wait_time = resp_max_wait_time
    #     self.num_rounds = num_rounds
    #     self.start_round = start_round
    #     self.current_round = start_round
    #     self.best_model: Optional[FLModel] = None
    #     self.aggr_params_helper = WeightedAggregationHelper()
    #     self.aggr_metrics_helper = WeightedAggregationHelper()
    #     self.params_type: Optional[ParamsType] = None
    #     if stop_cond:
    #         self.stop_criteria = parse_compare_criteria(stop_cond)
    #     else:
    #         self.stop_criteria = None

    
    def run(self):
        # self.logger.info("SLEEPING")
        # time.sleep(20)
        # self.logger.info("start_controller!!!\n \n")
        # self.start_controller()
        self.logger.info("control_flow!!!\n \n")
        self.control_flow(None)

    def start_controller(self):
        # wf_id = fl_ctx.get_prop(FLContextKey.WORKFLOW)
        # self.log_debug(fl_ctx, f"starting controller for workflow {wf_id}")
        # if not wf_id:
        #     raise RuntimeError("workflow ID is missing from FL context")
        # self.workflow_id = wf_id
        self.workflow_id = 'WFCommunicator' #"cyclic_ccwf"

        # all_clients = self._engine.get_clients()
        # if len(all_clients) < 2:
        #     raise RuntimeError(f"this workflow requires at least 2 clients, but only got {all_clients}")

        all_client_names = self.get_site_names()
        print(f"\t{all_client_names=}")
        #all_client_names = [t.name for t in all_clients]
        self.participating_clients = validate_candidates(
            var_name="participating_clients",
            candidates=self.participating_clients,
            base=all_client_names,
            default_policy=DefaultValuePolicy.ALL,
            allow_none=False,
        )

        self.starting_client = validate_candidate(
            var_name="starting_client",
            candidate=self.starting_client,
            base=self.participating_clients,
            default_policy=self.starting_client_policy,
            allow_none=True,
        )

        self.result_clients = validate_candidates(
            var_name="result_clients",
            candidates=self.result_clients,
            base=self.participating_clients,
            default_policy=self.result_clients_policy,
            allow_none=True,
        )

        for c in self.participating_clients:
            self.client_statuses[c] = ClientStatus()

    def prepare_config(self) -> dict:
        return {}

    def sub_flow(self, abort_signal: Signal):
        pass

    def control_flow(self, abort_signal: Signal):


        all_client_names = self.get_site_names()
        self.participating_clients = validate_candidates(
            var_name="participating_clients",
            candidates=self.participating_clients,
            base=all_client_names,
            default_policy=DefaultValuePolicy.ALL,
            allow_none=False,
        )
        self.starting_client = validate_candidate(
            var_name="starting_client",
            candidate=self.starting_client,
            base=self.participating_clients,
            default_policy=self.starting_client_policy,
            allow_none=True,
        )

        self.result_clients = validate_candidates(
            var_name="result_clients",
            candidates=self.result_clients,
            base=self.participating_clients,
            default_policy=self.result_clients_policy,
            allow_none=True,
        )
        self.workflow_id = 'WFCommunicator'


        # wait for every client to become ready
        self.logger.info(f"Waiting for clients to be ready: {self.participating_clients}")

        # GET STARTED
        self.logger.info(f"Configuring clients {self.participating_clients} for workflow {self.workflow_id}")

        learn_config = {
            Constant.PRIVATE_P2P: self.private_p2p,
            Constant.TASK_NAME_PREFIX: self.task_name_prefix,
            Constant.CLIENTS: self.participating_clients,
            Constant.START_CLIENT: self.starting_client,
            Constant.RESULT_CLIENTS: self.result_clients,
            AppConstants.NUM_ROUNDS: self.num_rounds,
            Constant.START_ROUND: self.start_round,
            FLContextKey.WORKFLOW: self.workflow_id,
        }

        extra_config = self.prepare_config()
        if extra_config:
            learn_config.update(extra_config)

        self.logger.info(f"Workflow Config: {learn_config}")

        data_model = FLModel(params={Constant.CONFIG: learn_config})
        self.prepare_broadcast_and_wait(task_name=self.configure_task_name,
                                        model=data_model,
                                        targets=self.participating_clients,
                                        callback=self._process_configure_reply)
        
        print(f"\n\t\t after prepare_broadcast_and_wait!!!")

        # # configure all clients
        # shareable = Shareable()
        # shareable[Constant.CONFIG] = learn_config

        # task = Task(
        #     name=self.configure_task_name,
        #     data=shareable,
        #     timeout=self.configure_task_timeout,
        #     result_received_cb=self._process_configure_reply,
        # )

        # self.logger.info(f"sending task {self.configure_task_name} to clients {self.participating_clients}")
        # start_time = time.time()
        # self.broadcast_and_wait(
        #     task=task,
        #     targets=self.participating_clients,
        #     min_responses=len(self.participating_clients),
        #     fl_ctx=fl_ctx,
        #     abort_signal=abort_signal,
        # )

        # time_taken = time.time() - start_time
        # self.logger.info(f"client configuration took {time_taken} seconds")

        failed_clients = []
        for c, cs in self.client_statuses.items():
            assert isinstance(cs, ClientStatus)
            if not cs.ready_time:
                failed_clients.append(c)

        if failed_clients:
            # self.system_panic(
            #     f"failed to configure clients {failed_clients}",
            #     fl_ctx,
            # )
            raise RuntimeError(f"failed to configure clients {failed_clients}")
            return

        self.logger.info(f"successfully configured clients {self.participating_clients}")

        # starting the starting_client
        if self.starting_client:

            self.logger.info(f"sending task {self.start_task_name} to client {self.starting_client}")

            data_model = FLModel(params={})
            targets = [self.starting_client]
            self.send_and_wait(task_name=self.start_task_name,
                               min_responses=1,
                               data=data_model,
                               targets=targets,
                               callback=self._process_start_reply)

            # shareable = Shareable()
            # task = Task(
            #     name=self.start_task_name,
            #     data=shareable,
            #     timeout=self.start_task_timeout,
            #     result_received_cb=self._process_start_reply,
            # )

            # self.send_and_wait(
            #     task=task,
            #     targets=[self.starting_client],
            #     fl_ctx=fl_ctx,
            #     abort_signal=abort_signal,
            # )

            if not self.cw_started:
                # self.system_panic(
                #     f"failed to start workflow {self.workflow_id} on client {self.starting_client}",
                #     fl_ctx,
                # )
                return

            self.logger.info(f"started workflow {self.workflow_id} on client {self.starting_client}")

        #####################

        # a subclass could provide additional control flow
        self.sub_flow(abort_signal)

        # self.logger.info(f"Waiting for clients to finish workflow {self.workflow_id}  ...")
        # while not self.asked_to_stop:#not abort_signal.triggered and not self.asked_to_stop:
        #     time.sleep(self.job_status_check_interval)
        #     done = self._check_job_status()
        #     if done:
        #         break

        self.logger.info(f"Workflow {self.workflow_id} finished on all clients")

        # ask all clients to end the workflow
        self.logger.info(f"asking all clients to end workflow {self.workflow_id}")

        self.logger.info(f"Workflow {self.workflow_id} done!")


    def prepare_broadcast_and_wait(self, task_name, model: FLModel, targets, callback=None):
        # (2) broadcast and wait
        #model.current_round = self.current_round
        results = self.broadcast_and_wait(
            task_name=task_name, min_responses=self.min_clients, data=model, targets=targets, callback=callback
        )
        if callback is None:
            return results
        else:
            return None
        
    #######

    def process_config_reply(self, client_name: str, reply: FLModel) -> bool:
        return True

    #move this to the communicator???
    def _process_configure_reply(self, client_task: ClientTask, fl_ctx: FLContext = None):
        result = client_task.result
        client_name = client_task.client.name

        print(f"\n\t\t PROCESS CONFIURE REPLY {client_task=}")

        rc = result.get_return_code()
        if rc == ReturnCode.OK:
            self.logger.info(f"successfully configured client {client_name}")

            try:
                ok = self.process_config_reply(client_name, result)
                if not ok:
                    return
            except:
                self.logger.error(
                    f"exception processing config reply from client {client_name}: {secure_format_traceback()}"
                )
                return
            cs = self.client_statuses.get(client_name)
            if cs:
                assert isinstance(cs, ClientStatus)
                cs.ready_time = time.time()
        else:
            error = result.get(Constant.ERROR, "?")
            self.logger.error(f"client {client_task.client.name} failed to configure: {rc}: {error}")

    def client_started(self, client_task: ClientTask):
        return True

    def _process_start_reply(self, client_task: ClientTask, fl_ctx: FLContext = None):
        result = client_task.result
        client_name = client_task.client.name

        rc = result.get_return_code()
        if rc == ReturnCode.OK:
            try:
                ok = self.client_started(client_task)
                if not ok:
                    return
            except:
                self.logger.info(f"exception in client_started: {secure_format_traceback()}")
                return

            self.cw_started = True
        else:
            error = result.get(Constant.ERROR, "?")
            self.logger.error(f"client {client_task.client.name} couldn't start workflow {self.workflow_id}: {rc}: {error}")

    def is_sub_flow_done(self) -> bool:
        return False
