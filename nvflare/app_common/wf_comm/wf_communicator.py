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

from nvflare.apis.fl_context import FLContext
from nvflare.apis.impl.controller import Controller
from nvflare.apis.signal import Signal
from nvflare.app_common.wf_comm.base_wf_communicator import BaseWFCommunicator
from nvflare.apis.fl_constant import FLContextKey

from abc import ABC
from typing import Dict, List, Optional, Tuple

from nvflare.apis.client import Client
from nvflare.apis.controller_spec import ClientTask, ControllerSpec, OperatorMethod, SendOrder, Task, TaskOperatorKey
from nvflare.apis.shareable import ReturnCode, Shareable

from nvflare.apis.fl_context import FLContext

from nvflare.app_common.app_constant import AppConstants

from nvflare.app_common.wf_comm.wf_comm_api_spec import (
    DATA,
    MIN_RESPONSES,
    RESULT,
    SITE_NAMES,
    STATUS,
    TARGET_SITES,
    TASK_NAME,
)


import time
from datetime import datetime


from nvflare.apis.client import Client
from nvflare.apis.fl_context import FLContext
from nvflare.apis.impl.controller import ClientTask, Controller, Task
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

import logging

class ClientStatus:
    def __init__(self):
        self.ready_time = None
        self.last_report_time = time.time()
        self.last_progress_time = time.time()
        self.num_reports = 0
        self.status = StatusReport()


