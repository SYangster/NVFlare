# Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
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
from abc import ABC
from threading import Lock
from typing import List, Optional, Tuple, Union

from nvflare.apis.client import Client
from nvflare.apis.controller_spec import ClientTask, ControllerSpec, SendOrder, Task, TaskCompletionStatus
from nvflare.apis.fl_context import FLContext
from nvflare.apis.responder import Responder
from nvflare.apis.shareable import Shareable
from nvflare.apis.signal import Signal
from nvflare.widgets.info_collector import GroupInfoCollector, InfoCollector


from .wf_comm_server import WFCommServer
from .wf_comm_spec import WFCommSpec


class Controller(Responder, ControllerSpec, ABC):
    def __init__(self, task_check_period=0.2):
        """Manage life cycles of tasks and their destinations.

        Args:
            task_check_period (float, optional): interval for checking status of tasks. Defaults to 0.2.
        """
        super().__init__()
        self._engine = None
        self._tasks = []  # list of standing tasks
        self._client_task_map = {}  # client_task_id => client_task
        self._all_done = False
        self._task_lock = Lock()
        #self._task_monitor = threading.Thread(target=self._monitor_tasks, args=())
        self._task_check_period = task_check_period
        self._dead_client_reports = {}  # clients that reported the job is dead on it: name => report time
        self._dead_clients_lock = Lock()  # need lock since dead_clients can be modified from different threads
        # make sure _check_tasks, process_task_request, process_submission does not interfere with each other
        self._controller_lock = Lock()

        self.communicator = WFCommServer() #None

    def communicator_fn(func): 
        def wrapper(*args, **kwargs): 
            ctrl =  args[0]
            task = getattr(ctrl.communicator, func.__name__)(*args[1:], **kwargs)
            with ctrl._task_lock:
                ctrl._tasks.append(task)
                #ctrl.log_info(**kwargs["fl_ctx"], "scheduled task {}".format(task.name))
        return wrapper
    
    def set_communicator(self, communicator: WFCommSpec):
        self.communicator = communicator

    def initialize_run(self, fl_ctx: FLContext):
        """Called by runners to initialize controller with information in fl_ctx.

        .. attention::

            Controller subclasses must not overwrite this method.

        Args:
            fl_ctx (FLContext): FLContext information
        """
        self.communicator.initialize_run(fl_ctx)
        engine = fl_ctx.get_engine()
        if not engine:
            self.system_panic(f"Engine not found. {self.__class__.__name__} exiting.", fl_ctx)
            return

        self._engine = engine
        self.start_controller(fl_ctx)
        #self._task_monitor.start()

    def handle_event(self, event_type: str, fl_ctx: FLContext):
        """Called when events are fired.

        Args:
            event_type (str): all event types, including AppEventType and EventType
            fl_ctx (FLContext): FLContext information with current event type
        """
        # if event_type == InfoCollector.EVENT_TYPE_GET_STATS:
        #     self._set_stats(fl_ctx)
        self.communicator.handle_event(event_type, fl_ctx)

    def process_task_request(self, client: Client, fl_ctx: FLContext) -> Tuple[str, str, Shareable]:
        """Called by runner when a client asks for a task.

        .. note::

            This is called in a separate thread.

        Args:
            client (Client): The record of one client requesting tasks
            fl_ctx (FLContext): The FLContext associated with this request

        Raises:
            TypeError: when client is not an instance of Client
            TypeError: when fl_ctx is not an instance of FLContext
            TypeError: when any standing task containing an invalid client_task

        Returns:
            Tuple[str, str, Shareable]: task_name, an id for the client_task, and the data for this request
        """
        return self.communicator.process_task_request(client, fl_ctx) #should we make communicator a responder too then?, how to generalize the responder code between server and client?
        # with self._controller_lock:
        #     return self._do_process_task_request(client, fl_ctx)

    def handle_exception(self, task_id: str, fl_ctx: FLContext) -> None:
        """Called to cancel one task as its client_task is causing exception at upper level.

        Args:
            task_id (str): an id to the failing client_task
            fl_ctx (FLContext): FLContext associated with this client_task
        """
        # with self._task_lock:
        #     # task_id is the uuid associated with the client_task
        #     client_task = self._client_task_map.get(task_id, None)
        #     self.logger.debug("Handle exception on client_task {} with id {}".format(client_task, task_id))

        # if client_task is None:
        #     # cannot find a standing task on the exception
        #     return

        # task = client_task.task
        # self.cancel_task(task=task, fl_ctx=fl_ctx)
        # self.log_error(fl_ctx, "task {} is cancelled due to exception".format(task.name))
        self.communicator.handle_exception(task_id, fl_ctx)

    def handle_dead_job(self, client_name: str, fl_ctx: FLContext):
        """Called by the Engine to handle the case that the job on the client is dead.

        Args:
            client_name: name of the client on which the job is dead
            fl_ctx: the FLContext

        """
        # record the report and to be used by the task monitor
        # with self._dead_clients_lock:
        #     self.log_info(fl_ctx, f"received dead job report from client {client_name}")
        #     if not self._dead_client_reports.get(client_name):
        #         self._dead_client_reports[client_name] = time.time()
        self.communicator.handle_dead_job(client_name, fl_ctx)

    def process_task_check(self, task_id: str, fl_ctx: FLContext):
        return self.communicator.process_task_check(task_id, fl_ctx)
        # with self._task_lock:
        #     # task_id is the uuid associated with the client_task
        #     return self._client_task_map.get(task_id, None)

    def process_submission(self, client: Client, task_name: str, task_id: str, result: Shareable, fl_ctx: FLContext):
        """Called to process a submission from one client.

        .. note::

            This method is called by a separate thread.

        Args:
            client (Client): the client that submitted this task
            task_name (str): the task name associated this submission
            task_id (str): the id associated with the client_task
            result (Shareable): the actual submitted data from the client
            fl_ctx (FLContext): the FLContext associated with this submission

        Raises:
            TypeError: when client is not an instance of Client
            TypeError: when fl_ctx is not an instance of FLContext
            TypeError: when result is not an instance of Shareable
            ValueError: task_name is not found in the client_task
        """
        self.communicator.process_submission(client, task_name, task_id, result, fl_ctx)
        # with self._controller_lock:
        #     self._do_process_submission(client, task_name, task_id, result, fl_ctx)

    #@communicator_fn
    def broadcast(
        self,
        task: Task,
        fl_ctx: FLContext,
        targets: Union[List[Client], List[str], None] = None,
        min_responses: int = 1,
        wait_time_after_min_received: int = 0,
    ):
        self.communicator.broadcast(task, fl_ctx, targets, min_responses, wait_time_after_min_received)

    def broadcast_and_wait(
        self,
        task: Task,
        fl_ctx: FLContext,
        targets: Union[List[Client], List[str], None] = None,
        min_responses: int = 1,
        wait_time_after_min_received: int = 0,
        abort_signal: Optional[Signal] = None,
    ):
        self.communicator.broadcast_and_wait(task, fl_ctx, targets, min_responses, wait_time_after_min_received, abort_signal)

    def broadcast_forever(self, task: Task, fl_ctx: FLContext, targets: Union[List[Client], List[str], None] = None):
        self.communicator.broadcast_forever(task, fl_ctx, targets)

    def send(
        self,
        task: Task,
        fl_ctx: FLContext,
        targets: Union[List[Client], List[str], None] = None,
        send_order: SendOrder = SendOrder.SEQUENTIAL,
        task_assignment_timeout: int = 0,
    ):
        self.communicator.send(task, fl_ctx, targets, send_order, task_assignment_timeout)

    def send_and_wait(
        self,
        task: Task,
        fl_ctx: FLContext,
        targets: Union[List[Client], List[str], None] = None,
        send_order: SendOrder = SendOrder.SEQUENTIAL,
        task_assignment_timeout: int = 0,
        abort_signal: Signal = None,
    ):
        self.communicator.send_and_wait(task, fl_ctx, targets, send_order, task_assignment_timeout, abort_signal)

    def relay(
        self,
        task: Task,
        fl_ctx: FLContext,
        targets: Union[List[Client], List[str], None] = None,
        send_order: SendOrder = SendOrder.SEQUENTIAL,
        task_assignment_timeout: int = 0,
        task_result_timeout: int = 0,
        dynamic_targets: bool = True,
    ):
        self.communicator.relay(task, fl_ctx, targets, send_order, task_assignment_timeout, task_result_timeout, dynamic_targets)

    def relay_and_wait(
        self,
        task: Task,
        fl_ctx: FLContext,
        targets: Union[List[Client], List[str], None] = None,
        send_order=SendOrder.SEQUENTIAL,
        task_assignment_timeout: int = 0,
        task_result_timeout: int = 0,
        dynamic_targets: bool = True,
        abort_signal: Optional[Signal] = None,
    ):
        self.communicator.relay_and_wait(task, fl_ctx, targets, send_order, task_assignment_timeout, task_result_timeout, dynamic_targets, abort_signal)

    def get_num_standing_tasks(self) -> int:
        """Get the number of tasks that are currently standing.

        Returns:
            int: length of the list of standing tasks
        """
        return len(self._tasks)

    def cancel_task(
        self, task: Task, completion_status=TaskCompletionStatus.CANCELLED, fl_ctx: Optional[FLContext] = None
    ):
        """Cancel the specified task.

        Change the task completion_status, which will inform task monitor to clean up this task

        note::

            We only mark the task as completed and leave it to the task monitor to clean up. This is to avoid potential deadlock of task_lock.

        Args:
            task (Task): the task to be cancelled
            completion_status (str, optional): the completion status for this cancellation. Defaults to TaskCompletionStatus.CANCELLED.
            fl_ctx (Optional[FLContext], optional): FLContext associated with this cancellation. Defaults to None.
        """
        self.communicator.cancel_task(task, completion_status, fl_ctx)

    def cancel_all_tasks(self, completion_status=TaskCompletionStatus.CANCELLED, fl_ctx: Optional[FLContext] = None):
        """Cancel all standing tasks in this controller.

        Args:
            completion_status (str, optional): the completion status for this cancellation. Defaults to TaskCompletionStatus.CANCELLED.
            fl_ctx (Optional[FLContext], optional): FLContext associated with this cancellation. Defaults to None.
        """
        self.communicator.cancel_all_tasks(fl_ctx)

    def finalize_run(self, fl_ctx: FLContext):
        """Do cleanup of the coordinator implementation.

        .. attention::

            Subclass controllers should not overwrite finalize_run.

        Args:
            fl_ctx (FLContext): FLContext associated with this action
        """
        self.communicator.finalize_run(fl_ctx)
        self.stop_controller(fl_ctx)


