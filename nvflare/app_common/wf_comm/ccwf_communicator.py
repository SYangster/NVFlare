# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
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

from nvflare.apis.fl_context import FLContext
from nvflare.apis.signal import Signal
from nvflare.app_common.ccwf.server_ctl import ServerSideController
from nvflare.app_common.wf_comm.base_wf_communicator import BaseWFCommunicator

import time


class CCWFCommunicator(BaseWFCommunicator, ServerSideController):
    def __init__(self, max_status_report_interval: float):
        BaseWFCommunicator.__init__(self)
        ServerSideController.__init__(self, max_status_report_interval=max_status_report_interval)
        self.register_serializers()

    def control_flow(self, abort_signal: Signal, fl_ctx: FLContext):
        self.start_workflow(abort_signal, fl_ctx)

        self.logger.info(f"Waiting for clients to finish workflow {self.workflow_id}  ...")
        while not abort_signal.triggered and not self.asked_to_stop:
            time.sleep(self.job_status_check_interval)
            done = self._check_job_status(fl_ctx)
            if done:
                break
        
        self.logger.info(f"Workflow {self.workflow_id} finished on all clients")

        # ask all clients to end the workflow
        self.logger.info(f"asking all clients to end workflow {self.workflow_id}")

        self.logger.info(f"Workflow {self.workflow_id} done!")


