from src.fl.net import Net

from nvflare import FedAvg, FedJob, ScriptExecutor
from nvflare.app_common.executors.model_learner_executor import ModelLearnerExecutor
from nvflare.app_common.workflows.cross_site_eval import CrossSiteEval
from nvflare.app_common.workflows.initialize_global_weights import InitializeGlobalWeights
from src.fl.executor import CIFAR10Executor #TODO


CIFAR10_ROOT = "/tmp/nvflare/data/cifar10"

if __name__ == "__main__":
    n_clients = 2
    num_rounds = 2

    job = FedJob(name="cifar10_fedavg")

    ctrl1 = InitializeGlobalWeights(task_name="get_weights")
    job.to(ctrl1, "server")

    # Define the controller workflow and send to server
    ctrl2 = FedAvg(
        num_clients=n_clients,
        num_rounds=num_rounds,
    )
    job.to(ctrl2, "server")

    ctrl3 = CrossSiteEval()
    job.to(ctrl3, "server")

    # Define the initial global model and send to server
    job.to(Net(), "server")

    # Add clients
    for i in range(n_clients):
        executor = CIFAR10Executor(epochs=2, lr=0.001)
        job.to(executor, f"site-{i}", tasks=["get_weights", "train", "submit_model", "validate"], gpu=0)

    # job.export_job("/tmp/nvflare/jobs/job_config")
    job.simulator_run("/tmp/nvflare/jobs/workdir")
