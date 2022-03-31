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

#TODO make app agnostic for more generalizable tests (also cyclic) DONE
#TODO figure out hanging thread on exit bug (this is the worker process pr YT fix) DONE
#TODO kill threads on unclean exit? aka catch ctrl-c and also send to finally statement? DONE (see above)
#TODO make this file a class? where certain vars are intialized? aka things like rounds and workflows are app specific and need to be initalized DONE
#TODO break run_app_ha() into multiple functions DONE


#TODO figure out hanging thread on exit bug (this is the worker process pr YT fix)

#TODO investigate more specific killing time? such as sending task / model? end of round?
#TODO how to encode restarting? update: use ordering of kills/restarts with time.sleep()
#TODO figure out killing and restarting client issue
#TODO see if this works with latest dev2.1 branch, need to update to work with MT
#TODO make sure original run_app_tests.sha and run_example_tests.sh work, or maybe create a separate ha_test_runner.py?

#encode starting restarting with state change (what about more specific string based things like sending model?)
#fix client restarting
#fix end workflow state killing after completed run
#get everything to work with new dev2.1
#clean up

#14 upload a job, kill the server during training, restart it should pick up the work
test_case_14 = {
    "setup": {"n_servers": 1, "n_clients": 2},
    "kill_target": "server", 
    #"event": ROUND_1_TRAINING,
    "event": {"round": 1},
    "kill_delay": 2, 
    "result_state": {"round": 1}
}

#15 upload a job, kill the server after we start training but no round is completed, restart it should pick up the work
test_case_15 = {
    "setup": {"n_servers": 1, "n_clients": 2},
    "kill_target": "server", 
    "event": {"round": 0},
    "kill_delay": 2, 
    "result_state": {"round": 0}
}

#16 upload a job, kill the server during sending models to clients, restart it should pick up the work
BEFORE_SENDING_MODELS = "- ScatterAndGather - INFO - [run=1, wf=scatter_and_gather]: scheduled task train"

#17 upload a job, kill the primary server during training, the second one should pick up the work
test_case_17 = {
    "setup": {"n_servers": 2, "n_clients": 2},
    "kill_target": "server", 
    "event": {"round": 1},
    "kill_delay": 2, 
    "result_state": {"round": 1}
}

#18 upload a job, kill the primary server after we start training but no round is completed, the second one should start from round 0
test_case_18 = {
    "setup": {"n_servers": 2, "n_clients": 2},
    "kill_target": "server", 
    "event": {"round": 0},
    "kill_delay": 2, 
    "result_state": {"round": 0}
}

#19 upload a job, kill the primary server  during sending models to clients, the second one should start from round 0

#20 upload a job that has multiple workflows, kill the primary server when the first workflow is completed, the second one should start with the second workflow
test_case_20 = {
    "setup": {"n_servers": 2, "n_clients": 2},
    "kill_target": "server", 
    "event": {"workflow": 1},
    "kill_delay": 5, 
    "result_state": {"workflow": 1}
} #instead of string event, do based on state change??

#21 upload a job, kill the OverSeer, since the primary server is still running, things should run into completion (if client sites already get the old SP info.)

#22 kill overseer with old information
test_case_22 = {
    "setup": {"n_servers": 2, "n_clients": 2},
    "kill_target": "overseer", 
    "event": {"round": 0}, 
    "kill_delay": 1, 
}

#23
# kill overseer with no information
# test_case_23 = {
#     "setup": {"n_servers": 2, "n_clients": 2},
#     "kill_target": "overseer", 
#     "event": {"round": 0},
#     "kill_delay": 1, 
# }

#24
# start overseer, client, then server

#25
# overseer returns there is no hot endpoint available? -> fallback to previous SP

#26
# overseer gives wrong information? -> keep trying

#27
# sequence of kills and restarts of server -> need to change to list of tuples [(kill_target, when), (restart_target, when) ... ]
# test_case_27 = {
#     "setup": {"n_servers": 2, "n_clients": 2},
#     "kill_target": "server", 
#     "event": "TBD", 
#     "kill_delay": 1, 
# }

#28
# kill client during training, change server, restart client
test_case_28 = { # -> need to change to list of tuples [(kill_target, when), (restart_target, when) ... ]
    "setup": {"n_servers": 2, "n_clients": 1},
    "kill_target": "client server", 
    "event": {"round": 0},
    "kill_delay": 5, 
    "result_state": {"round": 0}
}

#29
# overseer dies, will job submit fail?

#30
# no overseer section in fed_client.json

#31 After the successful run is completed, kill the server, restart it, it should NOT go into training phase
AFTER_SUCCESSFUL_RUN = "- ServerRunner - INFO - [run=1, wf=cross_site_validate]: Workflow: cross_site_validate finalizing ..."
test_case_31 = {
    "setup": {"n_servers": 1, "n_clients": 2},
    "kill_target": "server", 
    "event": {"round": None, "workflow": -1},
    "kill_delay": 1, 
    "result_state": {"round": None, "workflow": None}
}

#TODO [('ScatterAndGather', {'tasks': {}, 'phase': '_finished_', 'current_round': 2, 'num_rounds': 2}), ('CrossSiteModelEval', {'tasks': {}}), (None, None)] <class 'list'>
            #when run is finished

#32 After the successful run is completed, kill the 1st server, the second server should NOT go into training phase
AFTER_SUCCESSFUL_RUN = "- ServerRunner - INFO - [run=1, wf=cross_site_validate]: Workflow: cross_site_validate finalizing ..."
test_case_32 = {
    "setup": {"n_servers": 2, "n_clients": 2},
    "kill_target": "server", 
    "event": {"round": None, "workflow": None},
    "kill_delay": 1, 
    "result_state": {}
}

#1 upload a job, kill the primary server after we start training but no round is completed, the second one should start from round 0
test_case_101 = {
    "setup": {"n_servers": 2, "n_clients": 2},#, "overseer": True}, #"overseer": True or 1?
    # "kill_target": "server", 
    # "event": {"round": 0},
    "events": [
        {
            "target": "server", 
            "action": "kill", 
            "when": {"round": 0}, 
            "delay": 5,
            "result_state": {"round": 0},
        }, #make targetype.SERVER?
        {
            "target": "server", 
            "action": "kill", 
            "when": {"round": 1}, 
            "delay": 5,
            "result_state": {"round": 1},
        }, #make targetype.SERVER?
    ],
    # "kill_delay": 2, 
    # "result_state": {"round": 0}
}

#1 upload a job, kill the primary server after we start training but no round is completed, the second one should start from round 0
test_case_102 = {
    "setup": {"n_servers": 2, "n_clients": 2},#, "overseer": True}, #"overseer": True or 1?
    "kill_target": "server", 
    "event": {"round": 0},
    "kill_delay": 2, 
    "result_state": {"round": 0} #wokflow -> task -> rounds/task specific args
}

# kill and restart at random times, see what happens?
# look at tasks ex: train, submit_model, validate for more specificity?

ha_tests = [test_case_102]#test_case_31], test_case_17]#, test_case_18]
