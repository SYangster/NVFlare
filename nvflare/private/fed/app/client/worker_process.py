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

"""Provides a command line interface for a federated client trainer."""

import argparse
import os
import sys
import threading

from nvflare.apis.fl_constant import ConfigVarName, FLContextKey, JobConstants, SiteType, SystemConfigs
from nvflare.apis.overseer_spec import SP
from nvflare.apis.workspace import Workspace
from nvflare.fuel.f3.mpm import MainProcessMonitor as mpm
from nvflare.fuel.utils.argument_utils import parse_vars
from nvflare.fuel.utils.config_service import ConfigService
from nvflare.fuel.utils.log_utils import configure_logging, get_script_logger
from nvflare.private.fed.app.fl_conf import FLClientStarterConfiger
from nvflare.private.fed.app.utils import monitor_parent_process
from nvflare.private.fed.client.client_app_runner import ClientAppRunner
from nvflare.private.fed.client.client_status import ClientStatus
from nvflare.private.fed.utils.fed_utils import (
    create_stats_pool_files_for_job,
    fobs_initialize,
    register_ext_decomposers,
    security_close,
    security_init_for_job,
    set_stats_pool_config_for_job,
)
from nvflare.security.logging import secure_format_exception


def main(args):
    kv_list = parse_vars(args.set)

    # get parent process id
    parent_pid = os.getppid()

    args.train_config = os.path.join("config", "config_train.json")
    config_folder = kv_list.get("config_folder", "")
    secure_train = kv_list.get("secure_train", True)
    if config_folder == "":
        args.client_config = JobConstants.CLIENT_JOB_CONFIG
    else:
        args.client_config = os.path.join(config_folder, JobConstants.CLIENT_JOB_CONFIG)
    args.config_folder = config_folder
    args.env = os.path.join("config", "environment.json")
    workspace = Workspace(args.workspace, args.client_name, config_folder)
    set_stats_pool_config_for_job(workspace, args.job_id)

    try:
        remove_restart_file(workspace)
    except Exception:
        print("Could not remove the restart.fl / shutdown.fl file.  Please check your system before starting FL.")
        sys.exit(-1)

    restart_file = workspace.get_file_path_in_root("restart.fl")
    if os.path.exists(restart_file):
        os.remove(restart_file)

    fobs_initialize(workspace=workspace, job_id=args.job_id)

    # initialize security processing and ensure that content in the startup has not been tampered with.
    security_init_for_job(secure_train, workspace, SiteType.CLIENT, args.job_id)

    thread = None
    stop_event = threading.Event()
    deployer = None
    client_app_runner = None
    federated_client = None

    app_root = workspace.get_app_dir(str(args.job_id))

    logger = None
    try:
        conf = FLClientStarterConfiger(
            workspace=workspace,
            args=args,
            kv_list=args.set,
        )
        conf.configure()

        decomposer_module = ConfigService.get_str_var(
            name=ConfigVarName.DECOMPOSER_MODULE, conf=SystemConfigs.RESOURCES_CONF
        )
        register_ext_decomposers(decomposer_module)

        configure_logging(workspace, args.job_id)
        logger = get_script_logger()
        logger.info("Worker_process started.")

        deployer = conf.base_deployer
        # federated_client = deployer.create_fed_client(args, args.sp_target)
        federated_client = deployer.create_fed_client(args)
        federated_client.status = ClientStatus.STARTING

        federated_client.communicator.set_auth(args.client_name, args.token, args.token_signature, args.ssid)
        federated_client.token = args.token
        federated_client.token_signature = args.token_signature
        federated_client.ssid = args.ssid
        federated_client.client_name = args.client_name
        federated_client.fl_ctx.set_prop(FLContextKey.CLIENT_NAME, args.client_name, private=False)
        federated_client.fl_ctx.set_prop(FLContextKey.WORKSPACE_ROOT, args.workspace, private=True)

        client_app_runner = ClientAppRunner(time_out=kv_list.get("app_runner_timeout", 60.0))
        # start parent process checking thread
        thread = threading.Thread(target=monitor_parent_process, args=(client_app_runner, parent_pid, stop_event))
        thread.start()

        sp = _create_sp(args)
        client_app_runner.start_run(app_root, args, config_folder, federated_client, secure_train, sp, conf.handlers)
    except Exception as e:
        if logger:
            logger.error(f"FL client execution exception: {secure_format_exception(e)}")
        raise e
    finally:
        if client_app_runner:
            client_app_runner.close()
        if deployer:
            deployer.close()
        if federated_client:
            federated_client.terminate()
        stop_event.set()
        if thread and thread.is_alive():
            thread.join()
        security_close()
        err = create_stats_pool_files_for_job(workspace, args.job_id)
        if err:
            logger.warning(err)


def parse_arguments():
    """Worker process start program."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", "-m", type=str, help="WORKSPACE folder", required=True)
    parser.add_argument("--startup", "-w", type=str, help="startup folder", required=True)
    parser.add_argument("--token", "-t", type=str, help="auth token", required=True)
    parser.add_argument("--token_signature", "-ts", type=str, help="auth token signature", required=True)
    parser.add_argument("--ssid", "-d", type=str, help="ssid", required=True)
    parser.add_argument("--job_id", "-n", type=str, help="job_id", required=True)
    parser.add_argument("--client_name", "-c", type=str, help="client name", required=True)
    # parser.add_argument("--listen_port", "-p", type=str, help="listen port", required=True)
    parser.add_argument("--sp_target", "-g", type=str, help="Sp target", required=True)
    parser.add_argument("--sp_scheme", "-scheme", type=str, help="Sp connection scheme", required=True)
    parser.add_argument("--parent_url", "-p", type=str, help="parent_url", required=True)
    parser.add_argument(
        "--parent_conn_sec",
        "-pcs",
        type=str,
        help="parent conn security",
        required=False,
        default="",
    )
    parser.add_argument(
        "--fed_client", "-s", type=str, help="an aggregation server specification json file", required=True
    )
    parser.add_argument("--set", metavar="KEY=VALUE", nargs="*")
    parser.add_argument("--local_rank", type=int, default=0)
    args = parser.parse_args()
    return args


def _create_sp(args):
    sp = SP()
    target = args.sp_target.split(":")
    sp.name = target[0]
    sp.fl_port = target[1]
    sp.service_session_id = args.ssid
    sp.primary = True
    return sp


def remove_restart_file(workspace: Workspace):
    """To remove the restart.fl file.

    Args:
        workspace: workspace object

    """
    restart_file = workspace.get_file_path_in_root("restart.fl")
    if os.path.exists(restart_file):
        os.remove(restart_file)
    restart_file = workspace.get_file_path_in_root("shutdown.fl")
    if os.path.exists(restart_file):
        os.remove(restart_file)


if __name__ == "__main__":
    """
    This is the program when starting the child process for running the NVIDIA FLARE executor.
    """

    # main()
    args = parse_arguments()
    run_dir = os.path.join(args.workspace, args.job_id)
    rc = mpm.run(main_func=main, run_dir=run_dir, args=args)
    sys.exit(rc)
