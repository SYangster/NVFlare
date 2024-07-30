import sys
import os

sys.path.insert(0, os.path.join(os.getcwd(), ".."))

from src.fl.net import Net

from nvflare import FedAvg, FedJob, ScriptExecutor

CIFAR10_ROOT = "/tmp/nvflare/data/cifar10"

if __name__ == "__main__":
    n_clients = 2
    num_rounds = 2
    train_script = "../src/fl/train_with_mlflow.py"
    task_script_args = f"--batch_size 4 --dataset_path {CIFAR10_ROOT} --num_workers 2"

    job = FedJob(name="cifar10_fedavg")

    # Define the controller workflow and send to server
    controller = FedAvg(
        num_clients=n_clients,
        num_rounds=num_rounds,
    )
    job.to(controller, "server")

    # Define the initial global model and send to server
    job.to(Net(), "server")

    # Add clients
    for i in range(n_clients):
        executor = ScriptExecutor(
            task_script_path=train_script, task_script_args=task_script_args
        )
        job.to(executor, f"site-{i}", gpu=0)
        # job.to("../src/fl/train_with_mlflow.py", f"site-{i}")

    # job.export_job("/tmp/nvflare/jobs/job_config")
    job.simulator_run("/tmp/nvflare/jobs/workdir")