from src.fl.net import Net

from nvflare import FedAvg, FedJob, ScriptExecutor

from nvflare.app_common.workflows.cyclic import Cyclic

CIFAR10_ROOT = "/tmp/nvflare/data/cifar10"

if __name__ == "__main__":
    n_clients = 2
    num_rounds = 3
    train_script = "../src/fl/train.py"

    job = FedJob(name="cifar10_fedavg")

    # Define the controller workflow and send to server
    controller = Cyclic(
        num_clients=n_clients,
        num_rounds=num_rounds,
    )
    job.to(controller, "server")

    # Define the initial global model and send to server
    job.to(Net(), "server")

    # Add clients
    for i in range(n_clients):
        executor = ScriptExecutor(
            task_script_path=train_script
        )
        job.to(executor, f"site-{i}", gpu=0)

    # job.export_job("/tmp/nvflare/jobs/job_config")
    job.simulator_run("/tmp/nvflare/jobs/workdir")