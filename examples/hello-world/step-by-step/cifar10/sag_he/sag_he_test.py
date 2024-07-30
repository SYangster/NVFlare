from src.fl.net import Net

from nvflare import FedAvg, FedJob, ScriptExecutor, FilterType
from nvflare.app_opt.he.model_serialize_filter import HEModelSerializeFilter
from nvflare.app_opt.pt.file_model_persistor import PTFileModelPersistor

from nvflare.app_opt.he.model_decryptor import HEModelDecryptor
from nvflare.app_opt.he.model_encryptor import HEModelEncryptor


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

    job.to(
        PTFileModelPersistor(
            model=Net(),
            filter_id=job.as_id(HEModelSerializeFilter())
        ),
        "server"
    )

    # Define the initial global model and send to server
    #job.to(Net(), "server")

    # Add clients
    for i in range(n_clients):
        executor = ScriptExecutor(
            task_script_path=train_script
        )
        job.to(executor, f"site-{i}", gpu=0)
        job.to(HEModelDecryptor(), f"site-{i}", tasks=["train"], filter_type=FilterType.TASK_DATA)
        job.to(HEModelEncryptor(), f"site-{i}", tasks=["train"], filter_type=FilterType.TASK_RESULT)

    #job.export_job("/tmp/nvflare/jobs/job_config")
    job.simulator_run("/tmp/nvflare/jobs/workdir")