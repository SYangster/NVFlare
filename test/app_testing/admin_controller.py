# Copyright (c) 2021-2022, NVIDIA CORPORATION.  All rights reserved.
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

import logging
import re
import time

from nvflare.ha.overseer_agent import HttpOverseerAgent
from nvflare.fuel.hci.client.api_status import APIStatus
from nvflare.fuel.hci.client.fl_admin_api import FLAdminAPI
from nvflare.fuel.hci.client.fl_admin_api_constants import FLDetailKey
from nvflare.fuel.hci.client.fl_admin_api_spec import TargetType


class AdminController(object):
    def __init__(self, app_path, poll_period=10):
        """
        This class runs an app on a given server and clients.
        """
        super().__init__()

        self.app_path = app_path
        self.poll_period = poll_period
        self.last_app_name = ""

        overseer_agent = HttpOverseerAgent(role="admin", overseer_end_point="http://localhost:6000/api/v1", project="example_project", name="admin")

        self.admin_api: FLAdminAPI = FLAdminAPI(
            host="localhost",
            port=8003,
            upload_dir=self.app_path,
            download_dir=self.app_path,
            overseer_agent=overseer_agent, #TODO add password and username here?
            auto_login=True,
            poc=True,
            debug=False,
        )
        self.run_number = 0

        self.logger = logging.getLogger("AdminController")

    def initialize(self):
        success = False

        try:
            response = None
            timeout = 100
            start_time = time.time()
            while time.time() - start_time <= timeout:
                response = self.admin_api.login_with_password(username="admin", password="admin")
                if response["status"] == APIStatus.SUCCESS:
                    success = True
                    break
                time.sleep(1.0)
            if not success:
                details = response.get("details") if response else "No details"
                raise ValueError(f"Login to admin api failed: {details}")
            else:
                print("Admin successfully logged into server.")
        except Exception as e:
            print(f"Exception in logging in to admin: {e.__str__()}")

        return success

    def get_run_data(self):
        run_data = {"run_number": self.run_number, "app_path": self.app_path, "app_name": self.last_app_name}

        return run_data

    def get_stats(self, target):
        return self.admin_api.show_stats(target)

    def ensure_clients_started(self, num_clients):
        if not self.admin_api:
            return False

        timeout = 1000
        start_time = time.time()
        clients_up = False
        while not clients_up:
            if time.time() - start_time > timeout:
                raise ValueError(f"Clients could not be started in {timeout} seconds.")

            response = self.admin_api.check_status(target_type=TargetType.CLIENT)
            if response["status"] == APIStatus.SUCCESS:
                # print(f"check client status response {response}")
                if "details" not in response:  # clients not ready....
                    # client response would be: {'status': <APIStatus.SUCCESS: 'SUCCESS'>, 'raw': {'time': '2021-10-29 00:09:06.220615', 'data': [{'type': 'error', 'data': 'no clients available'}], 'status': <APIStatus.SUCCESS: 'SUCCESS'>}}
                    # How can the user know if clients are ready or not.....
                    continue
                for row in response["details"]["client_statuses"][1:]:
                    if row[3] != "not started":
                        continue
                # wait for all clients to come up
                if len(response["details"]["client_statuses"]) < num_clients + 1:
                    continue
                clients_up = True
                print("All clients are up.")
            time.sleep(1.0)

        return clients_up

    def server_status(self):
        if not self.admin_api:
            return ""

        response = self.admin_api.check_status(target_type=TargetType.SERVER)
        if response["status"] == APIStatus.SUCCESS:
            if "details" in response:
                return response["details"]
        return ""

    def client_status(self):
        if not self.admin_api:
            return ""

        response = self.admin_api.check_status(target_type=TargetType.CLIENT)
        if response["status"] == APIStatus.SUCCESS:
            if "details" in response:
                return response["details"]
        return ""

    def deploy_app(self, app_name) -> bool:
        if not self.admin_api:
            return False

        self.run_number += 1

        response = self.admin_api.set_run_number(self.run_number)
        if response["status"] != APIStatus.SUCCESS:
            raise RuntimeError(f"set run number failed: {response}")
        response = self.admin_api.upload_app(app_name)
        if response["status"] != APIStatus.SUCCESS:
            raise RuntimeError(f"upload_app failed: {response}")
        response = self.admin_api.deploy_app(app=app_name, target_type=TargetType.ALL)
        if response["status"] != APIStatus.SUCCESS:
            raise RuntimeError(f"deploy_app failed: {response}")
        response = self.admin_api.start_app(target_type=TargetType.ALL)
        if response["status"] != APIStatus.SUCCESS:
            raise RuntimeError(f"start_app failed: {response}")

        self.last_app_name = app_name

        return True

    def run_app(self):
        # TODO:: Is it possible to get the training log after training is done?
        training_done = False
        while not training_done:
            response = self.admin_api.check_status(target_type=TargetType.SERVER)
            if response["status"] != APIStatus.SUCCESS:
                raise RuntimeError(f"check_status failed: {response}")
            if response["details"][FLDetailKey.SERVER_ENGINE_STATUS] == "stopped":
                response = self.admin_api.check_status(target_type=TargetType.CLIENT)
                if response["status"] != APIStatus.SUCCESS:
                    raise RuntimeError(f"check_status failed: {response}")
                for row in response["details"]["client_statuses"]:
                    if row[3] != "stopped":
                        continue
                training_done = True
            time.sleep(self.poll_period)

    def run_app_ha(self, site_launcher, ha_test_args):
        round_number = 0
        workflow = None

        last_read_line = 0

        test_complete = False
        killed = False

        training_done = False
        while not training_done:
            server_logs = self.admin_api.cat_target(TargetType.SERVER, file="log.txt")["details"]["message"].splitlines()[last_read_line:]
            last_read_line = len(server_logs) + last_read_line
            server_logs_string = "\n".join(server_logs)

            #stats = self.admin_api.show_stats(TargetType.SERVER) 
            stats = self.get_stats(TargetType.SERVER)
            print("\nSTATS", stats)
            # stats2 = self.get_stats(TargetType.CLIENT)
            # print("STATTS2", stats2)
            round_number, workflow, wfs = self.process_stats(stats, round_number, workflow)
            wfs = list(wfs.items())
            wfs.append((None, None))
            print(wfs, type(wfs))

            #TODO [('ScatterAndGather', {'tasks': {}, 'phase': '_finished_', 'current_round': 2, 'num_rounds': 2}), ('CrossSiteModelEval', {'tasks': {}}), (None, None)] <class 'list'>
            #when run is finished

            # round_number, workflow = self.process_logs(server_logs_string, round_number, workflow)
            print(f"ROUND NUMBER: {round_number}")
            print(f"WORKFLOW: {workflow}") #TODO limit printing to be more sparse, until state changes
            
            # if not killed:
            #     event_trigger = [] # need way to see if test doesn't trigger event properly, then means test did not test correctly
            #     for k, v in ha_test_args["event"].items():
            #         if k == "round":
            #             event_trigger.append(round_number == v)
            #         elif k == "workflow":
            #             event_trigger.append(workflow == list(wfs.items())[v][0])

            #if not killed and ha_test_args["event"] in server_logs_string:
            if not killed:
                event_trigger = [] # need way to see if test doesn't trigger event properly, then means test did not test correctly
                for k, v in ha_test_args["event"].items():
                    if k == "round":
                        event_trigger.append(round_number == v)
                    elif k == "workflow":
                        #event_trigger.append(workflow == list(wfs.items())[v][0])
                        event_trigger.append(workflow == wfs[v][0])

                if all(event_trigger):
                    killed = True

                    time.sleep(ha_test_args["kill_delay"])

                    kill_target = ha_test_args["kill_target"]
                    if kill_target == "server": 
                        #TODO need to work on when to restart? can just do a sleep and then a restart? this means I cannot restart at a specific point though
                        active_server_id = site_launcher.get_active_server_id(self.admin_api.port)
                        site_launcher.stop_server(active_server_id)
                        if ha_test_args["setup"]["n_servers"] > 1:
                            last_read_line = 0 # only if switching servers
                        else:
                            time.sleep(5)
                            site_launcher.restart_server(active_server_id)
                    elif kill_target == "overseer": # test this!
                        site_launcher.stop_overseer()
                    elif kill_target == "client":
                        site_launcher.stop_client(site_launcher.client_properties.keys()[0])
                    elif kill_target == "client server": # change to ["kill client", "kill server", "restart client"]? 
                        # or maybe need to change to list of tuples [(kill_target, when), (restart_target, when) ... ]

                        #kill client during training, change the server, then restart the client
                        client_id = list(site_launcher.client_properties.keys())[0]
                        site_launcher.stop_client(client_id)
                        self.admin_api.remove_client([site_launcher.client_properties[client_id]["name"]])  #these 2 test
                    
                        # time.sleep(5)
                        # active_server_id = site_launcher.get_active_server_id(self.admin_api.port)
                        # site_launcher.stop_server(active_server_id)
                        time.sleep(15)
                        print("RESTARTING CLIENT") # TODO need to investigate why this doesn't work
                        #site_launcher.restart_client(client_id) # add site_launcher to init args?
                        self.admin_api.restart(TargetType.CLIENT, [site_launcher.client_properties[client_id]["name"]])
                        time.sleep(10)
                    continue

            response = self.admin_api.check_status(target_type=TargetType.SERVER)
            if response and "status" in response and response["status"] != APIStatus.SUCCESS:
                print("NO ACTIVE SERVER!") # for debugging
                
            if response and "status" in response and "details" in response and response["status"] == APIStatus.SUCCESS:

                if killed and not test_complete and response["status"] == APIStatus.SUCCESS and server_logs_string:
                    result_state = ha_test_args["result_state"]
                    for k, v in result_state.items():
                        if k == "round":
                            print(f"ASSERT Current round: {round_number} == Expected round: {v}")
                            assert round_number == v
                        elif k == "workflow":
                            # print(f"ASSERT Current workflow: {workflow} == Expected workflow: {list(wfs.items())[v][0]}")
                            # assert workflow == list(wfs.items())[v][0]
                            print(f"ASSERT Current workflow: {workflow} == Expected workflow: {wfs[v][0]}")
                            assert workflow == wfs[v][0]

                    test_complete = True

                if FLDetailKey.SERVER_ENGINE_STATUS in response["details"] and response["details"][FLDetailKey.SERVER_ENGINE_STATUS] == "stopped":
                    response = self.admin_api.check_status(target_type=TargetType.CLIENT)
                    if response["status"] != APIStatus.SUCCESS:
                        #raise RuntimeError(f"check_status failed: {response}")
                        print(f"CHECK status failed: {response}")
                    for row in response["details"]["client_statuses"]:
                        if row[3] != "stopped":
                            continue
                    training_done = True
            time.sleep(self.poll_period)

    def process_stats(self, stats, round_number, current_workflow): #TODO maybe keep state as a dict?
        #STATS: {'status': <APIStatus.SUCCESS: 'SUCCESS'>, 
        #        'details': {
        #           'message': {
        #               'ScatterAndGather': {
        #                   'tasks': {'train': []}, 
        #                   'phase': 'train', 
        #                   'current_round': 0, 
        #                   'num_rounds': 2}, 
        #               'CrossSiteModelEval': 
        #                   {'tasks': {}}, 
        #               'ServerRunner': {
        #                   'run_number': 1, 
        #                   'status': 'started', 
        #                   'workflow': 'scatter_and_gather'
        #                }
        #            }
        #       }, 
        # 'raw': {'time': '2022-04-04 15:13:09.367350', 'data': [{'type': 'dict', 'data': {'ScatterAndGather': {'tasks': {'train': []}, 'phase': 'train', 'current_round': 0, 'num_rounds': 2}, 'CrossSiteModelEval': {'tasks': {}}, 'ServerRunner': {'run_number': 1, 'status': 'started', 'workflow': 'scatter_and_gather'}}}], 'status': <APIStatus.SUCCESS: 'SUCCESS'>}}
        wfs = {}
        if stats and "status" in stats and "details" in stats and stats["status"] == APIStatus.SUCCESS:
            if "message" in stats["details"]:
                wfs = stats["details"]["message"]
                # current_workflow = None
                # round_number = None
                for item in wfs:
                    if wfs[item].get("tasks"):
                        current_workflow = item
                        if "current_round" in wfs[item]:
                            round_number = wfs[item]["current_round"]
                        
        return round_number, current_workflow, wfs

    # def process_logs(self, logs, round_number, workflow): #USE STATS INSTEAD FOR STATE!!!
    #     # matches latest instance of "Round {0-999} started."
    #     match = re.search("Round ([0-9]|[1-9][0-9]|[1-9][0-9][0-9]) started\.(?!.*Round ([0-9]|[1-9][0-9]|[1-9][0-9][0-9]) started\.)", logs)
    #     if match:
    #         round_number = int(match.group(1))

    #     # matches latest instance of "wf={workflow}," or "wf={workflow}]"
    #     match = re.search("(wf=)([^\,\]]+)(\,|\])(?!.*(wf=)([^\,\]]+)(\,|\]))", logs)
    #     if match:
    #         workflow = match.group(2) 

    #     return round_number, workflow

    def finalize(self):
        self.admin_api.shutdown(target_type=TargetType.ALL)
