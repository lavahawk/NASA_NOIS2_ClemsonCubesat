from __future__ import annotations

import logging

from background_worker import BackgroundWorker, WorkerConfig


def main() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    config = WorkerConfig.from_env()
    worker = BackgroundWorker(config)
    worker.run_forever()


if __name__ == "__main__":
    main()