class WFCommunicator(BaseWFCommunicator, Controller):
    def __init__(
        self,
        num_rounds: int = 3,
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
        super().__init__()
        self.register_serializers()

        Controller.__init__(self, task_check_period)
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
        self.max_status_report_interval = 300#max_status_report_interval #need to configure this!!!
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

    def start_controller(self, fl_ctx):
        super().start_controller(fl_ctx)
        wf_id = fl_ctx.get_prop(FLContextKey.WORKFLOW)
        self.log_debug(fl_ctx, f"starting controller for workflow {wf_id}")
        if not wf_id:
            raise RuntimeError("workflow ID is missing from FL context")
        self.workflow_id = wf_id
        #self.workflow_id = 'WFCommunicator' #"cyclic_ccwf"

        all_clients = self._engine.get_clients()
        if len(all_clients) < 2:
            raise RuntimeError(f"this workflow requires at least 2 clients, but only got {all_clients}")

        #all_client_names = self.get_site_names()
        #print(f"\t{all_client_names=}")
        all_client_names = [t.name for t in all_clients]
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

    def control_flow(self, abort_signal: Signal, fl_ctx: FLContext):
        self.start_workflow(abort_signal, fl_ctx)

        self.logger.info(f"Waiting for clients to finish workflow {self.workflow_id}  ...")
        while not self.asked_to_stop:#not abort_signal.triggered and not self.asked_to_stop:
            time.sleep(self.job_status_check_interval)
            done = self._check_job_status(fl_ctx)
            if done:
                break
        
        engine = fl_ctx.get_engine()
        end_wf_request = Shareable()
        resp = engine.send_aux_request(
            targets=self.participating_clients,
            topic=topic_for_end_workflow(self.workflow_id),
            request=end_wf_request,
            timeout=self.end_workflow_timeout,
            fl_ctx=fl_ctx,
            secure=False,
        )

        assert isinstance(resp, dict)
        num_errors = 0
        for c in self.participating_clients:
            reply = resp.get(c)
            if not reply:
                self.logger.error(f"not reply from client {c} for ending workflow {self.workflow_id}")
                num_errors += 1
                continue

            assert isinstance(reply, Shareable)
            rc = reply.get_return_code(ReturnCode.OK)
            if rc != ReturnCode.OK:
                self.logger.error(f"client {c} failed to end workflow {self.workflow_id}: {rc}")
                num_errors += 1

        if num_errors > 0:
            #self.system_panic(f"failed to end workflow {self.workflow_id} on all clients", fl_ctx)
            raise RuntimeError(f"failed to end workflow {self.workflow_id} on all clients")
        
        self.logger.info(f"Workflow {self.workflow_id} done!")

    def process_task_request(self, client: Client, fl_ctx: FLContext):
        self._update_client_status(fl_ctx)
        return super().process_task_request(client, fl_ctx)
    
    def get_payload_task(self, pay_load) -> Tuple[Task, int, List[str]]:
        min_responses = pay_load.get(MIN_RESPONSES)
        current_round = pay_load.get(AppConstants.CURRENT_ROUND, 0)
        start_round = pay_load.get(AppConstants.START_ROUND, 0)
        num_rounds = pay_load.get(AppConstants.NUM_ROUNDS, 1)
        targets = pay_load.get(TARGET_SITES, self.get_site_names())
        task_name = pay_load.get(TASK_NAME)

        data = pay_load.get(DATA, {})
        data_shareable = self.get_shareable(data)
        data_shareable.set_header(AppConstants.START_ROUND, start_round)
        data_shareable.set_header(AppConstants.CURRENT_ROUND, current_round)
        data_shareable.set_header(AppConstants.NUM_ROUNDS, num_rounds)
        data_shareable.add_cookie(AppConstants.CONTRIBUTION_ROUND, current_round)

        operator = {
            TaskOperatorKey.OP_ID: task_name,
            TaskOperatorKey.METHOD: OperatorMethod.BROADCAST,
            TaskOperatorKey.TIMEOUT: self.task_timeout,
        }

        task = Task(
            name=task_name,
            data=data_shareable,
            operator=operator,
            props={},
            timeout=self.task_timeout,
            before_task_sent_cb=None,
            result_received_cb=pay_load.get("task_callback")#self._result_received_cb,
        )

        return task, min_responses, targets
    
    def _update_client_status(self, fl_ctx: FLContext):
        peer_ctx = fl_ctx.get_peer_context()
        assert isinstance(peer_ctx, FLContext)
        client_name = peer_ctx.get_identity_name()
        if client_name not in self.client_statuses:
            self.logger.error(f"received result from unknown client {client_name}!")
            return

        # see whether status is available
        reports = peer_ctx.get_prop(Constant.STATUS_REPORTS)
        if not reports:
            self.logger.info(f"no status report from client {client_name}")
            return

        my_report = reports.get(self.workflow_id)
        if not my_report:
            return

        report = status_report_from_dict(my_report)
        cs = self.client_statuses[client_name]
        assert isinstance(cs, ClientStatus)
        now = time.time()
        cs.last_report_time = now
        cs.num_reports += 1

        if report.error:
            self.asked_to_stop = True
            self.system_panic(f"received failure report from client {client_name}: {report.error}", fl_ctx)
            return

        if cs.status != report:
            # updated
            cs.status = report
            cs.last_progress_time = now
            timestamp = datetime.fromtimestamp(report.timestamp) if report.timestamp else False
            self.logger.info(
                f"updated status of client {client_name} on round {report.last_round}: "
                f"timestamp={timestamp}, action={report.action}, all_done={report.all_done}",
            )
        else:
            self.logger.debug(
                f"ignored status report from client {client_name} at round {report.last_round}: no change"
            )
    
    def is_sub_flow_done(self) -> bool:
        return False
    
    def _check_job_status(self, fl_ctx):
        # see whether the server side thinks it's done
        if self.is_sub_flow_done():
            return True

        now = time.time()
        overall_last_progress_time = 0.0
        for client_name, cs in self.client_statuses.items():
            assert isinstance(cs, ClientStatus)
            assert isinstance(cs.status, StatusReport)

            if cs.status.all_done:
                self.logger.info(f"Got ALL_DONE from client {client_name}")
                return True

            if now - cs.last_report_time > self.max_status_report_interval:
                #raise RuntimeError(f"client {client_name} didn't report status for {self.max_status_report_interval} seconds")
                self.system_panic(
                    f"client {client_name} didn't report status for {self.max_status_report_interval} seconds",
                    fl_ctx,
                )

                return True

            if overall_last_progress_time < cs.last_progress_time:
                overall_last_progress_time = cs.last_progress_time

        if time.time() - overall_last_progress_time > self.progress_timeout:
            #raise RuntimeError(f"the workflow {self.workflow_id} has no progress for {self.progress_timeout} seconds")
            self.system_panic(
                f"the workflow {self.workflow_id} has no progress for {self.progress_timeout} seconds",
                fl_ctx,
            )
            return True

        return False
    

