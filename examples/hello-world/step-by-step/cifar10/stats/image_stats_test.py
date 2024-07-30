from src.fl.net import Net

from nvflare import FedAvg, FedJob, ScriptExecutor, FilterType

from nvflare.app_common.workflows.statistics_controller import StatisticsController
from nvflare.app_common.statistics.json_stats_file_persistor import JsonStatsFileWriter
from nvflare.app_common.executors.statistics.statistics_executor import StatisticsExecutor
from image_statistics import ImageStatistics
from nvflare.app_common.filters.statistics_privacy_filter import StatisticsPrivacyFilter
from nvflare.app_common.statistics.min_count_cleanser import MinCountCleanser


CIFAR10_ROOT = "/tmp/nvflare/data/cifar10"

if __name__ == "__main__":
    n_clients = 2

    job = FedJob(name="cifar10_fedavg")

    # Define the controller workflow and send to server
    controller = StatisticsController(
        min_clients=n_clients,
        statistic_configs=
            {
                "count": {},
                "histogram": {
                    "*": {
                    "bins": 255,
                    "range": [0,256]
                    }
                }
            },
        writer_id=job.as_id(
            JsonStatsFileWriter(
                output_path="statistics/image_statistics.json",
                json_encoder_path="nvflare.app_common.utils.json_utils.ObjectEncoder"
            )
        ),
        enable_pre_run_task=False
    )
    job.to(controller, "server")

    # Add clients
    for i in range(n_clients):
        executor = StatisticsExecutor(
            generator_id=job.as_id(ImageStatistics(data_root=CIFAR10_ROOT))
        )
        job.to(executor, f"site-{i}", gpu=0)
        filter = StatisticsPrivacyFilter(
            result_cleanser_ids=[job.as_id(MinCountCleanser(min_count=20))]
        )
        job.to(filter, f"site-{i}", tasks=["fed_stats"], filter_type=FilterType.TASK_RESULT)

    # job.export_job("/tmp/nvflare/jobs/job_config")
    job.simulator_run("/tmp/nvflare/jobs/workdir")
