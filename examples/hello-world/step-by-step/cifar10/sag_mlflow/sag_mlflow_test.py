from src.fl.net import Net

from nvflare import FedAvg, FedJob, ScriptExecutor
from nvflare.app_opt.tracking.mlflow.mlflow_receiver import MLflowReceiver

CIFAR10_ROOT = "/tmp/nvflare/data/cifar10"

if __name__ == "__main__":
    n_clients = 2
    num_rounds = 2
    train_script = "../src/fl/train_with_mlflow.py"
    task_script_args = "--batch_size 6 --dataset_path /tmp/nvflare/data/cifar10 --num_workers 2"

    job = FedJob(name="cifar10_fedavg")

    # Define the controller workflow and send to server
    controller = FedAvg(
        num_clients=n_clients,
        num_rounds=num_rounds,
    )
    job.to(controller, "server")

    receiver = MLflowReceiver(
        tracking_uri="file:///tmp/nvflare/jobs/workdir/server/simulate_job/mlruns", #TODO "file:///{WORKSPACE}/{JOB_ID}/mlruns\"
        kwargs={
            "experiment_name": "nvflare-fedavg-np-experiment",
            "run_name": "nvflare-fedavg-np-with-mlflow",
            "experiment_tags": {"mlflow.note.content": "## **NVFlare FedAvg PyTorch experiment with MLflow**"},
            "run_tags": {"mlflow.note.content": "## Federated Experiment tracking with MLflow \n### Example of using **[NVIDIA FLARE](https://nvflare.readthedocs.io/en/main/index.html)** to train an image classifier using federated averaging ([FedAvg]([FedAvg](https://arxiv.org/abs/1602.05629))) and [PyTorch](https://pytorch.org/) as the deep learning training framework. This example also highlights the NVFlare streaming capability from the clients to the server.\n\n> **_NOTE:_** \n This example uses the *[CIFAR-10](https://www.cs.toronto.edu/~kriz/cifar.html)* dataset and will load its data within the trainer code.\n"},
        },
        artifact_location="artifacts",
        events=["fed.analytix_log_stats"],
    )
    job.to(receiver, "server")

    # Define the initial global model and send to server
    job.to(Net(), "server")

    # Add clients
    for i in range(n_clients):
        executor = ScriptExecutor(
            task_script_path=train_script, task_script_args=task_script_args
        )
        job.to(executor, f"site-{i}", gpu=0)

    # job.export_job("/tmp/nvflare/jobs/job_config")
    job.simulator_run("/tmp/nvflare/jobs/workdir")