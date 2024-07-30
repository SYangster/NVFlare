import sys
import os

sys.path.insert(0, os.path.join(os.getcwd(), ".."))

from src.fl.net import Net

from nvflare import FedJob, ScriptExecutor
from nvflare.apis.dxo import DataKind
from nvflare.app_common.aggregators.intime_accumulate_model_aggregator import InTimeAccumulateWeightedAggregator
from nvflare.app_common.ccwf import (
    CrossSiteEvalClientController,
    CrossSiteEvalServerController,
    SwarmClientController,
    SwarmServerController,
)
from nvflare.app_common.ccwf.comps.simple_model_shareable_generator import SimpleModelShareableGenerator
from nvflare.app_opt.pt.file_model_persistor import PTFileModelPersistor

if __name__ == "__main__":
    n_clients = 2
    num_rounds = 3
    train_script = "../src/fl/train.py"

    job = FedJob(name="cifar10_swarm")

    ctrl1 = SwarmServerController(
        num_rounds=num_rounds,
    )
    job.to(ctrl1, "server")
    ctrl2 = CrossSiteEvalServerController(eval_task_timeout=300)
    job.to(ctrl2, "server")

    # Define the initial server model
    job.to(Net(), "server")

    for i in range(n_clients):
        executor = ScriptExecutor(task_script_path=train_script)
        job.to(executor, f"site-{i}", gpu=0, tasks=["train", "validate", "submit_model"])

        # In swarm learning, each client acts also as an aggregator
        aggregator = InTimeAccumulateWeightedAggregator(expected_data_kind=DataKind.WEIGHTS)
        #job.to(aggregator, f"site-{i}")

        # In swarm learning, each client uses a model persistor and shareable_generator
        persistor = PTFileModelPersistor(model=Net())
        #job.to(persistor, f"site-{i}")
        shareable_generator = SimpleModelShareableGenerator()
        #job.to(shareable_generator, f"site-{i}")

        client_ctrl1 = SwarmClientController(
            aggregator_id=job.as_id(aggregator),
            persistor_id=job.as_id(persistor),
            shareable_generator_id=job.as_id(shareable_generator),
        )
        job.to(client_ctrl1, f"site-{i}", tasks=["swarm_*"])

        client_ctrl2 = CrossSiteEvalClientController()
        job.to(client_ctrl2, f"site-{i}", tasks=["cse_*"])

    # job.export_job("/tmp/nvflare/jobs/job_config")
    job.simulator_run("/tmp/nvflare/jobs/workdir")
