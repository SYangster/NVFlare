import sys
import os

sys.path.insert(0, os.path.join(os.getcwd(), ".."))

from src.fl.net import Net

from nvflare import FedAvg, FedJob, ScriptExecutor

from nvflare.app_common.workflows.cyclic import Cyclic

from nvflare import FedJob, ScriptExecutor
from nvflare.app_common.ccwf import CyclicClientController, CyclicServerController
from nvflare.app_common.ccwf.comps.simple_model_shareable_generator import SimpleModelShareableGenerator
from nvflare.app_opt.pt.file_model_persistor import PTFileModelPersistor

if __name__ == "__main__":
    n_clients = 2
    num_rounds = 3
    train_script = "../src/fl/train.py"

    job = FedJob(name="cifar10_cyclic")

    controller = CyclicServerController(num_rounds=num_rounds, max_status_report_interval=300)
    job.to(controller, "server")

    for i in range(n_clients):
        executor = ScriptExecutor(
            task_script_path=train_script
        )
        job.to(executor, f"site-{i}", tasks=["train"], gpu=0)

        # Add client-side controller for cyclic workflow
        executor = CyclicClientController()
        job.to(executor, f"site-{i}", tasks=["cyclic_*"])

        # In swarm learning, each client uses a model persistor and shareable_generator
        job.to(PTFileModelPersistor(model=Net()), f"site-{i}", id="persistor")
        job.to(SimpleModelShareableGenerator(), f"site-{i}", id="shareable_generator")

    # job.export_job("/tmp/nvflare/jobs/job_config")
    job.simulator_run("/tmp/nvflare/jobs/workdir")
