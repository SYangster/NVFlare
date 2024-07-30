from src.fl.net import Net

from nvflare import FedAvg, FedJob, ScriptExecutor

CIFAR10_ROOT = "/tmp/nvflare/data/cifar10"

if __name__ == "__main__":
    n_clients = 2
    num_rounds = 2
    train_script = "../src/fl/train.py"

    job = FedJob(name="cifar10_fedavg")

    # Define the controller workflow and send to server
    controller = FedAvg(
        num_clients=n_clients,
        num_rounds=num_rounds,
    )
    job.to(controller, "server")

    # Define the initial global model and send to server
    job.to(Net(), "server")

    executor0 = ScriptExecutor(
        task_script_path=train_script, task_script_args="--batch_size 4"
    )
    job.to(executor0, f"site-{0}", gpu=0)
    
    executor1 = ScriptExecutor(
        task_script_path=train_script, task_script_args="--batch_size 6"
    )
    job.to(executor1, f"site-{1}", gpu=0)

    # job.export_job("/tmp/nvflare/jobs/job_config")
    job.simulator_run("/tmp/nvflare/jobs/workdir")
