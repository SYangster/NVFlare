from src.fl.net import Net

import sys
sys.path.append('.')
print(sys.path)

from nvflare import FedAvg, FedJob, ScriptExecutor
from nvflare.app_common.executors.model_learner_executor import ModelLearnerExecutor
from nvflare.app_common.workflows.cross_site_eval import CrossSiteEval
from src.fl.model_learner import CIFAR10ModelLearner #TODO



CIFAR10_ROOT = "/tmp/nvflare/data/cifar10"

if __name__ == "__main__":
    n_clients = 2
    num_rounds = 2
    train_script = "../src/fl/train_with_mlflow.py"
    task_script_args = f"--batch_size 4 --dataset_path {CIFAR10_ROOT} --num_workers 2"

    job = FedJob(name="cifar10_fedavg")

    # Define the controller workflow and send to server
    controller1 = FedAvg(
        num_clients=n_clients,
        num_rounds=num_rounds,
    )
    job.to(controller1, "server")

    controller2 = CrossSiteEval()
    job.to(controller2, "server")

    # Define the initial global model and send to server
    job.to(Net(), "server")

    # Add clients
    for i in range(n_clients):
        learner = CIFAR10ModelLearner(epochs=2, lr=0.001)
        executor = ModelLearnerExecutor(learner_id=job.as_id(learner))
        job.to(executor, f"site-{i}", tasks=["train", "submit_model", "validate"], gpu=0)

    # job.export_job("/tmp/nvflare/jobs/job_config")
    job.simulator_run("/tmp/nvflare/jobs/workdir")


 ####
    # ctrl1 = FedAvg(
    #     num_clients=n_clients,
    #     num_rounds=num_rounds,
    # )
    # ctrl2 = CrossSiteModelEval()

    # load_cifar10_data()  # preload CIFAR10 data
    # data_splitter = Cifar10DataSplitter(
    #     split_dir=train_split_root,
    #     num_sites=n_clients,
    #     alpha=alpha,
    # )

    # job.to(ctrl1, "server")
    # job.to(ctrl2, "server")
    # job.to(data_splitter, "server")

    # # Define the initial global model and send to server
    # job.to(ModerateCNN(), "server")

    # for i in range(n_clients):
    #     learner = CIFAR10ModelLearner(train_idx_root=train_split_root, aggregation_epochs=aggregation_epochs, lr=0.01)
    #     executor = ModelLearnerExecutor(learner_id=job.as_id(learner))
    #     job.to(executor, f"site-{i+1}", gpu=0)  # data splitter assumes client names start from 1

    # # job.export_job("/tmp/nvflare/jobs/job_config")
    # job.simulator_run("/tmp/nvflare/jobs/workdir")
